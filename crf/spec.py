"""The study CRF, written once.

Source: documentations/tools/questionnaire final.docx ("Clinical profile, disease severity and need for liver
transplantation among patients with decompensated chronic liver disease at Muhimbili National Hospital").
Units and reference limits: documentations/si_units_range (MNH Gastroenterology unit lab sheet and the MNH
Jeeva clinical chemistry screen).

The database tables, the entry forms, skip logic, data quality checks, exports and the Excel data dictionary are
all generated from this file. When a new CRF version arrives: edit this file and crf/decisions.py, raise VERSION,
then run  makemigrations crf && migrate && build_dictionary.

This module must not import Django: the dictionary builder uses it on its own.
"""
from dataclasses import dataclass, field as dc_field

VERSION = '0.1'
VERSION_DATE = '2026-11-08'
STUDY_TITLE = ('Clinical profile, disease severity and need for liver transplantation among patients with '
               'decompensated chronic liver disease at Muhimbili National Hospital')
CRF_SOURCE = 'questionnaire final.docx'

# --- Choice lists ------------------------------------------------------------------------------------------------
# (code, English label). Codes are proposed (the CRF prints only tick boxes): 1 = Yes, 0 = No, 9 = Unknown.
CHOICES = {
    'yesno': [(1, 'Yes'), (0, 'No')],
    'yesnounk': [(1, 'Yes'), (0, 'No'), (9, 'Unknown')],
    'presence': [(1, 'Present'), (0, 'Absent')],
    'sex': [(1, 'Male'), (2, 'Female')],
    'marital': [(1, 'Single'), (2, 'Married'), (3, 'Divorced/Separated'), (4, 'Widowed')],
    'education': [(0, 'No formal education'), (1, 'Primary'), (2, 'Secondary'), (3, 'College/University')],
    'duration_unit': [(1, 'Months'), (2, 'Years')],
    'he_grade': [(1, 'Grade I'), (2, 'Grade II'), (3, 'Grade III'), (4, 'Grade IV')],
    'bilirubin_unit': [(1, 'µmol/L'), (2, 'mg/dL')],
    'albumin_unit': [(1, 'g/L'), (2, 'g/dL')],
    'creatinine_unit': [(1, 'µmol/L'), (2, 'mg/dL')],
    'cp_ascites': [(1, 'None (1 point)'), (2, 'Mild (2 points)'), (3, 'Moderate-Severe (3 points)')],
    'outcome': [(1, 'Discharged alive'), (2, 'Died')],
    # Options of the "Tick all applicable" symptom question; each is stored as its own 0/1 column sym_<code>.
    'symptoms': [
        ('abd_distension', 'Abdominal distension'), ('jaundice', 'Jaundice'), ('hematemesis', 'Hematemesis'),
        ('melena', 'Melena'), ('confusion', 'Confusion'), ('reduced_consciousness', 'Reduced consciousness'),
        ('leg_swelling', 'Leg swelling'), ('fatigue', 'Fatigue'), ('weight_loss', 'Weight loss'),
        ('abd_pain', 'Abdominal pain'), ('pruritus', 'Pruritus'), ('fever', 'Fever'), ('other', 'Others'),
    ],
}


@dataclass
class Field:
    name: str
    label: str
    type: str                     # integer | decimal | text | date | select_one | select_multiple
    qn: str = ''                  # question number assigned in the dictionary (the CRF numbering is incomplete)
    choices: str = ''             # key in CHOICES
    group: str = ''               # sub-heading inside the section
    unit: str = ''
    dp: int = 0                   # decimal places
    hard: tuple = None            # (min, max): values outside are rejected
    check: tuple = None           # (low, high): possible but unusual, flagged "verify against source"
    ref: tuple = None             # (low, high): normal reference interval, shown as L/H
    unit_field: str = ''          # for results recorded in more than one unit: the field holding the unit
    by_unit: dict = None          # unit code -> {'unit', 'hard', 'check', 'ref'}
    default: object = None        # initial value on a new form
    relevant: list = dc_field(default_factory=list)  # all conditions must hold: (field, op, value)
    expected: bool = True         # counts toward completeness when relevant
    allow_nd: bool = False        # can be ticked "Not done / not available"
    help: str = ''
    crf_wording: str = ''         # as printed, when the dictionary changed it
    status: str = 'Ready'         # Ready | Changed from CRF | Added (not on CRF) | Code proposed
    decision: str = ''            # Decisions sheet ID
    notes: str = ''

    @property
    def columns(self):
        """Database/export columns for this question."""
        if self.type == 'select_multiple':
            return [f'{self.name}_{code}' for code, _ in CHOICES[self.choices]]
        return [self.name]


@dataclass
class Derived:
    name: str
    label: str
    section: str
    calculation: str
    range: str = ''
    interpretation: str = ''
    source: str = ''
    status: str = 'Ready'
    decision: str = ''
    unit: str = ''


@dataclass
class Section:
    code: str
    key: str
    title: str
    fields: list
    note: str = ''

    @property
    def entered(self):
        return list(self.fields)


def YN(name, label, qn, choices='yesno', **kw):
    return Field(name, label, 'select_one', qn=qn, choices=choices, **kw)


LAB = 'Laboratory results'
RAD = 'Radiological findings'

# Header of the questionnaire: kept on the participant record itself (not a section table).
HEADER = [
    Field('study_id', 'Study ID', 'text', qn='H1', status='Changed from CRF', decision='D01',
          notes='Generated by the system when the participant is registered (e.g. CLD-0001).'),
    Field('hospital_id', 'Hospital ID (MNH registration number)', 'text', qn='H1a', status='Added (not on CRF)',
          decision='D35', notes='Required before a participant can be registered; unique (the same patient cannot be '
          'registered twice). Identifying: shown only to Data Clerks, Data Managers and Admins; only in identifiable '
          'exports.'),
    Field('interview_date', 'Date of interview', 'date', qn='H2', notes='Cannot be in the future or before the study start date.'),
    Field('interviewer', 'Interviewer', 'text', qn='H3', status='Changed from CRF', decision='D28',
          crf_wording='Interviewer Initials', notes='Recorded automatically from the logged-in account.'),
    Field('phone_number', 'Patient phone number', 'text', qn='H4', decision='D27',
          notes='Identifying. Shown only to Data Clerks, Data Managers and Admins; left out of de-identified exports.'),
    Field('admission_date', 'Date of admission (current admission)', 'date', qn='H5', status='Added (not on CRF)',
          decision='D21', notes='Needed to check length of stay and the timing of laboratory results.'),
]

SECTIONS = [
    Section('A', 'sociodemographic', 'Sociodemographic characteristics', [
        Field('age_years', 'Age (years)', 'integer', qn='A1', unit='years', hard=(0, 120), check=(18, 100), decision='D33',
              notes='Below 18 is flagged until the eligibility criteria are confirmed.'),
        Field('sex', 'Sex', 'select_one', qn='A2', choices='sex', status='Code proposed'),
        Field('marital_status', 'Marital status', 'select_one', qn='A3', choices='marital', status='Code proposed'),
        Field('education', 'Level of education', 'select_one', qn='A4', choices='education', status='Code proposed'),
        Field('occupation', 'Occupation', 'text', qn='A5', decision='D18'),
        Field('residence', 'Place of residence', 'text', qn='A6', decision='D18'),
        YN('health_insurance', 'Health insurance', 'A7'),
        Field('insurance_specify', 'If yes, specify insurance', 'text', qn='A7a', relevant=[('health_insurance', '==', 1)],
              decision='D19'),
    ]),
    Section('B', 'liver_history', 'History of chronic liver disease', [
        YN('ever_dx_cld', 'Have you ever been diagnosed with chronic liver disease?', 'B1', decision='D06'),
        Field('dx_duration', 'Duration since diagnosis', 'integer', qn='B2', hard=(0, 100),
              relevant=[('ever_dx_cld', '==', 1)], status='Changed from CRF', decision='D07',
              crf_wording='Duration since diagnosis: ______ (free text)'),
        Field('dx_duration_unit', 'Duration unit', 'select_one', qn='B2a', choices='duration_unit',
              relevant=[('ever_dx_cld', '==', 1)], status='Added (not on CRF)', decision='D07'),
        YN('prev_admission', 'Previous hospital admission due to liver disease', 'B3'),
        Field('admissions_past_year', 'Number of admissions in the past year', 'integer', qn='B4', hard=(0, 50),
              check=(0, 12), relevant=[('prev_admission', '==', 1)]),
    ]),
    Section('C', 'presentation', 'Presenting clinical characteristics', [
        Field('sym', 'What symptoms brought you to hospital? (tick all applicable)', 'select_multiple', qn='C1',
              choices='symptoms', notes='One 0/1 column per symptom (sym_<code>). At least one must be ticked.'),
        Field('sym_other_specify', 'Other symptoms, specify', 'text', qn='C1a', relevant=[('sym_other', '==', True)]),
        Field('symptom_duration_days', 'Duration of current symptoms', 'integer', qn='C2', unit='days', hard=(0, 3650),
              check=(0, 365)),
    ]),
    Section('D', 'examination', 'Physical examination findings', [
        Field('weight_kg', 'Weight', 'decimal', qn='D1', group='Anthropometric measurements', unit='kg', dp=1,
              hard=(20, 250), check=(30, 150), allow_nd=True),
        Field('height_cm', 'Height', 'decimal', qn='D2', group='Anthropometric measurements', unit='cm', dp=1,
              hard=(100, 230), check=(135, 200), allow_nd=True),
        Field('muac_cm', 'MUAC', 'decimal', qn='D4', group='Anthropometric measurements', unit='cm', dp=1,
              hard=(8, 60), check=(15, 45), allow_nd=True,
              notes='D3 BMI is calculated from weight and height (Derived Scores sheet), not entered.'),
        YN('jaundice', 'Jaundice', 'D5', choices='presence', group='Clinical signs'),
        YN('fever', 'Fever', 'D6', choices='presence', group='Clinical signs'),
        Field('temperature_c', 'If present: temperature', 'decimal', qn='D6a', group='Clinical signs', unit='°C', dp=1,
              hard=(34, 43), check=(37.5, 42), relevant=[('fever', '==', 1)], status='Changed from CRF',
              decision='D08', crf_wording='If present: ______degree'),
        YN('ascites', 'Ascites', 'D7', choices='presence', group='Clinical signs'),
        YN('peripheral_edema', 'Peripheral edema', 'D8', choices='presence', group='Clinical signs'),
        YN('hepatic_enceph', 'Hepatic encephalopathy', 'D9', choices='presence', group='Clinical signs'),
        Field('he_grade', 'If present: grade (West Haven)', 'select_one', qn='D9a', choices='he_grade',
              group='Clinical signs', relevant=[('hepatic_enceph', '==', 1)], decision='D34'),
        YN('splenomegaly', 'Splenomegaly', 'D10', choices='presence', group='Clinical signs'),
        YN('hepatomegaly', 'Hepatomegaly', 'D11', choices='presence', group='Clinical signs'),
        YN('muscle_wasting', 'Muscle wasting', 'D12', choices='presence', group='Clinical signs'),
        YN('asterixis', 'Asterixis', 'D13', choices='presence', group='Clinical signs'),
        YN('gi_bleeding', 'Evidence of gastrointestinal bleeding', 'D14', group='Clinical signs'),
    ]),
    Section('E', 'etiology', 'Etiology of chronic liver disease', [
        YN('hbv', 'Hepatitis B infection (HBsAg positive)', 'E1', choices='yesnounk'),
        YN('hcv', 'Hepatitis C infection', 'E2', choices='yesnounk'),
        YN('hdv', 'Hepatitis D infection', 'E3', choices='yesnounk', decision='D15'),
        YN('schistosomiasis', 'History of schistosomiasis', 'E4', choices='yesnounk'),
        YN('alcohol', 'Alcohol use history', 'E5', group='Alcohol'),
        Field('alcohol_units_day', 'Amount in units per day', 'decimal', qn='E5a', group='Alcohol', unit='units/day', dp=1,
              hard=(0, 100), check=(0, 30), relevant=[('alcohol', '==', 1)], decision='D14'),
        Field('alcohol_units_week', 'Amount in units per week', 'decimal', qn='E5b', group='Alcohol', unit='units/week',
              dp=1, hard=(0, 700), check=(0, 200), relevant=[('alcohol', '==', 1)], decision='D14'),
        Field('alcohol_years', 'Years of alcohol use', 'integer', qn='E5c', group='Alcohol', unit='years', hard=(0, 90),
              relevant=[('alcohol', '==', 1)]),
        YN('alcohol_recent_3m', 'Recent alcohol use within 3 months', 'E5d', group='Alcohol',
           relevant=[('alcohol', '==', 1)], status='Changed from CRF', decision='D14',
           crf_wording='Recent alcohol use within 3 months: ______'),
        YN('masld', 'Metabolic-associated steatotic liver disease (MASLD)', 'E6', group='Other causes'),
        YN('autoimmune_hepatitis', 'Autoimmune hepatitis', 'E7', group='Other causes'),
        YN('pbc', 'Primary biliary cholangitis', 'E8', group='Other causes'),
        YN('psc', 'Primary sclerosing cholangitis', 'E9', group='Other causes'),
        YN('wilson', 'Wilson disease', 'E10', group='Other causes'),
        YN('hemochromatosis', 'Hemochromatosis', 'E11', group='Other causes'),
        YN('dili', 'Drug-induced liver disease', 'E12', group='Other causes'),
        YN('hcc_etiology', 'Hepatocellular carcinoma', 'E13', group='Other causes', decision='D11'),
        Field('other_cause_specify', 'Other cause, specify', 'text', qn='E14', group='Other causes', expected=False),
        Field('final_etiology', 'Final etiology assigned by treating physician', 'text', qn='E15',
              group='Final etiology', decision='D16', notes='Numbered 39 on the CRF.'),
    ]),
    Section('F', 'comorbidities', 'Comorbidities', [
        YN('hiv', 'HIV infection', 'F1'),
        YN('diabetes', 'Diabetes mellitus', 'F2'),
        YN('hypertension', 'Hypertension', 'F3'),
        YN('ckd', 'Chronic kidney disease', 'F4'),
        YN('heart_disease', 'Heart disease', 'F5'),
        Field('other_comorbidity_specify', 'Other comorbidity, specify', 'text', qn='F6', expected=False),
    ]),
    Section('G', 'investigations', 'Investigations', [
        Field('lab_sample_date', 'Date of the laboratory sample', 'date', qn='G0', group=LAB, allow_nd=True,
              status='Added (not on CRF)', decision='D32',
              notes='Which result to record (first after admission is proposed) is decision D32.'),
        Field('hb', 'Hemoglobin', 'decimal', qn='G1', group=LAB, unit='g/dL', dp=1, hard=(1, 25), check=(4, 20),
              ref=(12.0, 17.5), allow_nd=True, notes='Reference interval proposed (not on the MNH sheet); confirm with MNH lab.'),
        Field('platelets', 'Platelet count', 'integer', qn='G2', group=LAB, unit='×10⁹/L', hard=(1, 2000),
              check=(10, 1000), ref=(150, 400), allow_nd=True, notes='Reference interval proposed; confirm with MNH lab.'),
        Field('wbc', 'WBC', 'decimal', qn='G3', group=LAB, unit='×10⁹/L', dp=1, hard=(0.1, 300), check=(1, 50),
              ref=(4.0, 11.0), allow_nd=True, status='Changed from CRF', decision='D23', crf_wording='WBC): ______',
              notes='Unit missing on the CRF; MNH sheet uses K/µL, which is the same as ×10⁹/L.'),
        Field('bilirubin', 'Serum total bilirubin', 'decimal', qn='G4', group=LAB, dp=1, unit_field='bilirubin_unit',
              allow_nd=True, decision='D03', by_unit={
                  1: {'unit': 'µmol/L', 'hard': (1, 1200), 'check': (3, 600), 'ref': (3.4, 20.5)},
                  2: {'unit': 'mg/dL', 'hard': (0.1, 70), 'check': (0.2, 35), 'ref': (0.2, 1.2)}},
              notes='Recorded in the unit on the result slip; the system converts to mg/dL for scores (÷17.1).'),
        Field('bilirubin_unit', 'Bilirubin unit', 'select_one', qn='G4a', group=LAB, choices='bilirubin_unit', default=1,
              relevant=[('bilirubin', 'filled', None)], status='Added (not on CRF)', decision='D03'),
        Field('albumin', 'Serum albumin', 'decimal', qn='G5', group=LAB, dp=1, unit_field='albumin_unit',
              allow_nd=True, status='Changed from CRF', decision='D03', crf_wording='Serum albumin (g/dL)', by_unit={
                  1: {'unit': 'g/L', 'hard': (5, 70), 'check': (10, 55), 'ref': (35, 50)},
                  2: {'unit': 'g/dL', 'hard': (0.5, 7), 'check': (1.0, 5.5), 'ref': (3.5, 5.0)}},
              notes='MNH lab sheet reports g/L; the CRF asks g/dL. Converted to g/dL for Child-Pugh (÷10).'),
        Field('albumin_unit', 'Albumin unit', 'select_one', qn='G5a', group=LAB, choices='albumin_unit', default=1,
              relevant=[('albumin', 'filled', None)], status='Added (not on CRF)', decision='D03'),
        Field('inr', 'INR', 'decimal', qn='G6', group=LAB, dp=2, hard=(0.5, 20), check=(0.8, 8), ref=(0.8, 1.2),
              allow_nd=True, notes='Reference interval proposed; confirm with MNH lab.'),
        Field('creatinine', 'Serum creatinine', 'decimal', qn='G7', group=LAB, dp=1, unit_field='creatinine_unit',
              allow_nd=True, status='Changed from CRF', decision='D03', crf_wording='Serum creatinine (mg/dL)', by_unit={
                  1: {'unit': 'µmol/L', 'hard': (10, 2500), 'check': (25, 1000), 'ref': (63.6, 110.5)},
                  2: {'unit': 'mg/dL', 'hard': (0.1, 30), 'check': (0.3, 12), 'ref': (0.72, 1.25)}},
              notes='MNH Jeeva reports µmol/L (63.6-110.5); the CRF asks mg/dL. Converted to mg/dL for MELD-Na (÷88.4).'),
        Field('creatinine_unit', 'Creatinine unit', 'select_one', qn='G7a', group=LAB, choices='creatinine_unit', default=1,
              relevant=[('creatinine', 'filled', None)], status='Added (not on CRF)', decision='D03'),
        Field('sodium', 'Serum sodium', 'integer', qn='G8', group=LAB, unit='mmol/L', hard=(90, 190), check=(115, 160),
              ref=(135, 145), allow_nd=True, notes='MNH sheet labels mEq/L, which equals mmol/L for sodium.'),
        Field('alt', 'ALT', 'decimal', qn='G9', group=LAB, unit='U/L', dp=1, hard=(0, 20000), check=(1, 2000),
              ref=(0, 55), allow_nd=True, notes='Reference interval from MNH Jeeva.'),
        Field('ast', 'AST', 'decimal', qn='G10', group=LAB, unit='U/L', dp=1, hard=(0, 20000), check=(1, 2000),
              ref=(0, 48.1), allow_nd=True, notes='Reference interval from MNH Jeeva.'),
        Field('ggt', 'GGT', 'decimal', qn='G11', group=LAB, unit='U/L', dp=1, hard=(0, 10000), check=(1, 2000),
              ref=(9.3, 120.8), allow_nd=True, notes='Reference interval from MNH Jeeva.'),
        Field('alp', 'ALP', 'decimal', qn='G12', group=LAB, unit='U/L', dp=1, hard=(0, 10000), check=(10, 3000),
              ref=(45.4, 170), allow_nd=True, notes='Reference interval from MNH Jeeva.'),
        YN('us_cirrhotic', 'Cirrhotic liver on ultrasound', 'G13', group=RAD, allow_nd=True),
        YN('us_ascites', 'Ascites on ultrasound', 'G14', group=RAD, allow_nd=True),
        YN('us_splenomegaly', 'Splenomegaly (ultrasound)', 'G15', group=RAD, allow_nd=True),
        YN('us_pvt', 'Portal vein thrombosis (imaging)', 'G16', group=RAD, allow_nd=True, decision='D12'),
        YN('us_hcc', 'Hepatocellular carcinoma (imaging)', 'G17', group=RAD, allow_nd=True, decision='D11'),
    ]),
    Section('H', 'complications', 'Complications of cirrhosis', [
        YN('comp_ascites', 'Ascites', 'H1', decision='D10'),
        YN('comp_sbp', 'Spontaneous bacterial peritonitis', 'H2', decision='D30'),
        YN('comp_he', 'Hepatic encephalopathy', 'H3', decision='D09'),
        YN('comp_variceal_bleed', 'Variceal bleeding', 'H4'),
        YN('comp_hrs', 'Hepatorenal syndrome', 'H5', decision='D30'),
        YN('comp_pvt', 'Portal vein thrombosis', 'H6', decision='D12'),
        YN('comp_hcc', 'Hepatocellular carcinoma', 'H7', decision='D11'),
    ]),
    Section('I', 'child_pugh', 'Child-Pugh score', [
        Field('cp_ascites', 'Ascites (Child-Pugh grade)', 'select_one', qn='I4', choices='cp_ascites', decision='D04',
              notes='I1 bilirubin, I2 albumin, I3 INR and I5 encephalopathy points are calculated (Derived Scores).'),
    ], note='Bilirubin, albumin, INR and encephalopathy points are calculated from Sections D and G.'),
    Section('J', 'meld', 'MELD-Na score', [],
            note='Calculated from bilirubin, INR, creatinine and sodium in Section G. Nothing to enter.'),
    Section('K', 'transplant', 'Liver transplant eligibility assessment', [
        YN('k_recurrent_variceal', 'Recurrent variceal bleeding', 'K3', group='Indications'),
        YN('k_refractory_ascites', 'Refractory ascites', 'K4', group='Indications'),
        YN('k_recurrent_he', 'Recurrent hepatic encephalopathy', 'K5', group='Indications'),
        YN('k_hcc_milan', 'Hepatocellular carcinoma within transplant criteria (Milan criteria)', 'K6',
           group='Indications', decision='D20', crf_wording='... (Millan Criteria)'),
        YN('k_meets_criteria', 'Does the patient meet accepted criteria for liver transplantation?', 'K7',
           group='Assessment', decision='D20',
           notes='K1 Child-Pugh class C and K2 MELD-Na >= 15 are calculated (Derived Scores).'),
    ]),
    Section('L', 'outcome', 'Outcome of current admission', [
        Field('los_days', 'Length of hospital stay', 'integer', qn='L1', unit='days', hard=(0, 365), check=(0, 90)),
        Field('outcome', 'Outcome', 'select_one', qn='L2', choices='outcome', status='Code proposed'),
        Field('outcome_date', 'Date of discharge or death', 'date', qn='L3', status='Added (not on CRF)', decision='D21'),
    ]),
]

DERIVED = [
    Derived('bmi', 'Body mass index', 'D', 'weight_kg / (height_cm / 100)^2, 1 decimal', '10-70', unit='kg/m²',
            interpretation='<18.5 underweight, 18.5-24.9 normal, 25-29.9 overweight, >=30 obese',
            source='CRF D3 (BMI line)', status='Derived (CRF asks to write it)'),
    Derived('bilirubin_mgdl', 'Bilirubin in mg/dL', 'G', 'bilirubin if unit mg/dL; bilirubin / 17.1 if µmol/L',
            unit='mg/dL', source='Unit conversion', decision='D03'),
    Derived('albumin_gdl', 'Albumin in g/dL', 'G', 'albumin if unit g/dL; albumin / 10 if g/L', unit='g/dL',
            source='Unit conversion', decision='D03'),
    Derived('creatinine_mgdl', 'Creatinine in mg/dL', 'G', 'creatinine if unit mg/dL; creatinine / 88.4 if µmol/L',
            unit='mg/dL', source='Unit conversion', decision='D03'),
    Derived('apri', 'AST to platelet ratio index (APRI)', 'G', '(AST / 48.1) / platelets x 100; 48.1 = MNH AST upper limit',
            interpretation='>1.0 suggests cirrhosis', source='MNH Gastro lab sheet lists APRI', status='Proposed',
            decision='D31'),
    Derived('cp_bili_pts', 'Child-Pugh bilirubin points (I1)', 'I', 'bilirubin_mgdl <2 = 1, 2-3 = 2, >3 = 3', '1-3',
            source='CRF I1', status='Derived (CRF asks to tick)', decision='D04'),
    Derived('cp_alb_pts', 'Child-Pugh albumin points (I2)', 'I', 'albumin_gdl >3.5 = 1, 2.8-3.5 = 2, <2.8 = 3', '1-3',
            source='CRF I2', status='Derived (CRF asks to tick)', decision='D04'),
    Derived('cp_inr_pts', 'Child-Pugh INR points (I3)', 'I', 'inr <1.7 = 1, 1.7-2.3 = 2, >2.3 = 3', '1-3',
            source='CRF I3', status='Derived (CRF asks to tick)', decision='D04'),
    Derived('cp_ascites_pts', 'Child-Pugh ascites points (I4)', 'I', 'cp_ascites (entered)', '1-3', source='CRF I4'),
    Derived('cp_enceph_pts', 'Child-Pugh encephalopathy points (I5)', 'I',
            'hepatic_enceph Absent = 1; he_grade I-II = 2; III-IV = 3', '1-3', source='CRF I5',
            status='Derived (CRF asks to tick)', decision='D04'),
    Derived('cp_score', 'Child-Pugh score', 'I', 'Sum of the five points; blank if any is missing', '5-15',
            source='CRF Section I'),
    Derived('cp_class', 'Child-Pugh class', 'I', '5-6 = A, 7-9 = B, 10-15 = C', 'A-C', source='CRF Section I'),
    Derived('meld', 'MELD', 'J', '10 x (0.957 ln(Cr) + 0.378 ln(Bili) + 1.120 ln(INR)) + 6.43; Cr, Bili and INR '
            'below 1.0 set to 1.0, Cr above 4.0 set to 4.0 (mg/dL)', '6-40', source='CRF Section J',
            status='Derived (CRF lists inputs only)', decision='D05'),
    Derived('meld_na', 'MELD-Na score', 'J', 'If MELD > 11: MELD + 1.32 x (137 - Na) - 0.033 x MELD x (137 - Na), '
            'with Na limited to 125-137; rounded; maximum 40', '6-40', source='CRF Section J (OPTN 2016 formula)',
            status='Derived (CRF lists inputs only)', decision='D05'),
    Derived('k_child_c', 'Child-Pugh class C (K1)', 'K', '1 if cp_class = C', '0-1', source='CRF K1',
            status='Derived (CRF asks to tick)', decision='D20'),
    Derived('k_meld15', 'MELD-Na >= 15 (K2)', 'K', '1 if meld_na >= 15', '0-1', source='CRF K2',
            status='Derived (CRF asks to tick)', decision='D20'),
    Derived('los_from_dates', 'Length of stay from dates', 'L', 'outcome_date - admission_date in days', '0-365',
            source='Check on L1', status='Added (not on CRF)', decision='D21'),
]


# --- Helpers used by Django and the dictionary builder ----------------------------------------------------------
SECTION_BY_CODE = {s.code: s for s in SECTIONS}


def all_fields():
    for section in SECTIONS:
        for f in section.fields:
            yield section, f


FIELD_BY_NAME = {f.name: (s, f) for s, f in all_fields()}


def choice_label(list_name, code):
    for c, label in CHOICES.get(list_name, []):
        if c == code:
            return label
    return code


def relevance_text(f):
    """ODK-style expression, for the dictionary."""
    parts = []
    for name, op, value in f.relevant:
        if op == 'filled':
            parts.append(f"${{{name}}} != ''")
        elif op == '==' and value is True:
            parts.append(f"${{{name}}} = 1")
        elif op == 'in':
            parts.append('(' + ' or '.join(f"${{{name}}} = {v}" for v in value) + ')')
        else:
            parts.append(f"${{{name}}} {'=' if op == '==' else op} {value}")
    return ' and '.join(parts)


def is_relevant(f, values):
    """True when every condition of f.relevant holds for `values` (column -> value)."""
    for name, op, expected in f.relevant:
        actual = values.get(name)
        if op == 'filled':
            ok = actual not in (None, '')
        elif op == '==':
            ok = (bool(actual) is True) if expected is True else actual == expected
        elif op == '!=':
            ok = actual != expected
        elif op == 'in':
            ok = actual in expected
        else:
            raise ValueError(f'Unknown operator {op}')
        if not ok:
            return False
    return True


def limits(f, values):
    """(unit, hard, check, ref) for f, taking the chosen unit into account."""
    if f.by_unit:
        unit_code = values.get(f.unit_field)
        cfg = f.by_unit.get(unit_code)
        if not cfg:
            return '', None, None, None
        return cfg['unit'], cfg.get('hard'), cfg.get('check'), cfg.get('ref')
    return f.unit, f.hard, f.check, f.ref
