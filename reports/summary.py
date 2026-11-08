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
