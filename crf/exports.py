"""Excel exports: one row per participant.

Three layouts:
  combined  one sheet with every section side by side (default)
  sheets    one workbook, one sheet per section, each starting with the participant columns
  section   one section only (section='A' ... 'L')
Each part has the CRF columns in dictionary order, the calculated values of that part, and quality columns.
"""
from decimal import Decimal

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from quality import checks
from quality.models import DataQuery

from . import derived, spec

HEADER_FILL = PatternFill('solid', fgColor='1F3864')
HEADER_FONT = Font(bold=True, color='FFFFFF')


def _cell(x):
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, Decimal):
        return float(x)
    return x


def _part(code):
    """(crf columns, derived columns) for one section, or for everything when code is None."""
    if code is None:
        return [c for _s, f in spec.all_fields() for c in f.columns], list(derived.CALCULATORS)
    section = spec.SECTION_BY_CODE[code]
    return ([c for f in section.fields for c in f.columns],
            [d.name for d in spec.DERIVED if d.section == code and d.name in derived.CALCULATORS])


class _Rows:
    """Per-participant values, scores and quality, computed once and shared by every sheet."""

    def __init__(self, participants):
        self.items = []
        open_q = {}
        for pid, section in DataQuery.objects.exclude(status=DataQuery.Status.CLOSED).values_list('participant_id', 'section'):
            open_q.setdefault(pid, []).append(section)
        for p in participants:
            v = p.values()
            self.items.append({'p': p, 'v': v, 'status': checks.record_status(v), 'issues': checks.all_issues(v),
                               'scores': derived.compute_all(v), 'queries': open_q.get(p.pk, [])})


def _quality(item, code):
    if code is None:
        sections = [s for s in item['status']['sections'] if s['state'] != 'calculated']
        pct = item['status']['pct']
        issues, queries = item['issues'], item['queries']
    else:
        sections = [s for s in item['status']['sections'] if s['code'] == code]
        pct = sections[0]['pct'] if sections and sections[0]['state'] != 'calculated' else None
        issues = [i for i in item['issues'] if i.section == code]
        queries = [q for q in item['queries'] if q == code]
    missing = [f.name for s in sections for f in s['missing']]
    not_done = [f.name for s in sections for f in s['nd_fields']]
    state = sections[0]['state'] if code is not None and sections else ''
    return [pct, state, len(missing), ', '.join(missing), ', '.join(not_done),
            sum(1 for i in issues if i.level == checks.ERROR), sum(1 for i in issues if i.level == checks.WARNING),
            len(queries)]


QUALITY_COLUMNS = ['completeness_pct', 'section_status', 'missing_count', 'missing_items', 'not_done_items',
                   'checks_errors', 'checks_warnings', 'open_queries']


def _write_sheet(ws, rows, code, identifiable):
    header = ['study_id', 'interview_date', 'admission_date', 'interviewer'] + (
        ['hospital_id', 'phone_number'] if identifiable else [])
    crf_columns, derived_columns = _part(code)
    tail = ['locked', 'last_updated']
    ws.append(header + crf_columns + derived_columns + QUALITY_COLUMNS + tail)
    for cell in ws[1]:
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
    for item in rows.items:
        p, v = item['p'], item['v']
        row = [p.study_id, p.interview_date, p.admission_date, p.interviewer.email]
        if identifiable:
            row += [p.hospital_id, p.phone_number]
        row += [_cell(v.get(c)) for c in crf_columns]
        row += [item['scores'][c] for c in derived_columns]
        row += _quality(item, code)
        row += [int(p.locked), timezone.localtime(p.updated_at).replace(tzinfo=None)]
        ws.append(row)
    ws.freeze_panes = 'B2'


def _notes(wb, identifiable, scope):
    notes = wb.create_sheet('notes')
    for row in [
        ['Exported', timezone.localtime().strftime('%Y-%m-%d %H:%M')],
        ['Contents', scope],
        ['Data dictionary version', spec.VERSION],
        ['Codes', 'See the data dictionary (Choices sheet). Multiple-answer questions are 0/1 columns.'],
        ['Blank cells', 'Not entered yet, skipped by a skip rule, or marked "not done" (listed in not_done_items).'],
        ['Quality columns', 'Completeness and checks for the part shown on the sheet (the whole record on a '
                            'combined sheet, one section on a section sheet).'],
        ['Identifiable', 'Yes (contains hospital IDs and phone numbers): store securely' if identifiable
         else 'No (no hospital IDs or phone numbers)'],
    ]:
        notes.append(row)
    notes.column_dimensions['A'].width = 24
    notes.column_dimensions['B'].width = 100


def export_workbook(participants, identifiable=False, layout='combined', section=None):
    rows = _Rows(participants)
    wb = Workbook()
    if layout == 'section':
        if section not in spec.SECTION_BY_CODE:
            raise ValueError(f'Unknown section {section}')
        s = spec.SECTION_BY_CODE[section]
        wb.active.title = f'section_{section}'
        _write_sheet(wb.active, rows, section, identifiable)
        scope = f'Section {section}: {s.title}'
    elif layout == 'sheets':
        wb.remove(wb.active)
        for s in spec.SECTIONS:
            _write_sheet(wb.create_sheet(f'section_{s.code}'), rows, s.code, identifiable)
        scope = 'All sections, one sheet per section'
    else:
        wb.active.title = 'all_sections'
        _write_sheet(wb.active, rows, None, identifiable)
        scope = 'All sections combined on one sheet'
    _notes(wb, identifiable, scope)
    return wb
