"""Every automatic data check, described once: used by the checks themselves (quality/checks.py), the Automatic
checks page (filter by category) and the "Data Checks" sheet of the data dictionary. No Django imports.

(rule id, level, category, section, rule)
level: error = impossible or contradictory; warning = unusual, verify against the source.
"Blocked" rules (impossible numbers, missing units) are refused at entry; the others, including every date check,
are saved and flagged afterwards so that a query can be raised.
"""

DATE_FLOOR = '2020-01-01'  # any study date before this is treated as a mistyped year

RULES = [
    # --- Dates --------------------------------------------------------------------------------------------------
    ('date_future', 'error', 'Dates', 'Header', 'Date of interview or admission is in the future.'),
    ('date_old', 'error', 'Dates', 'Any', f'A date is before {DATE_FLOOR}: the year is probably mistyped.'),
    ('date_start', 'warning', 'Dates', 'Header', 'Date of interview is before the study start date (STUDY_START_DATE).'),
    ('adm_missing', 'warning', 'Dates', 'Header', 'Admission date is missing (needed for length of stay and lab timing).'),
    ('adm_after_int', 'error', 'Dates', 'Header', 'Admission date is after the interview date.'),
    ('int_late', 'warning', 'Dates', 'Header', 'Interview more than 60 days after admission.'),
    ('lab_future', 'error', 'Dates', 'G', 'Laboratory sample date is in the future.'),
    ('lab_early', 'warning', 'Dates', 'G', 'Laboratory sample more than 7 days before admission.'),
    ('lab_after_death', 'error', 'Dates', 'G', 'Laboratory sample after the date of death.'),
    ('lab_after_discharge', 'warning', 'Dates', 'G', 'Laboratory sample after the date of discharge.'),
    ('out_future', 'error', 'Dates', 'L', 'Date of discharge or death is in the future.'),
    ('out_before_adm', 'error', 'Dates', 'L', 'Date of discharge or death is before the admission date.'),
    ('disch_before_int', 'warning', 'Dates', 'L', 'Discharged before the interview date (interviewed after discharge?).'),
    ('death_before_int', 'warning', 'Dates', 'L', 'Date of death is before the interview date (information from relatives?).'),
    ('los_dates', 'warning', 'Dates', 'L', 'Length of stay (L1) differs by more than 1 day from the admission and discharge/death dates.'),
    ('los_long', 'warning', 'Dates', 'L', 'More than 180 days between admission and discharge/death.'),
    # --- Ranges and units ---------------------------------------------------------------------------------------
    ('hard', 'error', 'Ranges', 'Any', 'Value outside the hard limits in the data dictionary (blocked at entry).'),
    ('check', 'warning', 'Ranges', 'Any', 'Value outside the check limits: possible but unusual, or the wrong unit.'),
    ('unit', 'error', 'Ranges', 'G', 'Laboratory value entered without its unit (blocked at entry).'),
    ('bmi', 'warning', 'Ranges', 'F', 'BMI below 12 or above 60: check weight and height.'),
    ('bp', 'error', 'Ranges', 'F', 'Diastolic pressure is not below systolic.'),
    ('direct_bili', 'error', 'Ranges', 'G', 'Direct bilirubin is higher than total bilirubin (check the units).'),
    ('dx_gt_age', 'error', 'Ranges', 'B', 'Years since diagnosis is more than the age.'),
    ('alc_gt_age', 'error', 'Ranges', 'D', 'Years of alcohol use is more than the age.'),
    # --- Consistency between answers ----------------------------------------------------------------------------
    ('hosp_id', 'error', 'Consistency', 'Header', 'MRN is missing (required).'),
    ('asterixis', 'warning', 'Consistency', 'F', 'Asterixis present but hepatic encephalopathy absent.'),
    ('ascites_img', 'warning', 'Consistency', 'G', 'Ascites on examination (F7) but not on imaging (G23).'),
    ('refractory', 'warning', 'Consistency', 'K', 'Refractory ascites (K2) but ascites absent on examination (F7).'),
    ('gib', 'warning', 'Consistency', 'F', 'Bleeding varices on OGD (H2) but no evidence of GI bleeding (F14).'),
    ('hcc', 'warning', 'Consistency', 'G', 'History of HCC (D9) but imaging shows no HCC (G26).'),
    ('hbsag_history', 'warning', 'Consistency', 'D', 'HBsAg positive (G18) but history of hepatitis B is No (D1).'),
    ('hcv_ab_history', 'warning', 'Consistency', 'D', 'Hepatitis C antibody positive (G19) but history of hepatitis C is No (D2).'),
    ('hiv_test_history', 'warning', 'Consistency', 'E', 'HIV test positive (G20) but history of HIV is No (E1).'),
    ('jaundice', 'warning', 'Consistency', 'F', 'Jaundice absent on examination with bilirubin above 3 mg/dL.'),
]

CATEGORY = {rule: category for rule, _level, category, _section, _text in RULES}
CATEGORIES = ['Dates', 'Ranges', 'Consistency']
