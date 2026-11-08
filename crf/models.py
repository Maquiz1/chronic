"""Participant record plus one table per CRF section, generated from crf/spec.py.

Every CRF field is optional in the database: sections are saved as far as they are known and completed later
(for example when laboratory results come back). Completeness is measured by the data quality module instead.
"""
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.utils import timezone
from simple_history import register
from simple_history.models import HistoricalRecords

from . import spec


class SoftDeleteFields(models.Model):
    """Deleting only hides a record: an Admin can restore it from "Deleted records"."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    deletion_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self, user, reason):
        self.is_deleted, self.deleted_at, self.deleted_by, self.deletion_reason = True, timezone.now(), user, reason
        self.save()

    def restore(self):
        self.is_deleted, self.deleted_at, self.deleted_by, self.deletion_reason = False, None, None, ''
        self.save()


class ActiveManager(models.Manager):
    """Records that are not deleted. Use `all_objects` to include deleted ones."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Participant(SoftDeleteFields):
    study_id = models.CharField('Study ID', max_length=30, unique=True, editable=False)
    # Required by the form; nullable only so records made before this field existed can be migrated and then filled.
    hospital_id = models.CharField('MRN', max_length=30, unique=True, null=True,
                                   help_text='MNH medical record number (MRN) of the patient, unique in the hospital system.')
    interview_date = models.DateField('Date of interview')
    admission_date = models.DateField('Date of admission', null=True, blank=True)
    phone_number = models.CharField('Patient phone number', max_length=30, blank=True)
    interviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='interviews')

    locked = models.BooleanField('Verified and locked', default=False)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+')
    locked_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords(excluded_fields=['updated_at'])

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.study_id

    def save(self, *args, **kwargs):
        if not self.study_id:
            with transaction.atomic():
                self.study_id = next_study_id()
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    def section(self, code, include_deleted=False):
        """The saved section row, or None if nothing was entered yet or it was deleted (uses select_related data)."""
        if code not in SECTION_MODELS:
            return None
        try:
            row = getattr(self, SECTION_RELATED_NAME[code])
        except ObjectDoesNotExist:
            return None
        if row.is_deleted and not include_deleted:
            return None
        return row

    def values(self):
        """All entered values as {column: value}, including header fields."""
        data = {'study_id': self.study_id, 'interview_date': self.interview_date,
                'admission_date': self.admission_date, 'phone_number': self.phone_number,
                'hospital_id': self.hospital_id}
        for code in SECTION_MODELS:
            row = self.section(code)
            for column in SECTION_COLUMNS[code]:
                data[column] = getattr(row, column) if row else None
            data[f'_nd_{code}'] = list(row.not_done) if row else []
            data[f'_saved_{code}'] = row is not None
        return data

    def lock(self, user):
        self.locked, self.locked_by, self.locked_at = True, user, timezone.now()
        self.save(update_fields=['locked', 'locked_by', 'locked_at', 'updated_at'])

    def unlock(self):
        self.locked, self.locked_by, self.locked_at = False, None, None
        self.save(update_fields=['locked', 'locked_by', 'locked_at', 'updated_at'])


def next_study_id():
    prefix = settings.STUDY_ID_PREFIX
    last = (Participant.all_objects.select_for_update().filter(study_id__startswith=f'{prefix}-')
            .order_by('-study_id').values_list('study_id', flat=True).first())
    number = int(last.rsplit('-', 1)[1]) + 1 if last else 1
    return f'{prefix}-{number:04d}'


class SectionBase(SoftDeleteFields):
    """Fields shared by every section table. A deleted section counts as not entered until it is restored."""

    not_done = models.JSONField(default=list, blank=True,
                                help_text='Fields marked "not done / not available"; not counted as missing.')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def _django_field(f):
    kw = {'verbose_name': f.label[:250], 'help_text': f.help}
    if f.type == 'integer':
        return models.IntegerField(null=True, blank=True, **kw)
    if f.type == 'decimal':
        return models.DecimalField(max_digits=9, decimal_places=f.dp or 1, null=True, blank=True, **kw)
    if f.type == 'date':
        return models.DateField(null=True, blank=True, **kw)
    if f.type == 'text':
        return models.CharField(max_length=255, blank=True, default='', **kw)
    if f.type == 'select_one':
        return models.SmallIntegerField(choices=spec.CHOICES[f.choices], null=True, blank=True, **kw)
    raise ValueError(f'No database field for type {f.type}')


SECTION_MODELS = {}
SECTION_COLUMNS = {}
SECTION_RELATED_NAME = {}

# Model (class) names stay tied to the section's topic, not its letter, so that a new CRF version can re-letter
# sections without moving data: v0.2 turned Etiology from E into D, Examination from D into F, etc. The names below
# are the ones the v0.1 tables were created with; a section added later gets "Section" + its key in CamelCase.
MODEL_NAMES = {'sociodemographic': 'SectionA', 'liver_history': 'SectionB', 'presentation': 'SectionC',
               'examination': 'SectionD', 'etiology': 'SectionE', 'comorbidities': 'SectionF',
               'investigations': 'SectionG', 'complications': 'SectionH', 'transplant': 'SectionK',
               'outcome': 'SectionL'}


def model_name(section):
    return MODEL_NAMES.get(section.key) or 'Section' + ''.join(part.title() for part in section.key.split('_'))


for _section in spec.SECTIONS:
    if not _section.fields:
        continue  # e.g. Sections I and J are calculated only
    SECTION_RELATED_NAME[_section.code] = f'section_{_section.key}'
    attrs = {
        '__module__': __name__,
        '__doc__': f'CRF Section {_section.code}: {_section.title}',
        'participant': models.OneToOneField(Participant, on_delete=models.CASCADE,
                                            related_name=SECTION_RELATED_NAME[_section.code]),
        'SECTION': _section,
        'Meta': type('Meta', (), {'db_table': f'crf_section_{_section.key}',
                                  'verbose_name': f'Section {_section.code}: {_section.title}',
                                  'verbose_name_plural': f'Section {_section.code}: {_section.title}'}),
    }
    columns = []
    for _f in _section.fields:
        if _f.type == 'select_multiple':
            for code, label in spec.CHOICES[_f.choices]:
                attrs[f'{_f.name}_{code}'] = models.BooleanField(label, default=False)
                columns.append(f'{_f.name}_{code}')
        else:
            attrs[_f.name] = _django_field(_f)
            columns.append(_f.name)
    _model = type(model_name(_section), (SectionBase,), attrs)
    register(_model, excluded_fields=['updated_at'])
    globals()[_model.__name__] = _model
    SECTION_MODELS[_section.code] = _model
    SECTION_COLUMNS[_section.code] = columns


# For Participant.objects.select_related(*SECTION_RELATED): one query loads every section.
SECTION_RELATED = list(SECTION_RELATED_NAME.values())
