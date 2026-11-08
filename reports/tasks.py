import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from crf.views import participants_with_sections
from quality import checks
from quality.models import DataQuery

from .models import EmailLog
from .summary import build_pdf, build_summary, is_last_day_of_month, month_range, week_range

logger = logging.getLogger(__name__)

PERIODS = {'week': 'Weekly', 'month': 'Monthly', 'overall': 'Overall'}


def _active(qs):
    return qs.filter(is_active=True).exclude(email='')


def report_recipients():
    """Data Managers, Investigators and Admins (and superusers)."""
    return list(_active(User.objects.filter(Q(role__in=['data_manager', 'investigator', 'admin']) | Q(is_superuser=True))))


def send_email(kind, user, subject, template, context, attachment=None):
    context = {**context, 'user': user, 'SITE_NAME': settings.SITE_NAME, 'SITE_URL': settings.SITE_URL}
    subject = f'[{settings.SITE_NAME}] {subject}'
    message = EmailMultiAlternatives(subject, render_to_string(f'emails/{template}.txt', context), None, [user.email])
    try:
        message.attach_alternative(render_to_string(f'emails/{template}.html', context), 'text/html')
    except Exception:  # an HTML version is optional
        pass
    if attachment:
        message.attach(*attachment)
    log = EmailLog(kind=kind, to=user.email, subject=subject[:255])
    try:
        message.send()
        log.sent = True
    except Exception as exc:
        logger.exception('Email %s to %s failed', kind, user.email)
        log.error = str(exc)[:2000]
    log.save()
    return log.sent


@shared_task
def send_progress_report(period='week', month_end_only=False):
    """Progress and data quality report with a PDF, to Data Managers, Investigators and Admins.

    month_end_only: send only on the last day of the month (crontab cannot say "last day", so the schedule runs on
    days 28-31 and this skips the others).
    """
    if period not in PERIODS:
        raise ValueError(f'Unknown period {period!r}')
    today = timezone.localdate()
    if month_end_only and not is_last_day_of_month(today):
        return 'not the last day of the month'
    start, end = {'week': week_range, 'month': month_range}.get(period, lambda d: (None, None))(today)
    summary = build_summary(start, end)
    when = {'week': f'{start:%d %b} - {end:%d %b %Y}' if start else '', 'month': f'{start:%B %Y}' if start else '',
            'overall': f'as of {today:%d %b %Y}'}[period]
    title = f'{PERIODS[period]} progress and data quality report ({when})'
    pdf = build_pdf(summary, title)
    context = {'s': summary, 'title': title, 'period': period,
               'links': {'dashboard': settings.SITE_URL + reverse('dashboard'),
                         'quality': settings.SITE_URL + reverse('quality:overview'),
                         'pending': settings.SITE_URL + reverse('quality:pending'),
                         'queries': settings.SITE_URL + reverse('quality:queries')}}
    sent = 0
    for user in report_recipients():
        sent += send_email(f'progress_{period}', user, title, 'progress_report', context,
                           (f'dcld_{period}_report_{today:%Y%m%d}.pdf', pdf, 'application/pdf'))
    return f'{title}: sent to {sent}'


def _pending_items(participants, older_than):
    """Unlocked records interviewed on or before `older_than` that still have missing items."""
    out = []
    for p in participants:
        if p.locked or p.interview_date > older_than:
            continue
        status = checks.record_status(p.values())
        if status['missing_count']:
            labs = [f.qn for s in status['sections'] if s['code'] == 'G' for f in s['missing']]
            started = [s['code'] for s in status['sections'] if s['state'] == 'not_started']
            out.append({'p': p, 'pct': status['pct'], 'missing': status['missing_count'], 'labs': labs,
                        'not_started': started,
                        'url': settings.SITE_URL + reverse('crf:detail', args=[p.pk])})
    return out


@shared_task
def send_pending_reminders():
    """Daily: each Data Clerk gets their own unfinished records and open queries; Data Managers get everything,
    plus answered queries waiting to be closed. Nobody is emailed when there is nothing to do."""
    older_than = timezone.localdate() - timedelta(days=settings.PENDING_REMINDER_DAYS)
    participants = list(participants_with_sections())
    pending = _pending_items(participants, older_than)
    open_q = list(DataQuery.objects.filter(status=DataQuery.Status.OPEN).select_related('participant'))
    answered_q = list(DataQuery.objects.filter(status=DataQuery.Status.ANSWERED).select_related('participant'))
    sent = 0
    for user in _active(User.objects.filter(role__in=['data_clerk', 'data_manager'])):
        if user.role == 'data_clerk':
            mine = [x for x in pending if user.pk in (x['p'].created_by_id, x['p'].interviewer_id)]
            mine_ids = {x['p'].pk for x in mine} | {p.pk for p in participants
                                                     if user.pk in (p.created_by_id, p.interviewer_id)}
            queries = [q for q in open_q if q.participant_id in mine_ids]
            to_close = []
        else:
            mine, queries, to_close = pending, open_q, answered_q
        if not (mine or queries or to_close):
            continue
        context = {'pending': mine, 'queries': queries, 'to_close': to_close, 'days': settings.PENDING_REMINDER_DAYS,
                   'pending_url': settings.SITE_URL + reverse('quality:pending'),
                   'queries_url': settings.SITE_URL + reverse('quality:queries')}
        subject = f'{len(mine)} record(s) to complete, {len(queries)} open query(ies)'
        if to_close:
            subject += f', {len(to_close)} to close'
        sent += send_email('pending_reminder', user, subject, 'pending_reminder', context)
    return f'pending reminders sent to {sent}'
