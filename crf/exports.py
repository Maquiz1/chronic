"""Study data exports, one row per participant.

Datasets (key -> what is exported):
  A ... L     one CRF section
  combined    every section side by side on one sheet
  all         one Excel workbook, one sheet per section
Values: "codes" (numbers, variable names as column names: for Stata / R / SPSS, see the codebook) or
"labels" (readable answers, question labels as column names). Format: CSV or Excel ("all" is always Excel).
Each part has its CRF columns in dictionary order, its calculated values and completeness / check columns.
"""
import csv
from decimal import Decimal

from django.utils import timezone
from openpyxl import Workbook

from quality import checks
from quality.models import DataQuery

from . import derived, spec

MODES = {'labels': 'Labels (readable answers)', 'codes': 'Codes (numeric values)'}
FORMATS = {'xlsx': 'Excel', 'csv': 'CSV'}

QUALITY_COLUMNS = [('completeness_pct', 'Completeness %'), ('section_status', 'Status'),
                   ('missing_count', 'Missing items (number)'), ('missing_items', 'Missing items'),
                   ('not_done_items', 'Not done items'), ('checks_errors', 'Check errors'),
                   ('checks_warnings', 'Check warnings'), ('open_queries', 'Open queries')]
DERIVED_BY_NAME = {d.name: d for d in spec.DERIVED}


def datasets():
    """[(key, label)] in page order."""
    return [(s.code, f'Section {s.code}: {s.title}') for s in spec.SECTIONS]


def dataset_label(key):
    if key == 'all':
        return 'All sections (one sheet per section)'
    if key == 'combined':
        return 'All sections combined (one sheet)'
    return dict(datasets()).get(key)


def _part(code):
    """[(column, Field or None, option label)], [derived names] for a section, or everything when code is None."""
    sections = spec.SECTIONS if code is None else [spec.SECTION_BY_CODE[code]]
    columns = []
    for s in sections:
        for f in s.fields:
            if f.type == 'select_multiple':
                columns += [(c, f, label) for c, (_code, label) in zip(f.columns, spec.CHOICES[f.choices])]
            else:
                columns.append((f.name, f, None))
    names = [n for n in derived.CALCULATORS if code is None or DERIVED_BY_NAME[n].section == code]
    return columns, names


def _header(code, mode, identifiable):
    lead = [('study_id', 'Study ID'), ('interview_date', 'Date of interview'),
            ('admission_date', 'Date of admission'), ('interviewer', 'Interviewer')]
    if identifiable:
        lead += [('hospital_id', 'Hospital ID'), ('phone_number', 'Phone number')]
    columns, names = _part(code)
    crf = []
    for column, f, option in columns:
        label = f'{f.qn} {f.label}' + (f': {option}' if option else '')
        crf.append((column, label))
    der = [(n, DERIVED_BY_NAME[n].label) for n in names]
    tail = [('locked', 'Verified and locked'), ('last_updated', 'Last updated')]
    pick = 1 if mode == 'labels' else 0
    return [h[pick] for h in lead + crf + der + QUALITY_COLUMNS + tail]


def _value(x, f, option, mode):
    if isinstance(x, bool):
        if mode == 'labels':
            return 'Yes' if x else 'No'
        return int(x)
    if x is None:
        return ''
    if mode == 'labels' and f is not None and f.type == 'select_one':
        return spec.choice_label(f.choices, x)
    if isinstance(x, Decimal):
        return float(x)
    return x


STATE_LABELS = {'complete': 'Complete', 'incomplete': 'Incomplete', 'not_started': 'Not started',
                'calculated': 'Calculated'}


def _quality(item, code, mode):
    if code is None:
        sections = [s for s in item['status']['sections'] if s['state'] != 'calculated']
        pct, issues, queries, state = item['status']['pct'], item['issues'], item['queries'], ''
    else:
        sections = [s for s in item['status']['sections'] if s['code'] == code]
        state = sections[0]['state'] if sections else ''
        pct = sections[0]['pct'] if sections and state != 'calculated' else ''
        issues = [i for i in item['issues'] if i.section == code]
        queries = [q for q in item['queries'] if q == code]
    missing = [f.name for s in sections for f in s['missing']]
    not_done = [f.name for s in sections for f in s['nd_fields']]
    if mode == 'labels':
        missing = [f'{f.qn} {f.label}' for s in sections for f in s['missing']]
        not_done = [f'{f.qn} {f.label}' for s in sections for f in s['nd_fields']]
        state = STATE_LABELS.get(state, state)
    return [pct, state, len(missing), '; '.join(missing), '; '.join(not_done),
            sum(1 for i in issues if i.level == checks.ERROR), sum(1 for i in issues if i.level == checks.WARNING),
            len(queries)]


def collect(participants):
    """Values, scores and quality per participant, computed once and shared by every sheet."""
    open_q = {}
    for pid, section in DataQuery.objects.exclude(status=DataQuery.Status.CLOSED).values_list('participant_id', 'section'):
        open_q.setdefault(pid, []).append(section)
    items = []
    for p in participants:
        v = p.values()
        items.append({'p': p, 'v': v, 'status': checks.record_status(v), 'issues': checks.all_issues(v),
                      'scores': derived.compute_all(v), 'queries': open_q.get(p.pk, [])})
    return items


def _rows(items, code, mode, identifiable):
    columns, names = _part(code)
    for item in items:
        p, v = item['p'], item['v']
        row = [p.study_id, p.interview_date, p.admission_date or '', p.interviewer.email]
        if identifiable:
            row += [p.hospital_id or '', p.phone_number]
        row += [_value(v.get(column), f, option, mode) for column, f, option in columns]
        row += ['' if item['scores'][n] is None else item['scores'][n] for n in names]
        row += _quality(item, code, mode)
        row += [('Yes' if p.locked else 'No') if mode == 'labels' else int(p.locked),
                timezone.localtime(p.updated_at).replace(tzinfo=None)]
        yield row


def sheets(items, key, mode='codes', identifiable=False):
    """[(sheet title, header, rows)] for a dataset key."""
    if key == 'all':
        codes = [s.code for s in spec.SECTIONS]
    elif key == 'combined':
        return [('all_sections', _header(None, mode, identifiable), _rows(items, None, mode, identifiable))]
    elif key in spec.SECTION_BY_CODE:
        codes = [key]
    else:
        raise ValueError(f'Unknown dataset {key}')
    return [(f'section_{c}', _header(c, mode, identifiable), _rows(items, c, mode, identifiable)) for c in codes]


def notes_rows(key, mode, identifiable):
    return [
        ['Exported', timezone.localtime().strftime('%Y-%m-%d %H:%M')],
        ['Contents', dataset_label(key)],
        ['Values', MODES[mode]],
        ['Data dictionary version', spec.VERSION],
        ['Codes', 'See the codebook / data dictionary. Multiple-answer questions are one 0/1 column per option.'],
        ['Blank cells', 'Not entered yet, skipped by a skip rule, or marked "not done" (listed in the not done column).'],
        ['Identifiable', 'Yes (hospital IDs and phone numbers): store securely' if identifiable
         else 'No (no hospital IDs or phone numbers)'],
    ]


def write_xlsx(target, sheet_list, notes=None, progress=None):
    """Write-only workbook (low memory). Returns the number of data rows written."""
    wb = Workbook(write_only=True)
    count = 0
    for title, header, rows in sheet_list:
        ws = wb.create_sheet(title=title[:31])
        ws.append(header)
        for row in rows:
            ws.append(row)
            count += 1
            if progress:
                progress(count)
    if notes:
        ws = wb.create_sheet('notes')
        for row in notes:
            ws.append(row)
    wb.save(target)
    return count


def write_csv(target, sheet_list, progress=None):
    """target: a text file object. CSV holds one sheet only."""
    (_title, header, rows), = sheet_list
    writer = csv.writer(target)
    writer.writerow(header)
    count = 0
    for row in rows:
        writer.writerow(row)
        count += 1
        if progress:
            progress(count)
    return count
