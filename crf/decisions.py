"""Open questions about the CRF, shown on the Decisions sheet of the data dictionary.

Each one says what is wrong or missing, what the system does for now, and who should decide. When an answer comes
(or a new CRF / the proposal arrives), record it here with the answer and set status to Answered.
(id, priority, area, CRF item, problem found, what the system does now / proposal, who decides, answer, status)
"""

DECISIONS = [
    ('D00', 'Example', 'Example', 'A3', 'Code list has 3 options but 4 tick boxes.', 'Add the missing option.',
     'Data manager', 'Add option 4 "Other". Agreed 5 Nov.', 'Example'),

    # --- High: affect the main outcomes (severity scores, transplant eligibility) ---
    ('D03', 'High', 'Units', 'G4, G5, G7', 'The CRF fixes units that the MNH laboratory does not report: creatinine '
     'in mg/dL (MNH Jeeva reports µmol/L, 63.6-110.5) and albumin in g/dL (MNH sheet uses g/L). Bilirubin is '
     '"mg/dL or µmol/L" with no place to say which. A wrong unit changes Child-Pugh and MELD-Na.',
     'The system records each value with its unit (default = the MNH unit) and converts to mg/dL and g/dL for the '
     'scores. Values that look like the wrong unit are flagged.', 'PI + supervisor', '', 'Open'),
    ('D32', 'High', 'Lab timing', 'Section G', 'The CRF does not say which result to record when a patient has '
     'several during the admission (first, worst, or closest to the interview), or how long after admission '
     'results may be collected. Scores depend on it, and results arrive later than the interview.',
     'Record the first result after admission, with the sample date (G0, added). Results more than 7 days before '
     'admission are flagged.', 'PI + supervisor', '', 'Open'),
    ('D04', 'High', 'Child-Pugh', 'Section I', 'Section I asks the interviewer to tick bilirubin, albumin, INR and '
     'encephalopathy points by hand, although Sections D and G already hold the values. Hand scoring adds errors, '
     'and the CRF has no cut-offs printed. Ascites grade (None/Mild/Moderate-Severe) is not in Section D, which only '
     'has Present/Absent.', 'Points for bilirubin, albumin, INR and encephalopathy are calculated (standard cut-offs). '
     'Only the ascites grade (I4) is entered.', 'PI', '', 'Open'),
    ('D05', 'High', 'MELD-Na', 'Section J', 'Section J repeats the four inputs from Section G and has no result line. '
     'Formula not stated (MELD-Na OPTN 2016 or MELD 3.0). Dialysis in the past week (sets creatinine to 4.0) is not '
     'asked.', 'MELD-Na (OPTN 2016) calculated from Section G; Section J has nothing to enter. Add "dialysis twice '
     'or more in the past 7 days" if MELD-Na must be exact.', 'PI + statistician', '', 'Open'),
    ('D20', 'High', 'Transplant eligibility', 'Section K', 'K1 (Child-Pugh C) and K2 (MELD-Na >= 15) can be '
     'calculated. K7 "accepted criteria" is not defined (any one indication? a combination? a reference guideline?). '
     'K6 Milan criteria needs tumour number and size, which the CRF does not collect.',
     'K1 and K2 calculated. K7 entered as the assessor\'s judgement. Define K7 and decide whether to add HCC '
     'number and largest size (Milan: 1 lesion <= 5 cm, or up to 3 lesions <= 3 cm, no vascular invasion).',
     'PI + supervisor', '', 'Open'),
    ('D02', 'High', 'Eligibility', 'No CRF item', 'The CRF has no inclusion/exclusion checklist or consent record '
     '(date of consent, who consented: patient or relative, e.g. for encephalopathy). The proposal was not available.',
     'Not built yet. Add an eligibility and consent section when the proposal arrives.', 'PI', '', 'Open'),
    ('D21', 'High', 'Dates', 'H, L1', 'There is no admission date or discharge/death date, so length of stay (L1) '
     'cannot be checked, and lab timing cannot be judged. Cause and date of death are not collected.',
     'Admission date (H5) and discharge/death date (L3) added; L1 is checked against them. Decide whether to add '
     'cause of death.', 'PI', '', 'Open'),

    # --- Medium: definitions and coding ---
    ('D35', 'Medium', 'Hospital ID', 'H1a', 'The hospital registration number is recorded for every patient and is '
     'required before a participant can be registered, but it is not printed on the CRF, and its format is not '
     'stated. The MNH system shows both an MR number (one per patient) and an IP number (one per admission).',
     'Required and unique; letters, digits, "-", "/" and "." accepted, stored in capitals. Proposed: use the MR '
     'number (stays the same across admissions) and add a "Hospital ID" line to the CRF header.', 'PI', '', 'Open'),
    ('D01', 'Medium', 'Study ID', 'H1', 'Study ID format not given.', 'System generates CLD-0001, CLD-0002, ... when '
     'a participant is registered. Change the prefix in .env (STUDY_ID_PREFIX) if needed.', 'PI', '', 'Open'),
    ('D06', 'Medium', 'Skip logic', 'B1', 'If "Ever diagnosed with CLD" is No, should B2 be skipped? (Assumed yes.) '
     'All participants have decompensated CLD, so No means first diagnosis at this admission.',
     'B2 is asked only when B1 = Yes.', 'PI', '', 'Open'),
    ('D07', 'Medium', 'Units', 'B2', 'Duration since diagnosis is free text (no unit).', 'Number plus unit '
     '(months/years).', 'Data manager', '', 'Open'),
    ('D08', 'Medium', 'Units', 'D6a', '"If present: ____ degree" - temperature in °C assumed. Fever threshold not '
     'stated.', 'Temperature in °C (34-43); below 37.5 °C with fever = Present is flagged.', 'PI', '', 'Open'),
    ('D09', 'Medium', 'Duplicates', 'D9, H3, I5', 'Hepatic encephalopathy is asked three times (examination, '
     'complications, Child-Pugh).', 'D9 + grade entered; I5 calculated from D9a; H3 entered and checked against D9.',
     'PI', '', 'Open'),
    ('D10', 'Medium', 'Duplicates', 'D7, G14, H1, I4', 'Ascites is asked four times.', 'All kept (examination, '
     'ultrasound, complication, Child-Pugh grade); differences are flagged as data quality checks.', 'PI', '', 'Open'),
    ('D11', 'Medium', 'Duplicates', 'E13, G17, H7, K6', 'Hepatocellular carcinoma is asked four times, with no '
     'definition (imaging, AFP, histology?).', 'All kept; differences flagged. State how HCC is diagnosed. MNH sheet '
     'lists AFP (see D31).', 'PI', '', 'Open'),
    ('D12', 'Medium', 'Duplicates', 'G16, H6', 'Portal vein thrombosis is asked in radiology and complications.',
     'Both kept; imaging Yes with complication No is flagged.', 'PI', '', 'Open'),
    ('D14', 'Medium', 'Alcohol', 'E5a-E5d', 'Units per day and per week are both asked (one is enough); "unit" not '
     'defined (10 g ethanol?). "Recent use within 3 months" has a blank line instead of Yes/No.',
     'Both amounts kept and checked against each other; E5d recorded as Yes/No. Define a unit on the CRF.',
     'PI', '', 'Open'),
    ('D15', 'Medium', 'Etiology', 'E1-E3', 'Based on history or on a test? HBsAg positive is stated for HBV only; '
     'HDV testing is rarely available.', 'Recorded as on the CRF. Consider recording the test result and date '
     '(MNH sheet has HBsAg, HCV Ab, HBV and HCV viral load).', 'PI', '', 'Open'),
    ('D16', 'Medium', 'Etiology', 'E15', 'Final etiology is free text, which is hard to analyse.', 'Free text for '
     'now. Proposed: pick one or more from the E1-E14 list plus Other.', 'PI + statistician', '', 'Open'),
    ('D30', 'Medium', 'Definitions', 'H2, H5', 'SBP and hepatorenal syndrome definitions are not on the CRF. '
     'Handwritten notes on the MNH sheet mention "SBP => WBC count in ascitic fluid" and hepatorenal syndrome.',
     'Recorded as Yes/No. Proposed: add ascitic fluid PMN count (SBP if >= 250 cells/mm³) and use ICA criteria for '
     'HRS.', 'PI + supervisor', '', 'Open'),
    ('D31', 'Medium', 'Extra tests', 'MNH lab sheet', 'The MNH Gastro sheet lists tests not on the CRF: PT, PTT, '
     'urea, potassium, direct bilirubin, total protein, AFP, HBV/HCV viral load, CA 19-9, CEA, APRI.',
     'Not collected. APRI is calculated from AST and platelets. Decide which (if any) to add, e.g. AFP for HCC.',
     'PI', '', 'Open'),
    ('D33', 'Medium', 'Eligibility', 'A1', 'Minimum age not stated.', 'Age below 18 is flagged for checking.',
     'PI', '', 'Open'),
    ('D34', 'Medium', 'Definitions', 'D9a', 'Grading system for encephalopathy not named.', 'West Haven assumed.',
     'PI', '', 'Open'),

    # --- Low: wording and layout ---
    ('D17', 'Low', 'Numbering', 'Whole CRF', 'Questions are numbered only in places (5, 39, ...).', 'The dictionary '
     'gives every item a code (A1, A2, ...). Print these on the next CRF version.', 'Data manager', '', 'Open'),
    ('D18', 'Low', 'Coding', 'A5, A6', 'Occupation and residence are free text.', 'Free text for now. Proposed: '
     'occupation list, and region/district for residence.', 'PI', '', 'Open'),
    ('D19', 'Low', 'Coding', 'A7a', 'Insurance type is free text.', 'Free text for now. Proposed list: NHIF, '
     'iCHF/CHF, private, employer, other.', 'PI', '', 'Open'),
    ('D23', 'Low', 'Units', 'G3', 'WBC has no unit on the CRF ("WBC): ____").', 'Recorded as ×10⁹/L (same as K/µL '
     'on the MNH sheet).', 'Data manager', '', 'Open'),
    ('D27', 'Low', 'Confidentiality', 'H4', 'Patient phone number is collected, but the CRF has no follow-up after '
     'discharge. Why is it needed?', 'Stored, shown only to Data Clerks, Data Managers and Admins, and removed '
     'from de-identified exports. Drop it if not needed.', 'PI', '', 'Open'),
    ('D28', 'Low', 'Wording', 'H3', 'Interviewer initials.', 'Replaced by the logged-in account.', 'Data manager',
     '', 'Open'),
]
