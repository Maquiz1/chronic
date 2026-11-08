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


class Participant(models.Model):
    study_id = models.CharField('Study ID', max_length=30, unique=True, editable=False)
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

    def section(self, code):
        """The saved section row, or None if nothing was entered yet (uses select_related data when present)."""
        if code not in SECTION_MODELS:
            return None
        try:
            return getattr(self, f'section_{code.lower()}')
        except ObjectDoesNotExist:
            return None

    def values(self):
        """All entered values as {column: value}, including header fields."""
        data = {'study_id': self.study_id, 'interview_date': self.interview_date,
                'admission_date': self.admission_date, 'phone_number': self.phone_number}
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
    last = (Participant.objects.select_for_update().filter(study_id__startswith=f'{prefix}-')
            .order_by('-study_id').values_list('study_id', flat=True).first())
    number = int(last.rsplit('-', 1)[1]) + 1 if last else 1
    return f'{prefix}-{number:04d}'


class SectionBase(models.Model):
    """Fields shared by every section table."""

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

for _section in spec.SECTIONS:
    if not _section.fields:
        continue  # e.g. Section J is calculated only
    attrs = {
        '__module__': __name__,
        '__doc__': f'CRF Section {_section.code}: {_section.title}',
        'participant': models.OneToOneField(Participant, on_delete=models.CASCADE, related_name=f'section_{_section.code.lower()}'),
        'SECTION': _section,
        'Meta': type('Meta', (), {'db_table': f'crf_section_{_section.code.lower()}_{_section.key}',
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
    _model = type(f'Section{_section.code}', (SectionBase,), attrs)
    register(_model, excluded_fields=['updated_at'])
    globals()[_model.__name__] = _model
    SECTION_MODELS[_section.code] = _model
    SECTION_COLUMNS[_section.code] = columns


# For Participant.objects.select_related(*SECTION_RELATED): one query loads every section.
SECTION_RELATED = [f'section_{code.lower()}' for code in SECTION_MODELS]
