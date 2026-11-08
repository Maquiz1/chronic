"""Calculated values (Derived Scores sheet of the data dictionary). Each returns None when an input is missing."""
import math
from decimal import Decimal


def _f(value):
    if value in (None, ''):
        return None
    return float(value) if isinstance(value, (int, float, Decimal)) else None


def bmi(v):
    w, h = _f(v.get('weight_kg')), _f(v.get('height_cm'))
    if not w or not h:
        return None
    return round(w / (h / 100) ** 2, 1)


def bilirubin_mgdl(v):
    x = _f(v.get('bilirubin'))
    unit = v.get('bilirubin_unit')
    if x is None or unit not in (1, 2):
        return None
    return round(x / 17.1, 2) if unit == 1 else x


def albumin_gdl(v):
    x = _f(v.get('albumin'))
    unit = v.get('albumin_unit')
    if x is None or unit not in (1, 2):
        return None
    return round(x / 10, 2) if unit == 1 else x


def creatinine_mgdl(v):
    x = _f(v.get('creatinine'))
    unit = v.get('creatinine_unit')
    if x is None or unit not in (1, 2):
        return None
    return round(x / 88.4, 2) if unit == 1 else x


def apri(v):
    ast, plt = _f(v.get('ast')), _f(v.get('platelets'))
    if ast is None or not plt:
        return None
    return round((ast / 48.1) / plt * 100, 2)


def cp_bili_pts(v):
    b = bilirubin_mgdl(v)
    if b is None:
        return None
    return 1 if b < 2 else (2 if b <= 3 else 3)


def cp_alb_pts(v):
    a = albumin_gdl(v)
    if a is None:
        return None
    return 1 if a > 3.5 else (2 if a >= 2.8 else 3)


def cp_inr_pts(v):
    i = _f(v.get('inr'))
    if i is None:
        return None
    return 1 if i < 1.7 else (2 if i <= 2.3 else 3)


def cp_enceph_pts(v):
    he, grade = v.get('hepatic_enceph'), v.get('he_grade')
    if he == 0:
        return 1
    if he == 1 and grade in (1, 2):
        return 2
    if he == 1 and grade in (3, 4):
        return 3
    return None


def cp_score(v):
    parts = [cp_bili_pts(v), cp_alb_pts(v), cp_inr_pts(v), v.get('cp_ascites'), cp_enceph_pts(v)]
    if any(p is None for p in parts):
        return None
    return sum(parts)


def cp_class(v):
    s = cp_score(v)
    if s is None:
        return None
    return 'A' if s <= 6 else ('B' if s <= 9 else 'C')


def meld(v):
    cr, bili, inr = creatinine_mgdl(v), bilirubin_mgdl(v), _f(v.get('inr'))
    if None in (cr, bili, inr):
        return None
    cr = min(max(cr, 1.0), 4.0)
    bili, inr = max(bili, 1.0), max(inr, 1.0)
    return round(10 * (0.957 * math.log(cr) + 0.378 * math.log(bili) + 1.120 * math.log(inr)) + 6.43, 1)


def meld_na(v):
    m, na = meld(v), _f(v.get('sodium'))
    if m is None or na is None:
        return None
    if m > 11:
        na = min(max(na, 125), 137)
        m = m + 1.32 * (137 - na) - 0.033 * m * (137 - na)
    return min(int(round(m)), 40)


def k_child_c(v):
    c = cp_class(v)
    return None if c is None else int(c == 'C')


def k_meld15(v):
    m = meld_na(v)
    return None if m is None else int(m >= 15)


def los_from_dates(v):
    a, b = v.get('admission_date'), v.get('outcome_date')
    if not a or not b:
        return None
    return (b - a).days


CALCULATORS = {
    'bmi': bmi, 'bilirubin_mgdl': bilirubin_mgdl, 'albumin_gdl': albumin_gdl, 'creatinine_mgdl': creatinine_mgdl,
    'apri': apri, 'cp_bili_pts': cp_bili_pts, 'cp_alb_pts': cp_alb_pts, 'cp_inr_pts': cp_inr_pts,
    'cp_ascites_pts': lambda v: v.get('cp_ascites'), 'cp_enceph_pts': cp_enceph_pts, 'cp_score': cp_score,
    'cp_class': cp_class, 'meld': meld, 'meld_na': meld_na, 'k_child_c': k_child_c, 'k_meld15': k_meld15,
    'los_from_dates': los_from_dates,
}


def compute_all(values):
    return {name: fn(values) for name, fn in CALCULATORS.items()}
