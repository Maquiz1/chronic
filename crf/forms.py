import re
from decimal import Decimal

from django import forms
from django.urls import reverse
from django.utils.html import format_html

from accounts.widgets import BootstrapFormMixin, bootstrapify

from . import spec
from .models import SECTION_COLUMNS, SECTION_MODELS, Participant

RADIO_MAX_OPTIONS = 4
HOSPITAL_ID_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9/\-. ]{1,28}[A-Z0-9]$')


def normalise_hospital_id(value):
    """Upper case, single spaces, no spaces around - or /, so the same number is always stored the same way."""
    value = re.sub(r'\s+', ' ', (value or '').strip().upper())
    return re.sub(r'\s*([-/])\s*', r'\1', value)


class ParticipantForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Participant
        fields = ['hospital_id', 'interview_date', 'admission_date', 'phone_number']
        widgets = {'interview_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'admission_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'hospital_id': forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'off',
                                                         'style': 'text-transform: uppercase'})}
        help_texts = {'hospital_id': 'Required. The patient\'s MNH medical record number (MRN) from the hospital system. '
                                     'Visible only to Data Clerks, Data Managers and Admins.',
                      'phone_number': 'Optional. Visible only to Data Clerks, Data Managers and Admins.',
                      'admission_date': 'Can be added later.'}
        error_messages = {'hospital_id': {'unique': 'This MRN is already registered.'}}

    def __init__(self, *args, show_identity=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hospital_id'].required = True
        if not show_identity:
            del self.fields['phone_number']
            del self.fields['hospital_id']

    def clean_hospital_id(self):
        value = normalise_hospital_id(self.cleaned_data.get('hospital_id'))
        if not HOSPITAL_ID_PATTERN.match(value):
            raise forms.ValidationError('Use 3-30 letters, digits, "-", "/" or "." (as printed in the hospital system).')
        existing = Participant.all_objects.filter(hospital_id=value).exclude(pk=self.instance.pk).first()
        if existing and existing.is_deleted:
            raise forms.ValidationError(
                f'MRN {value} belongs to {existing.study_id}, which was deleted. Ask an Admin to restore it '
                f'(Deleted records) instead of registering the patient again.')
        if existing:
            raise forms.ValidationError(format_html(
                'MRN {} is already registered as <a href="{}">{}</a>. Open that record instead of registering '
                'the patient again.', value, reverse('crf:detail', args=[existing.pk]), existing.study_id))
        return value



def _widget(f):
    if f.type == 'date':
        return forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
    if f.type == 'select_one' and len(spec.CHOICES[f.choices]) <= RADIO_MAX_OPTIONS:
        return forms.RadioSelect
    if f.type == 'decimal':
        return forms.NumberInput(attrs={'step': 'any', 'inputmode': 'decimal'})
    if f.type == 'integer':
        return forms.NumberInput(attrs={'inputmode': 'numeric'})
    return None


class SectionFormBase(forms.ModelForm):
    """Every field optional. Impossible values are refused; skipped questions are cleared on save."""

    section = None  # spec.Section, set by section_form_class

    def __init__(self, *args, other_values=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.other_values = other_values or {}
        not_done = set(self.instance.not_done or []) if self.instance.pk else set()
        for f in self.section.fields:
            if f.type == 'select_one' and f.name in self.fields:
                field = self.fields[f.name]
                if isinstance(field.widget, forms.RadioSelect):
                    field.choices = spec.CHOICES[f.choices]
                if f.default is not None and getattr(self.instance, f.name, None) is None:
                    self.initial[f.name] = f.default
            if f.allow_nd:
                self.fields[f'nd__{f.name}'] = forms.BooleanField(
                    required=False, initial=f.name in not_done, label='Not done / not available')
        bootstrapify(self)

    def rows(self):
        """Fields in CRF order with what the template needs: grouping, units, skip rules, 'not done' box."""
        rows, current_group = [], None
        for f in self.section.fields:
            row = {'spec': f, 'group': f.group if f.group != current_group else None,
                   'relevant': [[n, op, v] for n, op, v in f.relevant],
                   'nd': self[f'nd__{f.name}'] if f.allow_nd else None}
            current_group = f.group
            if f.type == 'select_multiple':
                row['options'] = [(self[c], label) for c, (_code, label) in zip(f.columns, spec.CHOICES[f.choices])]
            else:
                row['bound'] = self[f.name]
            if f.by_unit:
                row['by_unit'] = {str(code): cfg for code, cfg in f.by_unit.items()}
            rows.append(row)
        return rows

    def clean(self):
        data = super().clean()
        values = {**self.other_values, **data}
        for f in self.section.fields:
            if f.type == 'select_multiple':
                continue
            x = data.get(f.name)
            if x in (None, '') or f.type not in ('integer', 'decimal'):
                continue
            if f.by_unit and data.get(f.unit_field) not in f.by_unit:
                self.add_error(f.unit_field, 'Choose the unit of this result.')
                continue
            unit, hard, _check, _ref = spec.limits(f, values)
            if hard and not Decimal(str(hard[0])) <= Decimal(x) <= Decimal(str(hard[1])):
                self.add_error(f.name, f'Impossible value. Allowed {hard[0]:g}-{hard[1]:g} {unit}.'.replace(' .', '.'))
        # Dates are not refused here: odd or impossible dates are saved and flagged in Data quality > Dates,
        # where a Data Manager can raise a query (quality/checks.py).
        if data.get('sym_other') is False and data.get('sym_other_specify'):
            data['sym_other_specify'] = ''
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        values = {**self.other_values, **{c: getattr(obj, c) for c in SECTION_COLUMNS[self.section.code]}}
        # Clear answers to questions that the skip rules now hide (e.g. grade when HE is Absent).
        for f in self.section.fields:
            if f.relevant and not spec.is_relevant(f, values):
                for column in f.columns:
                    empty = False if f.type == 'select_multiple' else ('' if f.type == 'text' else None)
                    setattr(obj, column, empty)
                    values[column] = empty
        # Length of stay left empty: fill it from the admission and discharge/death dates.
        if self.section.code == 'L' and getattr(obj, 'los_days', None) is None:
            from .derived import los_from_dates
            days = los_from_dates({**values, 'admission_date': self.other_values.get('admission_date')})
            if days is not None and days >= 0:
                obj.los_days = days
        not_done = []
        for f in self.section.fields:
            if not (f.allow_nd and self.cleaned_data.get(f'nd__{f.name}')):
                continue
            answered = any(getattr(obj, c) for c in f.columns) if f.type == 'select_multiple' \
                else getattr(obj, f.name) not in (None, '')
            if not answered:
                not_done.append(f.name)
        obj.not_done = not_done
        if commit:
            obj.save()
        return obj


def section_form_class(code):
    section = spec.SECTION_BY_CODE[code]
    widgets = {}
    for f in section.fields:
        w = _widget(f)
        if w is not None:
            widgets[f.name] = w
    meta = type('Meta', (), {'model': SECTION_MODELS[code], 'fields': SECTION_COLUMNS[code], 'widgets': widgets})
    return type(f'Section{code}Form', (SectionFormBase,), {'Meta': meta, 'section': section})


class QueryForm(BootstrapFormMixin, forms.Form):
    section = forms.ChoiceField(choices=[('Header', 'Header')] + [(s.code, f'{s.code}: {s.title}') for s in spec.SECTIONS])
    field = forms.ChoiceField(required=False, choices=[('', '(whole section)')] + [
        (f.name, f'{s.code} - {f.qn} {f.label}') for s, f in spec.all_fields()])
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))
