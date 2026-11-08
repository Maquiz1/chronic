"""Data quality: completeness per section, range checks and consistency checks.

Nothing here blocks saving (impossible values are already refused by the form). The results feed the data
quality pages, the participant page and the queries that Data Managers raise.
"""
import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from crf import derived, spec
from crf.models import SECTION_MODELS

ERROR, WARNING = 'error', 'warning'


@dataclass
class Issue:
    level: str          # error | warning
    section: str        # section code, or 'Header'
    field: str          # column name ('' for record-level)
    message: str
    rule: str = ''      # short id, used to avoid raising the same query twice

    @property
    def label(self):
        if self.field in spec.FIELD_BY_NAME:
            s, f = spec.FIELD_BY_NAME[self.field]
            return f'{f.qn} {f.label}'
        return self.field


def is_answered(f, values):
    if f.type == 'select_multiple':
        return any(values.get(c) for c in f.columns)
    return values.get(f.name) not in (None, '')


def section_status(code, values):
    """Completeness of one section, following the skip rules."""
    section = spec.SECTION_BY_CODE[code]
    started = bool(values.get(f'_saved_{code}'))
    not_done_list = values.get(f'_nd_{code}') or []
    expected = answered = not_done = 0
    missing, nd_fields = [], []
    for f in section.fields:
        if not f.expected or not spec.is_relevant(f, values):
            continue
        expected += 1
        if is_answered(f, values):
            answered += 1
        elif f.name in not_done_list:
            not_done += 1
            nd_fields.append(f)
        else:
            missing.append(f)
    done = answered + not_done
    pct = round(100 * done / expected) if expected else 100
    if not section.fields:
        state = 'calculated'
    elif not started and not not_done:
        state = 'not_started'
    elif missing:
        state = 'incomplete'
    else:
        state = 'complete'
    return {'code': code, 'title': section.title, 'expected': expected, 'answered': answered, 'not_done': not_done,
            'missing': missing, 'nd_fields': nd_fields, 'pct': pct, 'state': state}


def record_status(values):
    sections = [section_status(s.code, values) for s in spec.SECTIONS]
    counted = [s for s in sections if s['state'] != 'calculated']
    expected = sum(s['expected'] for s in counted)
    done = sum(s['answered'] + s['not_done'] for s in counted)
    return {'sections': sections, 'pct': round(100 * done / expected) if expected else 100,
            'done': done, 'expected': expected,
            'missing_count': sum(len(s['missing']) for s in counted),
            'complete': all(s['state'] == 'complete' for s in counted)}


def _num(value):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return float(value)
    return None


def _fmt(x):
    return f'{x:g}' if isinstance(x, float) else str(x)


def range_issues(values):
    issues = []
    for section, f in spec.all_fields():
        if f.type not in ('integer', 'decimal') or not spec.is_relevant(f, values):
            continue
        x = _num(values.get(f.name))
        if x is None:
            continue
        if f.by_unit and values.get(f.unit_field) not in f.by_unit:
            issues.append(Issue(ERROR, section.code, f.unit_field, f'{f.label} is entered without a unit.', 'unit'))
            continue
        unit, hard, check, _ref = spec.limits(f, values)
        if hard and not hard[0] <= x <= hard[1]:
            issues.append(Issue(ERROR, section.code, f.name,
                                f'{_fmt(x)} {unit} is impossible (allowed {_fmt(hard[0])}-{_fmt(hard[1])}).', 'hard'))
        elif check and not check[0] <= x <= check[1]:
            hint = ''
            if f.by_unit:
                hint = ' Check that the right unit is selected.'
            issues.append(Issue(WARNING, section.code, f.name,
                                f'{_fmt(x)} {unit} is unusual (expected {_fmt(check[0])}-{_fmt(check[1])}). '
                                f'Verify against the source document.{hint}', 'check'))
    return issues


def reference_flag(f, values):
    """'L', 'H' or '' against the normal reference interval (clinical information, not a data error)."""
    x = _num(values.get(f.name))
    if x is None:
        return ''
    _unit, _hard, _check, ref = spec.limits(f, values)
    if not ref:
        return ''
    return 'L' if x < ref[0] else ('H' if x > ref[1] else '')


def _differs(values, a, b):
    return values.get(a) in (0, 1) and values.get(b) in (0, 1) and values.get(a) != values.get(b)


def consistency_issues(values):
    v = values
    out = []

    def add(level, section, field, message, rule):
        out.append(Issue(level, section, field, message, rule))

    today = timezone.localdate()
    interview, admission, outcome_date = v.get('interview_date'), v.get('admission_date'), v.get('outcome_date')
    if interview and interview > today:
        add(ERROR, 'Header', 'interview_date', 'Date of interview is in the future.', 'date_future')
    if settings.STUDY_START_DATE and interview:
        start = datetime.date.fromisoformat(settings.STUDY_START_DATE)
        if interview < start:
            add(WARNING, 'Header', 'interview_date', f'Date of interview is before the study start ({start}).', 'date_start')
    if admission and interview and admission > interview:
        add(ERROR, 'Header', 'admission_date', 'Admission date is after the interview date.', 'adm_after_int')
    if not v.get('hospital_id') and 'hospital_id' in v:
        add(ERROR, 'Header', 'hospital_id', 'Hospital ID is missing (required). Add it with "Edit header".', 'hosp_id')
    if not admission:
        add(WARNING, 'Header', 'admission_date', 'Admission date is missing (needed for length of stay).', 'adm_missing')
    if outcome_date and admission and outcome_date < admission:
        add(ERROR, 'L', 'outcome_date', 'Discharge/death date is before the admission date.', 'out_before_adm')
    if outcome_date and outcome_date > today:
        add(ERROR, 'L', 'outcome_date', 'Discharge/death date is in the future.', 'out_future')
    sample = v.get('lab_sample_date')
    if sample and sample > today:
        add(ERROR, 'G', 'lab_sample_date', 'Laboratory sample date is in the future.', 'lab_future')
    if sample and admission and (sample - admission).days < -7:
        add(WARNING, 'G', 'lab_sample_date', 'Laboratory sample is more than 7 days before admission.', 'lab_early')

    los, los_dates = v.get('los_days'), derived.los_from_dates(v)
    if los is not None and los_dates is not None and abs(los - los_dates) > 1:
        add(WARNING, 'L', 'los_days', f'Length of stay is {los} days but the dates give {los_dates} days.', 'los_dates')

    age = v.get('age_years')
    if age is not None:
        years = v.get('dx_duration') if v.get('dx_duration_unit') == 2 else None
        if years is not None and years > age:
            add(ERROR, 'B', 'dx_duration', 'Years since diagnosis is more than the age.', 'dx_gt_age')
        if v.get('alcohol_years') is not None and v['alcohol_years'] > age:
            add(ERROR, 'D', 'alcohol_years', 'Years of alcohol use is more than the age.', 'alc_gt_age')

    bmi = derived.bmi(v)
    if bmi is not None and not 12 <= bmi <= 60:
        add(WARNING, 'F', 'weight_kg', f'BMI {bmi} is implausible; check weight and height.', 'bmi')

    # Answers that contradict each other.
    if v.get('asterixis') == 1 and v.get('hepatic_enceph') == 0:
        add(WARNING, 'F', 'asterixis', 'Asterixis present but hepatic encephalopathy absent.', 'asterixis')
    if v.get('hepatic_enceph') == 1 and v.get('he_grade') == 0:
        add(WARNING, 'F', 'he_grade', 'Hepatic encephalopathy "Present" with grade 0 (grade 0 means none).', 'he_grade0')
    if v.get('ascites') == 1 and v.get('img_ascites') == 0:
        add(WARNING, 'G', 'img_ascites', 'Ascites present on examination (F7) but not on imaging (G23).', 'ascites_img')
    if v.get('k_refractory_ascites') == 1 and v.get('ascites') == 0:
        add(WARNING, 'K', 'k_refractory_ascites', 'Refractory ascites (K2) but ascites absent on examination (F7).',
            'refractory')
    if v.get('comp_variceal_bleed') == 1 and v.get('gi_bleeding') == 0:
        add(WARNING, 'F', 'gi_bleeding', 'Bleeding varices on OGD (H2) but no evidence of GI bleeding (F14).', 'gib')
    if v.get('hcc_etiology') == 1 and v.get('img_hcc') == 0:
        add(WARNING, 'G', 'img_hcc', 'History of HCC (D9) but imaging shows no HCC (G26).', 'hcc')
    for lab, history, label in (('hbsag', 'hbv', 'HBsAg positive (G18) but history of hepatitis B is No (D1).'),
                                ('hcv_ab', 'hcv', 'Hepatitis C antibody positive (G19) but history of hepatitis C is '
                                                  'No (D2).'),
                                ('hiv_test', 'hiv', 'HIV test positive (G20) but history of HIV is No (E1).')):
        if v.get(lab) == 1 and v.get(history) == 0:
            add(WARNING, 'D' if history != 'hiv' else 'E', history, label, f'{lab}_history')
    systolic, diastolic = v.get('bp_systolic'), v.get('bp_diastolic')
    if systolic is not None and diastolic is not None and diastolic >= systolic:
        add(ERROR, 'F', 'bp_diastolic', f'Diastolic pressure ({diastolic}) is not below systolic ({systolic}).', 'bp')
    total, direct = derived.bilirubin_mgdl(v), _direct_bilirubin_mgdl(v)
    if total is not None and direct is not None and direct > total * 1.02:
        add(ERROR, 'G', 'direct_bilirubin', 'Direct bilirubin is higher than total bilirubin (check the units).',
            'direct_bili')
    if v.get('sym_jaundice') and v.get('jaundice') == 0 and (total or 0) > 3:
        add(WARNING, 'F', 'jaundice', 'Jaundice absent on examination with bilirubin above 3 mg/dL.', 'jaundice')
    return out


def _direct_bilirubin_mgdl(v):
    x = _num(v.get('direct_bilirubin'))
    unit = v.get('direct_bilirubin_unit')
    if x is None or unit not in (1, 2):
        return None
    return x / 17.1 if unit == 1 else x


def all_issues(values):
    return range_issues(values) + consistency_issues(values)
