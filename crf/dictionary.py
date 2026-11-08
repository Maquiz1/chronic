"""Builds the Excel data dictionary from crf/spec.py and crf/decisions.py.

Plain Python plus openpyxl (no Django), so it also runs from the command line:
    python -m crf.dictionary            -> data_dictionary/DCLD_Data_Dictionary_v<VERSION>.xlsx
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

try:  # works both inside Django (crf.spec) and as `python -m crf.dictionary`
    from . import check_rules
    from . import decisions as decisions_mod
    from . import spec
except ImportError:  # pragma: no cover
    import check_rules
    import decisions as decisions_mod
    import spec

HEADER_FILL = PatternFill('solid', fgColor='1F3864')
HEADER_FONT = Font(bold=True, color='FFFFFF')
YELLOW = PatternFill('solid', fgColor='FFF2CC')
GREY = PatternFill('solid', fgColor='EDEDED')
SECTION_FILL = PatternFill('solid', fgColor='D9E1F2')
# Decisions sheet: High = red, Medium = yellow, Low = green.
PRIORITY_FILLS = {'High': PatternFill('solid', fgColor='F8CBCB'), 'Medium': PatternFill('solid', fgColor='FFE699'),
                  'Low': PatternFill('solid', fgColor='D9EAD3')}
PRIORITY_FONTS = {'High': Font(bold=True, color='9C0006'), 'Medium': Font(bold=True, color='7F6000'),
                  'Low': Font(color='274E13')}
THIN = Side(style='thin', color='BFBFBF')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical='top')

# Version history: add a line for every new version.
CHANGE_LOG = [
    ('0.1', '2026-11-08', 'First draft from "questionnaire final.docx" and the MNH lab sheets (units1.jpeg, '
     'units2.jpeg). Proposal not yet received. Later: MRN added (H1a, D35).'),
    ('0.2', '2026-11-08', 'Updated to "questionnaire final_v0.2.docx". Sections re-lettered: Etiology D (was E), '
     'Comorbidities E (was F), Examination F (was D). Etiology: hepatitis B/C duration and treatment added; PBC, PSC, '
     'Wilson and haemochromatosis removed; alcohol units per week replaced by days drinking per week. Examination: blood '
     'pressure, ascites grade (Moderate/Severe) and HE grade 0 added. Investigations: direct bilirubin, potassium, '
     'chloride, BUN, AFP, HBsAg, HCV antibody, HIV test, imaging modality and HCC lesion details (number, largest size, '
     'vein invasion, extrahepatic spread) added; imaging items no longer ultrasound-only. Complications: only SBP and '
     'bleeding varices on OGD remain. Sections I (Child-Pugh) and J (MELD-Na) removed from the CRF: calculated. '
     'Transplant: Child-Pugh C, MELD-Na, Milan and "meets criteria" removed; calculated, plus a proposed outcome '
     '"transplant indicated" (D37). Decisions D04, D09-D12, D15, D20, D31, D34 answered; D36-D41 new.'),
    ('0.2.1', '2026-11-08', 'Pre-go-live unit review (no questionnaire change). No unit choice at entry: values are '
     'entered in the MNH laboratory units: total and direct bilirubin µmol/L, albumin g/L, creatinine µmol/L, BUN '
     'mmol/L (unit columns G4a, G5a, G6a, G8a, G12a removed). Decimals as the MNH lab prints them: ALT, AST, GGT, ALP, '
     'potassium, bilirubins and AFP 2 decimals; sodium and chloride 1 decimal (were whole numbers). Equivalent units '
     'shown: ×10⁹/L (= K/µL), mmol/L (= mEq/L), U/L (= IU/L). Decisions D03 and D38 answered.'),
]

# Issued versions are kept in data_dictionary/ (not in git; mounted read-only into the app on the server) and every
# version found there, other than the current one, can still be downloaded in the app.
ARCHIVE_DIR = Path(__file__).resolve().parent.parent / 'data_dictionary'


def archived_versions():
    """[(version, path)] of earlier dictionary versions, newest first, excluding the current one."""
    out = []
    for path in sorted(ARCHIVE_DIR.glob('DCLD_Data_Dictionary_v*.xlsx'), reverse=True):
        version = path.stem.rsplit('_v', 1)[1]
        if version != spec.VERSION:
            out.append((version, path))
    return out


def dictionary_filename(section=None):
    suffix = f'_Section_{section}' if section else ''
    return f'DCLD_Data_Dictionary_v{spec.VERSION}{suffix}.xlsx'


def _in_scope(section):
    """Sections included: all, or just the one asked for."""
    return [s for s in spec.SECTIONS if section is None or s.code == section]


def _decisions_for(section):
    if section is None:
        return list(decisions_mod.DECISIONS)
    s = spec.SECTION_BY_CODE[section]
    ids = {f.decision for f in s.fields if f.decision} | {d.decision for d in spec.DERIVED
                                                           if d.section == section and d.decision}
    return [d for d in decisions_mod.DECISIONS if d[0] in ids or d[1] == 'Example']


def _table(ws, headers, rows, widths, start_row=1, wrap_cols=()):
    for i, h in enumerate(headers, 1):
        c = ws.cell(start_row, i, h)
        c.fill, c.font, c.border, c.alignment = HEADER_FILL, HEADER_FONT, BORDER, WRAP
    for r, row in enumerate(rows, start_row + 1):
        for i, value in enumerate(row, 1):
            c = ws.cell(r, i, value)
            c.border = BORDER
            c.alignment = WRAP
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(start_row + 1, 1)
    if rows:
        ws.auto_filter.ref = f'A{start_row}:{get_column_letter(len(headers))}{start_row + len(rows)}'


def _range_text(r):
    return f'{r[0]:g}-{r[1]:g}' if r else ''


def _dictionary_rows(section=None):
    rows, n = [], 0
    for f in (spec.HEADER if section is None else []):
        n += 1
        rows.append([n, 'Header', 'Questionnaire header', f.name, f.qn, f.label, f.type, '', f.unit, '', '', '', '', '',
                     'Yes' if f.name in ('study_id', 'hospital_id', 'interview_date') else 'No', '', '', f.crf_wording, f.status,
                     f.decision, f.notes])
    for section in _in_scope(section):
        if not section.fields:
            n += 1
            rows.append([n, section.code, section.title, '(calculated)', '', section.note, 'calculated', '', '', '', '',
                         '', '', '', 'No', '', '', '', 'Derived', '', 'See Derived Scores sheet.'])
            continue
        for f in section.fields:
            n += 1
            if f.by_unit:
                hard = '; '.join(f'{c["unit"]}: {_range_text(c["hard"])}' for c in f.by_unit.values())
                check = '; '.join(f'{c["unit"]}: {_range_text(c["check"])}' for c in f.by_unit.values())
                ref = '; '.join(f'{c["unit"]}: {_range_text(c["ref"])}' for c in f.by_unit.values())
                unit = f'see {f.unit_field}'
            else:
                hard, check, ref, unit = _range_text(f.hard), _range_text(f.check), _range_text(f.ref), f.unit
            columns = ', '.join(f.columns) if f.type == 'select_multiple' else ''
            notes = '; '.join(x for x in (f.notes, f'Columns: {columns}' if columns else '') if x)
            rows.append([n, section.code, section.title, f.name, f.qn, f.label, f.type, f.choices, unit,
                         f.dp if f.type == 'decimal' else '', hard, check, ref,
                         'Yes' if f.allow_nd else '', 'No', 'Yes' if f.expected else 'No (optional)',
                         spec.relevance_text(f), f.crf_wording, f.status, f.decision, notes])
    return rows


def build_workbook(section=None):
    """The whole dictionary, or only one section (section='A' ... 'L')."""
    if section is not None and section not in spec.SECTION_BY_CODE:
        raise ValueError(f'Unknown section {section}')
    scope = 'All sections' if section is None else f'Section {section} only: {spec.SECTION_BY_CODE[section].title}'
    in_scope = _in_scope(section)
    decisions = _decisions_for(section)
    wb = Workbook()

    # README -------------------------------------------------------------------------------------------------------
    ws = wb.active
    ws.title = 'README'
    open_high = sum(1 for d in decisions if d[1] == 'High' and d[8] == 'Open')
    lines = [
        ('LIVERCare (DCLD study, Muhimbili National Hospital): Data Dictionary', None),
        (f'Version {spec.VERSION}, DRAFT, {spec.VERSION_DATE}. {open_high} High decisions open.', None),
        ('Contents', scope + ('' if section is None else '. Decisions, choices and derived values are limited to '
                              'this section; download "All sections" for the full workbook.')),
        (None, None),
        ('Study', spec.STUDY_TITLE),
        ('Purpose', 'Lists every variable on the questionnaire with its code, label, type, codes, units, limits and '
                    'skip rules. The data entry system, its checks and the exports are generated from the same source '
                    '(crf/spec.py), so this workbook always matches the system.'),
        ('Sources', f'documentations/tools/{spec.CRF_SOURCE} (CRF version {spec.VERSION}); documentations/si_units_range/units1.jpeg (MNH '
                    'Gastroenterology unit lab sheet: tests and units) and units2.jpeg (MNH Jeeva clinical chemistry '
                    'screen: units and reference limits). The study proposal was not available.'),
        ('What to do', '1. Answer the Decisions sheet in the yellow columns, starting with the High items (red; Medium '
                       'items are yellow, Low green).\n'
                       '2. Check the Reference Ranges sheet with the MNH laboratory (rows marked Proposed).\n'
                       '3. Send the updated CRF and the proposal; a new version of this workbook and the system follow.'),
        ('Saving incomplete forms', 'No CRF field is mandatory in the system. Each section is saved on its own and '
                                    'completed later (e.g. when laboratory results arrive). Lab and imaging items can be '
                                    'ticked "Not done / not available". The Data quality pages list what is still '
                                    'missing for each participant, following the skip rules.'),
        ('Limits', 'Hard limits: values outside are refused at entry. Check limits: possible but unusual, flagged '
                   '"verify against source". Reference: normal range, shown as L/H (clinical information, not an error).'),
        ('Codes', 'Yes = 1, No = 0, Unknown = 9; Present = 1, Absent = 0 (proposed; the CRF prints only tick boxes). '
                  'Multiple-answer questions are stored as one 0/1 column per option.'),
        (None, None),
        ('Sheets', None),
        ('Sections', 'The CRF sections and how many variables each has.'),
        ('Data Dictionary', 'One row per question.'),
        ('Choices', 'Code lists.'),
        ('Derived Scores', 'Values the system calculates: BMI, unit conversions, Child-Pugh, MELD-Na, APRI, K1-K2.'),
        ('Reference Ranges', 'Units and limits for every laboratory test, with their source (Section G).'),
        ('Data Checks', 'Every automatic check (dates, ranges, consistency): errors and warnings, and which are blocked at entry.'),
        ('Decisions', 'Problems found in the CRF, what the system does for now, and who decides.'),
        ('Change Log', 'What changed in each version.'),
    ]
    for r, (a, b) in enumerate(lines, 1):
        ws.cell(r, 1, a)
        ws.cell(r, 2, b).alignment = WRAP
        if a and b is not None:
            ws.cell(r, 1).font = Font(bold=True)
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'].font = Font(italic=True)
    ws.column_dimensions['A'].width = 24
    ws.column_dimensions['B'].width = 110

    # Sections ------------------------------------------------------------------------------------------------------
    ws = wb.create_sheet('Sections')
    rows = [['Header', 'Questionnaire header (Study ID, dates, interviewer, phone)', len(spec.HEADER), '',
             'Entered when the participant is registered.']] if section is None else []
    for s in in_scope:
        rows.append([s.code, s.title, f"=COUNTIF('Data Dictionary'!$B:$B,A{len(rows) + 2})",
                     sum(1 for d in spec.DERIVED if d.section == s.code), s.note])
    _table(ws, ['Section', 'Title', 'Variables', 'Derived values', 'Note'], rows, [10, 50, 11, 14, 70])

    # Data Dictionary -----------------------------------------------------------------------------------------------
    ws = wb.create_sheet('Data Dictionary')
    headers = ['Row', 'Section', 'Section title', 'Variable', 'Qn', 'Label (English)', 'Type', 'Choice list', 'Unit',
               'Decimals', 'Hard limits (refused)', 'Check limits (flagged)', 'Reference range', 'Can be "Not done"',
               'Required to save', 'Counts for completeness', 'Relevance (skip rule)', 'CRF wording (if changed)',
               'Status', 'Decision', 'Notes']
    rows = _dictionary_rows(section)
    _table(ws, headers, rows, [5, 8, 22, 22, 6, 45, 12, 14, 12, 8, 20, 20, 20, 9, 9, 11, 28, 26, 18, 9, 50])
    ws.freeze_panes = 'E2'
    for r in range(2, len(rows) + 2):
        status = ws.cell(r, 19).value or ''
        if status != 'Ready':
            ws.cell(r, 19).fill = YELLOW

    # Choices -------------------------------------------------------------------------------------------------------
    ws = wb.create_sheet('Choices')
    used = {f.choices for s in in_scope for f in s.fields if f.choices}
    rows = [[name, code, label, 'Code proposed' if isinstance(code, int) else 'Column suffix']
            for name, items in spec.CHOICES.items() if section is None or name in used for code, label in items]
    _table(ws, ['List', 'Code', 'Label (English)', 'Status'], rows, [18, 22, 40, 16])

    # Derived -------------------------------------------------------------------------------------------------------
    ws = wb.create_sheet('Derived Scores')
    rows = [[d.name, d.section, d.label, d.calculation, d.unit, d.range, d.interpretation, d.source, d.status,
             d.decision] for d in spec.DERIVED if section is None or d.section == section]
    _table(ws, ['Variable', 'Section', 'Description', 'Calculation', 'Unit', 'Range', 'Interpretation', 'Source',
                'Status', 'Decision'], rows, [18, 8, 32, 60, 9, 9, 34, 26, 24, 9])

    # Reference ranges (laboratory tests are all in Section G) ------------------------------------------------------
    rows = []
    for sec, f in spec.all_fields():
        if f.type not in ('integer', 'decimal') or sec.code != 'G' or section not in (None, 'G'):
            continue
        source = 'MNH Jeeva (units2.jpeg)' if 'Jeeva' in f.notes else 'Proposed - confirm with MNH lab'
        configs = f.by_unit.values() if f.by_unit else [{'unit': f.unit, 'hard': f.hard, 'check': f.check, 'ref': f.ref}]
        for cfg in configs:
            src = source
            if f.name == 'creatinine' and cfg['unit'] == 'mg/dL':
                src = 'MNH Jeeva µmol/L range ÷ 88.4'
            elif f.name == 'creatinine':
                src = 'MNH Jeeva (units2.jpeg)'
            rows.append([f.qn, f.label, cfg['unit'], cfg['ref'][0] if cfg['ref'] else '', cfg['ref'][1] if cfg['ref'] else '',
                         _range_text(cfg['check']), _range_text(cfg['hard']), src])
    if rows:
        ws = wb.create_sheet('Reference Ranges')
        _table(ws, ['Qn', 'Test', 'Unit', 'Lower limit', 'Upper limit', 'Check limits', 'Hard limits', 'Source'], rows,
               [6, 26, 12, 12, 12, 14, 14, 36])

    # Data checks ---------------------------------------------------------------------------------------------------
    ws = wb.create_sheet('Data Checks')
    rows = [[rule, category, level.title(), rule_section, text, 'Yes' if 'blocked at entry' in text else 'No']
            for rule, level, category, rule_section, text in check_rules.RULES
            if section is None or rule_section in (section, 'Any')]
    _table(ws, ['Rule', 'Category', 'Level', 'Section', 'Check', 'Blocked at entry'], rows, [18, 13, 9, 9, 90, 10])
    for r in range(2, len(rows) + 2):
        level = ws.cell(r, 3).value
        ws.cell(r, 3).fill = PRIORITY_FILLS['High'] if level == 'Error' else PRIORITY_FILLS['Medium']

    # Decisions -----------------------------------------------------------------------------------------------------
    ws = wb.create_sheet('Decisions')
    ws.cell(1, 1, 'Answer in the yellow columns and change Status to Answered. Row 3 is an example only. '
                  'IDs stay the same between versions, so some numbers are not used.').font = Font(italic=True)
    rows = [list(d[:7]) + [d[7], '', d[8]] for d in decisions]
    _table(ws, ['ID', 'Priority', 'Area', 'CRF item', 'Problem found', 'What the system does now / proposal',
                'Who decides', 'Answer', 'Answered by', 'Status'], rows, [6, 9, 18, 14, 70, 60, 16, 40, 18, 11],
           start_row=2)
    for r in range(3, len(rows) + 3):
        for col in (8, 9, 10):
            ws.cell(r, col).fill = YELLOW
        priority = ws.cell(r, 2).value
        if priority == 'Example':
            for col in range(1, 11):
                ws.cell(r, col).fill = GREY
        elif priority in PRIORITY_FILLS:
            ws.cell(r, 2).fill = PRIORITY_FILLS[priority]
            ws.cell(r, 2).font = PRIORITY_FONTS[priority]
            ws.cell(r, 1).font = PRIORITY_FONTS[priority]
    dv = DataValidation(type='list', formula1='"Open,Answered,Example"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f'J3:J{len(rows) + 2}')

    # Change log ----------------------------------------------------------------------------------------------------
    ws = wb.create_sheet('Change Log')
    _table(ws, ['Version', 'Date', 'Changes'], [list(x) for x in CHANGE_LOG], [10, 12, 110])
    return wb


def write(directory=None):
    directory = Path(directory or Path(__file__).resolve().parent.parent / 'data_dictionary')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / dictionary_filename()
    build_workbook().save(path)
    return path


if __name__ == '__main__':  # pragma: no cover
    print(write())


# --- Codebook (PDF): what each variable and code means, matching the "Codes" export --------------------------------
CODEBOOK_HEADER = ['Variable', 'Qn', 'Label', 'Type', 'Unit / limits', 'Code', 'Meaning']


def codebook_rows(section=None):
    """[(section title or None, row)] - a section title row starts each section."""
    out = []
    if section is None:
        out.append(('Questionnaire header', None))
        for f in spec.HEADER:
            out.append((None, [f.name, f.qn, f.label, f.type, f.unit, '', '']))
    for s in _in_scope(section):
        out.append((f'Section {s.code}: {s.title}', None))
        for f in s.fields:
            if f.by_unit:
                limits = '; '.join(f'{c["unit"]} {_range_text(c["hard"])}' for c in f.by_unit.values())
            else:
                limits = ' '.join(x for x in (f.unit, _range_text(f.hard)) if x)
            skip = f' (asked if {spec.relevance_text(f)})' if f.relevant else ''
            if f.type == 'select_multiple':
                for code, label in spec.CHOICES[f.choices]:
                    out.append((None, [f'{f.name}_{code}', f.qn, f'{f.label}: {label}{skip}', '0/1', '', '1 / 0',
                                       'Ticked / not ticked']))
            elif f.type == 'select_one':
                for i, (code, label) in enumerate(spec.CHOICES[f.choices]):
                    first = i == 0
                    out.append((None, [f.name if first else '', f.qn if first else '', f'{f.label}{skip}' if first else '',
                                       'code' if first else '', '', code, label]))
            else:
                out.append((None, [f.name, f.qn, f'{f.label}{skip}', f.type, limits, '', '']))
        for d in spec.DERIVED:
            if d.section == s.code:
                out.append((None, [d.name, '', f'{d.label} (calculated: {d.calculation})', 'calculated',
                                   ' '.join(x for x in (d.unit, d.range) if x), '', d.interpretation]))
    return out


# The built-in PDF fonts only cover Latin-1: replace the few characters outside it.
PDF_REPLACEMENTS = {'⁹': '^9', '≥': '>=', '≤': '<=', '–': '-', '—': '-', '’': "'", '“': '"', '”': '"', '…': '...'}


def pdf_text(value):
    text = str(value)
    for old, new in PDF_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def codebook_pdf(section=None):
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    buffer = BytesIO()
    styles = getSampleStyleSheet()
    cell = styles['BodyText'].clone('cell', fontSize=7, leading=8.5)
    head = styles['BodyText'].clone('head', fontSize=7.5, leading=9, textColor=colors.white)
    scope = 'all sections' if section is None else f'Section {section}: {spec.SECTION_BY_CODE[section].title}'
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=24, bottomMargin=24, leftMargin=24,
                            rightMargin=24, title=f'DCLD codebook - {scope}')
    data = [[Paragraph(h, head) for h in CODEBOOK_HEADER]]
    style = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f3864')),
             ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#bbbbbb')),
             ('VALIGN', (0, 0), (-1, -1), 'TOP')]
    for title, row in codebook_rows(section):
        if title:
            data.append([Paragraph(f'<b>{escape(pdf_text(title))}</b>', cell)] + [''] * 6)
            r = len(data) - 1
            style += [('SPAN', (0, r), (-1, r)), ('BACKGROUND', (0, r), (-1, r), colors.HexColor('#d9e1f2'))]
        else:
            data.append([Paragraph(escape(pdf_text(v)), cell) for v in row])
    table = Table(data, repeatRows=1, colWidths=[110, 34, 260, 52, 110, 40, 188])
    table.setStyle(TableStyle(style))
    doc.build([Paragraph(f'LIVERCare (DCLD study) codebook - {escape(scope)}', styles['Title']),
               Paragraph(f'Data dictionary version {spec.VERSION} ({spec.VERSION_DATE}). Codes match the "Codes" '
                         'export; the Excel data dictionary has the full detail and open decisions.', styles['Normal']),
               Spacer(1, 8), table])
    return buffer.getvalue()
