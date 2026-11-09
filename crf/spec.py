"""The study CRF, written once.

Source: documentations/tools/questionnaire final_v0.2.docx (v0.1 was questionnaire final.docx) ("Clinical profile, disease severity and need for liver
transplantation among patients with decompensated chronic liver disease at Muhimbili National Hospital").
Units and reference limits: documentations/si_units_range (units1: MNH Gastroenterology unit lab sheet;
units2-4: MNH Jeeva clinical chemistry screens; units5-6: MNH Jeeva full blood count screens).

The database tables, the entry forms, skip logic, data quality checks, exports and the Excel data dictionary are
all generated from this file. When a new CRF version arrives: edit this file and crf/decisions.py, raise VERSION,
then run  makemigrations crf && migrate && build_dictionary.

This module must not import Django: the dictionary builder uses it on its own.
"""
from dataclasses import dataclass, field as dc_field

VERSION = '0.3'
VERSION_DATE = '2026-11-09'
STUDY_TITLE = ('Clinical profile, disease severity and need for liver transplantation among patients with '
               'decompensated chronic liver disease at Muhimbili National Hospital')
CRF_SOURCE = 'questionnaire final_v0.2.docx'

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
    'he_grade': [(0, 'Grade 0'), (1, 'Grade I'), (2, 'Grade II'), (3, 'Grade III'), (4, 'Grade IV')],
    'ascites_grade': [(1, 'Moderate'), (2, 'Severe')],
    'posneg': [(1, 'Positive'), (0, 'Negative')],
    # "Which radiological investigation is available?" (two tick boxes): one 0/1 column each, img_modality_<code>.
    'imaging': [('us', 'Abdominal ultrasound'), ('ct', 'Abdominal CT scan')],
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
    relevant: list = dc_field(default_factory=list)  # all must hold: (field, op, value); op ==, !=, in, filled, any
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
SERO = 'Serology'
RAD = 'Radiological findings'
HCC = 'Hepatocellular carcinoma on imaging'
IMAGING_DONE = [('img_modality', 'any', None)]  # imaging questions apply once a modality is ticked

# Header of the questionnaire: kept on the participant record itself (not a section table).
HEADER = [
    Field('study_id', 'Study ID', 'text', qn='H1', status='Changed from CRF', decision='D01',
          notes='Generated by the system when the participant is registered (e.g. CLD-0001).'),
    Field('hospital_id', 'MRN (MNH medical record number)', 'text', qn='H1a', status='Added (not on CRF)',
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
    Section('D', 'etiology', 'Etiology of chronic liver disease', [
        YN('hbv', 'History of hepatitis B infection', 'D1', choices='yesnounk', group='Viral hepatitis'),
        Field('hbv_duration', 'If yes, for how long?', 'integer', qn='D1a', group='Viral hepatitis', hard=(0, 100),
              relevant=[('hbv', '==', 1)], crf_wording='Months ...... Years ......',
              notes='Number plus unit, as for B2 (D07): write 18 months or 2 years.'),
        Field('hbv_duration_unit', 'Duration unit', 'select_one', qn='D1b', group='Viral hepatitis',
              choices='duration_unit', relevant=[('hbv', '==', 1)], status='Code proposed'),
        YN('hbv_treatment', 'On treatment (hepatitis B)', 'D1c', group='Viral hepatitis', relevant=[('hbv', '==', 1)]),
        YN('hcv', 'History of hepatitis C infection', 'D2', choices='yesnounk', group='Viral hepatitis'),
        Field('hcv_duration', 'If yes, for how long?', 'integer', qn='D2a', group='Viral hepatitis', hard=(0, 100),
              relevant=[('hcv', '==', 1)], crf_wording='Months ...... Years ......'),
        Field('hcv_duration_unit', 'Duration unit', 'select_one', qn='D2b', group='Viral hepatitis',
              choices='duration_unit', relevant=[('hcv', '==', 1)], status='Code proposed'),
        YN('hcv_treatment', 'On treatment (hepatitis C)', 'D2c', group='Viral hepatitis', relevant=[('hcv', '==', 1)]),
        YN('hdv', 'History of hepatitis D infection', 'D3', choices='yesnounk', group='Viral hepatitis'),
        YN('schistosomiasis', 'History of schistosomiasis', 'D4', choices='yesnounk', group='Other causes'),
        YN('alcohol', 'Alcohol use history', 'D5', group='Alcohol'),
        Field('alcohol_units_day', 'Amount in units per day', 'decimal', qn='D5a', group='Alcohol', unit='units/day', dp=1,
              hard=(0, 100), check=(0, 30), relevant=[('alcohol', '==', 1)], decision='D14'),
        Field('alcohol_days_week', 'Number of days drinking alcohol per week', 'integer', qn='D5b', group='Alcohol',
              unit='days/week', hard=(0, 7), relevant=[('alcohol', '==', 1)]),
        Field('alcohol_years', 'Years of alcohol use', 'integer', qn='D5c', group='Alcohol', unit='years', hard=(0, 90),
              relevant=[('alcohol', '==', 1)]),
        YN('alcohol_recent_3m', 'Recent alcohol use within 3 months', 'D5d', group='Alcohol',
           relevant=[('alcohol', '==', 1)], status='Changed from CRF', decision='D14',
           crf_wording='Recent alcohol use within 3 months: ______'),
        YN('masld', 'Metabolic-associated steatotic liver disease (MASLD)', 'D6', group='Other causes'),
        YN('autoimmune_hepatitis', 'History of autoimmune hepatitis', 'D7', group='Other causes'),
        YN('dili', 'History of drug-induced liver disease', 'D8', group='Other causes'),
        YN('hcc_etiology', 'History of hepatocellular carcinoma', 'D9', group='Other causes', decision='D11'),
        YN('other_cause', 'Any other cause', 'D10', group='Other causes', status='Added (not on CRF)', decision='D42'),
        Field('other_cause_specify', 'If yes, specify', 'text', qn='D10a', group='Other causes',
              relevant=[('other_cause', '==', 1)], decision='D42'),
        Field('final_etiology', 'Final etiology assigned by treating physician', 'text', qn='D11',
              group='Final etiology', decision='D16'),
    ]),
    Section('E', 'comorbidities', 'Comorbidities', [
        YN('hiv', 'History of HIV infection', 'E1'),
        YN('diabetes', 'History of diabetes mellitus', 'E2'),
        YN('hypertension', 'History of hypertension', 'E3'),
        YN('ckd', 'History of chronic kidney disease', 'E4'),
        YN('heart_disease', 'History of heart disease', 'E5'),
        YN('other_comorbidity', 'Any other comorbidity', 'E6', status='Added (not on CRF)', decision='D42'),
        Field('other_comorbidity_specify', 'If yes, specify', 'text', qn='E6a',
              relevant=[('other_comorbidity', '==', 1)], decision='D42'),
    ]),
    Section('F', 'examination', 'Physical examination findings', [
        Field('weight_kg', 'Weight', 'decimal', qn='F1', group='Anthropometric measurements', unit='kg', dp=1,
              hard=(20, 250), check=(30, 150), allow_nd=True),
        Field('height_cm', 'Height', 'decimal', qn='F2', group='Anthropometric measurements', unit='cm', dp=1,
              hard=(100, 230), check=(135, 200), allow_nd=True),
        Field('muac_cm', 'MUAC', 'decimal', qn='F3', group='Anthropometric measurements', unit='cm', dp=1,
              hard=(8, 60), check=(15, 45), allow_nd=True,
              notes='BMI is calculated from weight and height (Derived Scores sheet).'),
        Field('bp_systolic', 'Blood pressure: systolic', 'integer', qn='F4a', group='Blood pressure', unit='mmHg',
              hard=(50, 260), check=(80, 200), allow_nd=True, decision='D38'),
        Field('bp_diastolic', 'Blood pressure: diastolic', 'integer', qn='F4b', group='Blood pressure', unit='mmHg',
              hard=(20, 160), check=(40, 120), allow_nd=True, decision='D38'),
        YN('jaundice', 'Jaundice', 'F5', choices='presence', group='Clinical signs'),
        YN('fever', 'Fever', 'F6', choices='presence', group='Clinical signs'),
        Field('temperature_c', 'If present: temperature', 'decimal', qn='F6a', group='Clinical signs', unit='°C', dp=1,
              hard=(34, 43), check=(37.5, 42), relevant=[('fever', '==', 1)], status='Changed from CRF',
              decision='D08', crf_wording='If present: ______degree'),
        YN('ascites', 'Ascites', 'F7', choices='presence', group='Clinical signs'),
        Field('ascites_grade', 'If present: grade', 'select_one', qn='F7a', choices='ascites_grade',
              group='Clinical signs', relevant=[('ascites', '==', 1)], status='Code proposed', decision='D36',
              notes='Used for the Child-Pugh ascites points (D36).'),
        YN('peripheral_edema', 'Peripheral edema', 'F8', choices='presence', group='Clinical signs'),
        YN('hepatic_enceph', 'Hepatic encephalopathy', 'F9', choices='presence', group='Clinical signs'),
        Field('he_grade', 'If present: grade (West Haven)', 'select_one', qn='F9a', choices='he_grade',
              group='Clinical signs', relevant=[('hepatic_enceph', '==', 1)], decision='D39'),
        YN('splenomegaly', 'Splenomegaly', 'F10', choices='presence', group='Clinical signs'),
        YN('hepatomegaly', 'Hepatomegaly', 'F11', choices='presence', group='Clinical signs'),
        YN('muscle_wasting', 'Muscle wasting', 'F12', choices='presence', group='Clinical signs'),
        YN('asterixis', 'Asterixis', 'F13', choices='presence', group='Clinical signs'),
        YN('gi_bleeding', 'Evidence of gastrointestinal bleeding', 'F14', group='Clinical signs'),
    ]),
    Section('G', 'investigations', 'Investigations', [
        Field('lab_sample_date', 'Date of the laboratory sample', 'date', qn='G0', group=LAB, allow_nd=True,
              status='Added (not on CRF)', decision='D32',
              notes='Which result to record (first after admission is proposed) is decision D32.'),
        Field('lab_result_date', 'Date the laboratory results were reported', 'date', qn='G0a', group=LAB,
              allow_nd=True, status='Added (not on CRF)', decision='D43',
              notes='Saved even if wrong; flagged under Data quality > Dates (future, before the sample date).'),
        Field('hb', 'Hemoglobin', 'decimal', qn='G1', group=LAB, unit='g/dL', dp=3, hard=(1, 25), check=(4, 20),
              ref=(11.1, 17.5), allow_nd=True,
              notes='MNH Jeeva full blood count: g/dL, 3 decimals, lower limit 11.1; upper limit proposed.'),
        Field('platelets', 'Platelet count', 'decimal', qn='G2', group=LAB, unit='×10⁹/L (= K/µL)', dp=2,
              hard=(1, 2000), check=(10, 1000), ref=(100, 400), allow_nd=True,
              notes='MNH Jeeva full blood count: K/µL, 2 decimals, lower limit 100; upper limit proposed.'),
        Field('wbc', 'WBC', 'decimal', qn='G3', group=LAB, unit='×10⁹/L (= K/µL)', dp=3, hard=(0.1, 300), check=(1, 50),
              ref=(5.0, 11.0), allow_nd=True, status='Changed from CRF', decision='D23', crf_wording='WBC): ______',
              notes='Unit missing on the CRF. MNH Jeeva full blood count: K/µL (= ×10⁹/L), 3 decimals, lower limit 5; '
                    'upper limit proposed.'),
        Field('bilirubin', 'Serum total bilirubin', 'decimal', qn='G4', group=LAB, unit='µmol/L', dp=2,
              hard=(1, 1200), check=(3, 600), ref=(5.2, 41), allow_nd=True, decision='D03',
              notes='MNH Jeeva: µmol/L, 5.2-41. Converted to mg/dL for the scores (÷17.1).'),
        Field('direct_bilirubin', 'Serum direct bilirubin', 'decimal', qn='G5', group=LAB, unit='µmol/L', dp=2,
              hard=(0, 900), check=(0, 450), ref=(0.72, 8.22), allow_nd=True, decision='D38',
              notes='New in v0.2. MNH Jeeva: µmol/L, 0.72-8.22. Cannot exceed total bilirubin.'),
        Field('albumin', 'Serum albumin', 'decimal', qn='G6', group=LAB, unit='g/L', dp=1, hard=(5, 70),
              check=(10, 55), ref=(35, 50), allow_nd=True, status='Changed from CRF', decision='D03',
              crf_wording='Serum albumin (g/dL)',
              notes='Fixed to the MNH lab unit (g/L); the CRF asks g/dL. Converted to g/dL for Child-Pugh (÷10).'),
        Field('inr', 'INR', 'decimal', qn='G7', group=LAB, dp=2, hard=(0.5, 20), check=(0.8, 8), ref=(0.8, 1.2),
              allow_nd=True, notes='Reference interval proposed; confirm with MNH lab.'),
        Field('creatinine', 'Serum creatinine', 'decimal', qn='G8', group=LAB, unit='µmol/L', dp=1, hard=(10, 2500),
              check=(25, 1000), ref=(63.6, 110.5), allow_nd=True, status='Changed from CRF', decision='D03',
              crf_wording='Serum creatinine (mg/dL)',
              notes='Fixed to the MNH Jeeva unit (µmol/L, 63.6-110.5); the CRF asks mg/dL. '
                    'Converted to mg/dL for MELD-Na (÷88.4).'),
        Field('sodium', 'Serum sodium', 'decimal', qn='G9', group=LAB, unit='mmol/L (= mEq/L)', dp=1, hard=(90, 190),
              check=(115, 160), ref=(133.6, 142.5), allow_nd=True,
              notes='MNH Jeeva: mmol/L, 133.6-142.5. The MNH Gastro sheet labels mEq/L, which equals mmol/L.'),
        Field('potassium', 'Serum potassium', 'decimal', qn='G10', group=LAB, unit='mmol/L (= mEq/L)', dp=2,
              hard=(1, 10), check=(2.5, 7), ref=(3.83, 5.52), allow_nd=True, decision='D38',
              notes='New in v0.2; unit missing on the CRF. MNH Jeeva: mmol/L, 3.83-5.52 (mEq/L equals mmol/L).'),
        Field('chloride', 'Serum chloride', 'decimal', qn='G11', group=LAB, unit='mmol/L (= mEq/L)', dp=1,
              hard=(60, 150), check=(80, 125), ref=(98, 107), allow_nd=True, decision='D38',
              notes='New in v0.2; unit missing on the CRF. Reference interval proposed; confirm with MNH lab.'),
        Field('bun', 'Serum blood urea nitrogen (BUN)', 'decimal', qn='G12', group=LAB, unit='mmol/L', dp=1,
              hard=(0.5, 80), check=(1, 50), ref=(3.2, 7.4), allow_nd=True, decision='D38',
              notes='New in v0.2; unit missing on the CRF. Fixed to the MNH Jeeva unit (mmol/L, 3.2-7.4).'),
        Field('alt', 'ALT', 'decimal', qn='G13', group=LAB, unit='U/L (= IU/L)', dp=2, hard=(0, 20000), check=(1, 2000),
              ref=(0, 55), allow_nd=True, notes='Reference interval from MNH Jeeva.'),
        Field('ast', 'AST', 'decimal', qn='G14', group=LAB, unit='U/L (= IU/L)', dp=2, hard=(0, 20000), check=(1, 2000),
              ref=(0, 48.1), allow_nd=True, notes='Reference interval from MNH Jeeva.'),
        Field('ggt', 'GGT', 'decimal', qn='G15', group=LAB, unit='U/L (= IU/L)', dp=2, hard=(0, 10000), check=(1, 2000),
              ref=(9.3, 120.8), allow_nd=True, notes='Reference interval from MNH Jeeva.'),
        Field('alp', 'ALP', 'decimal', qn='G16', group=LAB, unit='U/L (= IU/L)', dp=2, hard=(0, 10000), check=(10, 3000),
              ref=(45.4, 170), allow_nd=True, notes='Reference interval from MNH Jeeva.'),
        Field('afp', 'Serum alpha-fetoprotein (AFP)', 'decimal', qn='G17', group=LAB, unit='ng/mL', dp=2,
              hard=(0, 9000000), check=(0, 100000), ref=(0, 10), allow_nd=True, decision='D38',
              crf_wording='Serum Alpha fetal protein',
              notes='New in v0.2; unit missing on the CRF (MNH Gastro sheet: ng/mL). Reference interval proposed.'),
        YN('hbsag', 'Hepatitis B surface antigen', 'G18', choices='posneg', group=SERO, allow_nd=True),
        YN('hcv_ab', 'Hepatitis C antibody', 'G19', choices='posneg', group=SERO, allow_nd=True),
        YN('hiv_test', 'HIV test', 'G20', choices='posneg', group=SERO, allow_nd=True),
        Field('img_modality', 'Which radiological investigation is available?', 'select_multiple', qn='G21',
              choices='imaging', group=RAD, allow_nd=True, decision='D41',
              notes='Tick both if both were done. The imaging questions below apply once one is ticked; tick "Not '
                    'done" when no imaging is available.'),
        Field('imaging_date', 'Date of the imaging', 'date', qn='G21a', group=RAD, relevant=IMAGING_DONE,
              allow_nd=True, status='Added (not on CRF)', decision='D43',
              notes='Saved even if wrong; flagged under Data quality > Dates (future, long before admission, '
                    'after death or discharge).'),
        YN('img_cirrhotic', 'Cirrhotic liver', 'G22', group=RAD, relevant=IMAGING_DONE),
        YN('img_ascites', 'Ascites', 'G23', group=RAD, relevant=IMAGING_DONE),
        YN('img_splenomegaly', 'Splenomegaly', 'G24', group=RAD, relevant=IMAGING_DONE),
        YN('img_pvt', 'Portal vein thrombosis', 'G25', group=RAD, relevant=IMAGING_DONE),
        YN('img_hcc', 'Hepatocellular carcinoma', 'G26', group=RAD, relevant=IMAGING_DONE, decision='D11'),
        Field('hcc_lesions', 'Number of lesions', 'integer', qn='G26a', group=HCC, hard=(1, 50), check=(1, 10),
              relevant=IMAGING_DONE + [('img_hcc', '==', 1)], decision='D40'),
        Field('hcc_size_cm', 'Size of the largest lesion', 'decimal', qn='G26b', group=HCC, unit='cm', dp=1,
              hard=(0.1, 30), check=(0.5, 20), relevant=IMAGING_DONE + [('img_hcc', '==', 1)], status='Changed from CRF',
              decision='D40', crf_wording='Size of the lesions ...... in cm'),
        YN('hcc_vascular_invasion', 'Portal or hepatic vein invasion', 'G26c', group=HCC,
           relevant=IMAGING_DONE + [('img_hcc', '==', 1)]),
        YN('hcc_extrahepatic', 'Extrahepatic spread (metastasis)', 'G26d', group=HCC,
           relevant=IMAGING_DONE + [('img_hcc', '==', 1)]),
    ]),
    Section('H', 'complications', 'Complications of cirrhosis', [
        YN('comp_sbp', 'Spontaneous bacterial peritonitis (diagnosed by generalized abdominal tenderness)', 'H1',
           decision='D30'),
        YN('comp_variceal_bleed', 'Bleeding varices on OGD', 'H2'),
    ]),
    Section('I', 'child_pugh', 'Child-Pugh score (calculated)', [],
            note='Removed from the questionnaire in v0.2: the system calculates Child-Pugh from Sections F and G. '
                 'Nothing to enter.'),
    Section('J', 'meld', 'MELD-Na score (calculated)', [],
            note='Removed from the questionnaire in v0.2: the system calculates MELD-Na from Section G. Nothing to enter.'),
    Section('K', 'transplant', 'Liver transplant eligibility assessment', [
        YN('k_recurrent_variceal', 'Recurrent variceal bleeding', 'K1', group='Indications'),
        YN('k_refractory_ascites', 'Refractory ascites', 'K2', group='Indications'),
        YN('k_recurrent_he', 'Recurrent hepatic encephalopathy', 'K3', group='Indications',
           notes='Child-Pugh class C, MELD-Na >= 15, HCC within Milan criteria and "transplant indicated" are '
                 'calculated (Derived Scores, D37).'),
    ]),
    Section('L', 'outcome', 'Outcome of current admission', [
        Field('los_days', 'Length of hospital stay', 'integer', qn='L1', unit='days', hard=(0, 365), check=(0, 90),
              notes='Filled in automatically from the admission and discharge/death dates when left empty.'),
        Field('outcome', 'Outcome', 'select_one', qn='L2', choices='outcome', status='Code proposed'),
        Field('discharge_date', 'Date of discharge', 'date', qn='L3a', relevant=[('outcome', '==', 1)],
              status='Added (not on CRF)', decision='D21',
              notes='Asked when L2 = Discharged alive. Cannot be before admission or in the future.'),
        Field('death_date', 'Date of death', 'date', qn='L3b', relevant=[('outcome', '==', 2)],
              status='Added (not on CRF)', decision='D21',
              notes='Asked when L2 = Died. Cannot be before admission or in the future.'),
    ]),
]

DERIVED = [
    Derived('bmi', 'Body mass index', 'F', 'weight_kg / (height_cm / 100)^2, 1 decimal', '10-70', unit='kg/m²',
            interpretation='<18.5 underweight, 18.5-24.9 normal, 25-29.9 overweight, >=30 obese',
            source='Weight and height (F1, F2)', status='Derived (removed from CRF v0.2)'),
    Derived('bilirubin_mgdl', 'Total bilirubin in mg/dL', 'G', 'bilirubin (µmol/L) / 17.1',
            unit='mg/dL', source='Unit conversion', decision='D03'),
    Derived('albumin_gdl', 'Albumin in g/dL', 'G', 'albumin (g/L) / 10', unit='g/dL',
            source='Unit conversion', decision='D03'),
    Derived('creatinine_mgdl', 'Creatinine in mg/dL', 'G', 'creatinine (µmol/L) / 88.4',
            unit='mg/dL', source='Unit conversion', decision='D03'),
    Derived('apri', 'AST to platelet ratio index (APRI)', 'G', '(AST / 48.1) / platelets x 100; 48.1 = MNH AST upper limit',
            interpretation='>1.0 suggests cirrhosis', source='MNH Gastro lab sheet lists APRI', status='Proposed',
            decision='D31'),
    Derived('hcc_milan', 'HCC within Milan criteria', 'G',
            'Only when imaging shows HCC: 1 if no vein invasion, no extrahepatic spread, and 1 lesion <= 5 cm or 2-3 '
            'lesions with the largest <= 3 cm; else 0', '0-1', source='G26a-G26d (new in v0.2)', status='Proposed',
            decision='D40'),
    Derived('cp_bili_pts', 'Child-Pugh bilirubin points', 'I', 'bilirubin_mgdl <2 = 1, 2-3 = 2, >3 = 3', '1-3',
            source='Section I removed in v0.2: calculated', decision='D04'),
    Derived('cp_alb_pts', 'Child-Pugh albumin points', 'I', 'albumin_gdl >3.5 = 1, 2.8-3.5 = 2, <2.8 = 3', '1-3',
            source='Section I removed in v0.2: calculated', decision='D04'),
    Derived('cp_inr_pts', 'Child-Pugh INR points', 'I', 'inr <1.7 = 1, 1.7-2.3 = 2, >2.3 = 3', '1-3',
            source='Section I removed in v0.2: calculated', decision='D04'),
    Derived('cp_ascites_pts', 'Child-Pugh ascites points', 'I', 'ascites Absent = 1; grade Moderate = 2; Severe = 3',
            '1-3', source='F7, F7a', status='Proposed', decision='D36'),
    Derived('cp_enceph_pts', 'Child-Pugh encephalopathy points', 'I',
            'hepatic_enceph Absent or grade 0 = 1; grade I-II = 2; III-IV = 3', '1-3', source='F9, F9a', decision='D39'),
    Derived('cp_score', 'Child-Pugh score', 'I', 'Sum of the five points; blank if any is missing', '5-15',
            source='Section I removed in v0.2: calculated', decision='D04'),
    Derived('cp_class', 'Child-Pugh class', 'I', '5-6 = A, 7-9 = B, 10-15 = C', 'A-C',
            source='Section I removed in v0.2: calculated', decision='D04'),
    Derived('meld', 'MELD', 'J', '10 x (0.957 ln(Cr) + 0.378 ln(Bili) + 1.120 ln(INR)) + 6.43; Cr, Bili and INR '
            'below 1.0 set to 1.0, Cr above 4.0 set to 4.0 (mg/dL)', '6-40',
            source='Section J removed in v0.2: calculated', decision='D05'),
    Derived('meld_na', 'MELD-Na score', 'J', 'If MELD > 11: MELD + 1.32 x (137 - Na) - 0.033 x MELD x (137 - Na), '
            'with Na limited to 125-137; rounded; maximum 40', '6-40', source='OPTN 2016 formula', decision='D05'),
    Derived('k_child_c', 'Child-Pugh class C', 'K', '1 if cp_class = C', '0-1', source='Removed from K in v0.2: calculated',
            decision='D37'),
    Derived('k_meld15', 'MELD-Na >= 15', 'K', '1 if meld_na >= 15', '0-1', source='Removed from K in v0.2: calculated',
            decision='D37'),
    Derived('lt_indicated', 'Liver transplant indicated (study outcome)', 'K',
            '1 if any of: Child-Pugh C, MELD-Na >= 15, K1, K2, K3, HCC within Milan; 0 if all are known and none is '
            'met; blank otherwise', '0-1', source='Proposed definition', status='Proposed', decision='D37'),
    Derived('los_from_dates', 'Length of stay from dates', 'L', '(discharge_date or death_date) - admission_date in days', '0-365',
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
        elif op == 'any':
            parts.append(f"count-selected(${{{name}}}) > 0")
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
        if op == 'any':
            group = FIELD_BY_NAME[name][1]
            ok = any(values.get(c) for c in group.columns)
        elif op == 'filled':
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
