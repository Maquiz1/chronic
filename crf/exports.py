"""Excel export: one row per participant, CRF columns in dictionary order, then calculated values and quality."""
from decimal import Decimal

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from quality import checks
from quality.models import DataQuery

from . import derived, spec


def export_workbook(participants, identifiable=False):
    wb = Workbook()
    ws = wb.active
    ws.title = 'data'

    header = ['study_id', 'interview_date', 'admission_date', 'interviewer']
    if identifiable:
        header.append('phone_number')
    crf_columns = [c for _s, f in spec.all_fields() for c in f.columns]
    derived_columns = list(derived.CALCULATORS)
    quality_columns = ['completeness_pct', 'missing_items', 'not_done_items', 'checks_errors', 'checks_warnings', 'open_queries',
                       'locked', 'last_updated']
    columns = header + crf_columns + derived_columns + quality_columns
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1F3864')

    open_counts = {}
    for pid in DataQuery.objects.exclude(status=DataQuery.Status.CLOSED).values_list('participant_id', flat=True):
        open_counts[pid] = open_counts.get(pid, 0) + 1

    for p in participants:
        v = p.values()
        status = checks.record_status(v)
        issues = checks.all_issues(v)
        scores = derived.compute_all(v)
        row = [p.study_id, p.interview_date, p.admission_date, p.interviewer.email]
        if identifiable:
            row.append(p.phone_number)
        for c in crf_columns:
            x = v.get(c)
            if isinstance(x, bool):
                x = int(x)
            elif isinstance(x, Decimal):
                x = float(x)
            row.append(x)
        row += [scores[c] for c in derived_columns]
        not_done = [f.name for sec in status['sections'] for f in sec['nd_fields']]
        row += [status['pct'], status['missing_count'], ', '.join(not_done), sum(1 for i in issues if i.level == checks.ERROR),
                sum(1 for i in issues if i.level == checks.WARNING), open_counts.get(p.pk, 0), int(p.locked),
                timezone.localtime(p.updated_at).replace(tzinfo=None)]
        ws.append(row)
    ws.freeze_panes = 'B2'

    notes = wb.create_sheet('notes')
    notes.append(['Data dictionary version', spec.VERSION])
    notes.append(['Codes', 'See the data dictionary (Choices sheet). Multiple-answer questions are 0/1 columns.'])
    notes.append(['Blank cells', 'Not entered yet, skipped by a skip rule, or marked "not done". See the data quality '
                                 'pages for which.'])
    notes.append(['Identifiable', 'Yes (contains phone numbers): store securely' if identifiable else 'No'])
    return wb
