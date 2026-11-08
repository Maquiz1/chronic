"""Numbers for the progress and data quality reports."""
import calendar
from collections import Counter
from datetime import timedelta

from django.utils import timezone

from crf import derived, spec
from crf.views import ENTRY_CODES, participants_with_sections
from quality import checks
from quality.models import DataQuery


def week_range(today):
    """Monday-Sunday week ending on the most recent Sunday (today when run on a Sunday, yesterday on a Monday)."""
    end = today - timedelta(days=(today.weekday() + 1) % 7)
    return end - timedelta(days=6), end


def month_range(today):
    return today.replace(day=1), today.replace(day=calendar.monthrange(today.year, today.month)[1])


def is_last_day_of_month(today):
    return (today + timedelta(days=1)).day == 1


def build_summary(start=None, end=None):
    """Whole study, with counts for participants interviewed between start and end (inclusive) when given."""
    participants = list(participants_with_sections())
    items = []
    for p in participants:
        v = p.values()
        items.append((p, v, checks.record_status(v), checks.all_issues(v)))
    in_period = [x for x in items if start and start <= x[0].interview_date <= end]

    per_section = []
    pending = Counter()
    for code in ENTRY_CODES:
        states = [next(s for s in st['sections'] if s['code'] == code) for _p, _v, st, _i in items]
        per_section.append({'code': code, 'title': spec.SECTION_BY_CODE[code].title,
                            'complete': sum(1 for s in states if s['state'] == 'complete'),
                            'incomplete': sum(1 for s in states if s['state'] == 'incomplete'),
                            'not_started': sum(1 for s in states if s['state'] == 'not_started')})
        if code == 'G':
            for s in states:
                for f in s['missing']:
                    pending[f'{f.qn} {f.label}'] += 1

    classes = Counter(derived.cp_class(v) for _p, v, _s, _i in items)
    meld15 = sum(1 for _p, v, _s, _i in items if derived.k_meld15(v) == 1)
    outcomes = Counter(v.get('outcome') for _p, v, _s, _i in items)
    queries = Counter(DataQuery.objects.values_list('status', flat=True))
    total = len(items)
    return {
        'generated': timezone.localtime(), 'start': start, 'end': end,
        'total': total,
        'new': len(in_period),
        'complete': sum(1 for _p, _v, st, _i in items if st['complete']),
        'locked': sum(1 for p, *_ in items if p.locked),
        'avg_pct': round(sum(st['pct'] for _p, _v, st, _i in items) / total) if total else 0,
        'errors': sum(1 for *_x, issues in items for i in issues if i.level == checks.ERROR),
        'warnings': sum(1 for *_x, issues in items for i in issues if i.level == checks.WARNING),
        'per_section': per_section,
        'pending_labs': pending.most_common(8),
        'child_pugh': {c: classes.get(c, 0) for c in ('A', 'B', 'C')},
        'child_pugh_unknown': classes.get(None, 0),
        'meld15': meld15,
        'discharged': outcomes.get(1, 0), 'died': outcomes.get(2, 0),
        'queries_open': queries.get('open', 0), 'queries_answered': queries.get('answered', 0),
        'queries_closed': queries.get('closed', 0),
    }


def build_pdf(summary, title):
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=30, bottomMargin=30, title=title)
    grid = TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f3864')),
                       ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                       ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#bbbbbb')),
                       ('FONTSIZE', (0, 0), (-1, -1), 8.5), ('ALIGN', (1, 1), (-1, -1), 'RIGHT')])
    s = summary
    key = [['Measure', 'Number'],
           ['Participants registered (total)', s['total']]]
    if s['start']:
        key.append([f'Interviewed {s["start"]:%d %b} - {s["end"]:%d %b %Y}', s['new']])
    key += [['Complete records', s['complete']], ['Verified and locked', s['locked']],
            ['Average completeness', f'{s["avg_pct"]}%'], ['Check errors / warnings', f'{s["errors"]} / {s["warnings"]}'],
            ['Queries open / answered / closed', f'{s["queries_open"]} / {s["queries_answered"]} / {s["queries_closed"]}'],
            ['Child-Pugh A / B / C (not yet calculable)', f'{s["child_pugh"]["A"]} / {s["child_pugh"]["B"]} / '
                                                          f'{s["child_pugh"]["C"]} ({s["child_pugh_unknown"]})'],
            ['MELD-Na >= 15', s['meld15']], ['Discharged alive / died', f'{s["discharged"]} / {s["died"]}']]
    sections = [['Section', 'Complete', 'Incomplete', 'Not started']] + [
        [f'{r["code"]}: {r["title"]}', r['complete'], r['incomplete'], r['not_started']] for r in s['per_section']]
    story = [Paragraph(title, styles['Title']),
             Paragraph(f'Generated {s["generated"]:%d %b %Y %H:%M}', styles['Normal']), Spacer(1, 10),
             Table(key, colWidths=[300, 150], style=grid), Spacer(1, 14),
             Paragraph('Completeness by section', styles['Heading3']),
             Table(sections, colWidths=[270, 60, 60, 60], style=grid)]
    if s['pending_labs']:
        from crf.dictionary import pdf_text
        story += [Spacer(1, 14), Paragraph('Laboratory results still pending (most frequent)', styles['Heading3']),
                  Table([['Test', 'Participants']] + [[pdf_text(k), n] for k, n in s['pending_labs']], colWidths=[300, 150],
                        style=grid)]
    doc.build(story)
    return buffer.getvalue()


MELD_BINS = [(0, 9, '< 10'), (10, 14, '10-14'), (15, 19, '15-19'), (20, 24, '20-24'), (25, 29, '25-29'),
             (30, 99, '30+')]


def progress_data(start=None, end=None):
    """Everything the Reports pages show, for participants interviewed between start and end (all when blank)."""
    from collections import OrderedDict

    from django.conf import settings

    from quality.models import DataQuery

    qs = participants_with_sections()
    if start:
        qs = qs.filter(interview_date__gte=start)
    if end:
        qs = qs.filter(interview_date__lte=end)
    open_q = Counter(DataQuery.objects.exclude(status=DataQuery.Status.CLOSED).values_list('participant_id', flat=True))
    patients = []
    for p in qs.order_by('interview_date', 'study_id'):
        v = p.values()
        st = checks.record_status(v)
        issues = checks.all_issues(v)
        patients.append({
            'p': p, 'pct': st['pct'], 'done': st['done'], 'expected': st['expected'],
            'missing': st['missing_count'], 'complete': st['complete'],
            'sections': [s for s in st['sections'] if s['state'] != 'calculated'],
            'errors': sum(1 for i in issues if i.level == checks.ERROR),
            'warnings': sum(1 for i in issues if i.level == checks.WARNING),
            'queries': open_q.get(p.pk, 0),
            'cp_class': derived.cp_class(v), 'meld_na': derived.meld_na(v), 'lt': derived.lt_indicated(v),
            'outcome': v.get('outcome'),
        })
    total = len(patients)

    # Recruitment per week (Monday start), with no gaps between the first and last week.
    weekly = OrderedDict()
    if patients:
        first = min(x['p'].interview_date for x in patients)
        last = max(x['p'].interview_date for x in patients)
        week = first - timedelta(days=first.weekday())
        while week <= last:
            weekly[week] = 0
            week += timedelta(days=7)
        for x in patients:
            d = x['p'].interview_date
            weekly[d - timedelta(days=d.weekday())] += 1
    cumulative, running = [], 0
    for n in weekly.values():
        running += n
        cumulative.append(running)

    sections = []
    for code in ENTRY_CODES:
        states = [next(s for s in x['sections'] if s['code'] == code) for x in patients]
        complete = sum(1 for s in states if s['state'] == 'complete')
        missing_items = sum(len(s['missing']) for s in states)
        sections.append({'code': code, 'title': spec.SECTION_BY_CODE[code].title, 'complete': complete,
                         'incomplete': sum(1 for s in states if s['state'] == 'incomplete'),
                         'not_started': sum(1 for s in states if s['state'] == 'not_started'),
                         'missing_items': missing_items,
                         'pct': round(sum(s['pct'] for s in states) / total) if total else 0})

    cp = Counter(x['cp_class'] for x in patients)
    meld_bins = [(label, sum(1 for x in patients if x['meld_na'] is not None and lo <= x['meld_na'] <= hi))
                 for lo, hi, label in MELD_BINS]
    lt = Counter(x['lt'] for x in patients)
    outcome = Counter(x['outcome'] for x in patients)
    target = getattr(settings, 'STUDY_TARGET', 0)
    return {
        'start': start, 'end': end, 'total': total, 'target': target,
        'target_pct': min(100, round(100 * total / target)) if target else None,
        'complete': sum(1 for x in patients if x['complete']),
        'locked': sum(1 for x in patients if x['p'].locked),
        'avg_pct': round(sum(x['pct'] for x in patients) / total) if total else 0,
        'missing_items': sum(x['missing'] for x in patients),
        'with_missing': sum(1 for x in patients if x['missing']),
        'errors': sum(x['errors'] for x in patients), 'warnings': sum(x['warnings'] for x in patients),
        'open_queries': sum(x['queries'] for x in patients),
        'weekly_labels': [w.strftime('%d %b %Y') for w in weekly], 'weekly_counts': list(weekly.values()),
        'cumulative': cumulative,
        'sections': sections,
        'child_pugh': [('A', cp.get('A', 0)), ('B', cp.get('B', 0)), ('C', cp.get('C', 0))],
        'child_pugh_unknown': cp.get(None, 0),
        'meld_bins': meld_bins, 'meld_unknown': sum(1 for x in patients if x['meld_na'] is None),
        'lt_yes': lt.get(1, 0), 'lt_no': lt.get(0, 0), 'lt_unknown': lt.get(None, 0),
        'discharged': outcome.get(1, 0), 'died': outcome.get(2, 0), 'outcome_unknown': outcome.get(None, 0),
        'patients': patients,
    }
