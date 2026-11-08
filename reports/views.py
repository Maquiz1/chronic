import datetime
import json

from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView
from django_celery_beat.models import PeriodicTask

from accounts.mixins import RoleRequiredMixin
from config.celery import app

from .models import EmailLog
from .summary import build_pdf, build_summary, progress_data


class ScheduleListView(RoleRequiredMixin, TemplateView):
    action = 'manage_tasks'
    template_name = 'reports/schedules.html'

    def get_context_data(self, **kwargs):
        tasks = PeriodicTask.objects.exclude(name__startswith='celery.').select_related('crontab').order_by('name')
        return {**super().get_context_data(**kwargs), 'tasks': tasks, 'emails': EmailLog.objects.all()[:50]}


class RunTaskNowView(RoleRequiredMixin, View):
    action = 'manage_tasks'

    def post(self, request, pk):
        task = get_object_or_404(PeriodicTask, pk=pk)
        kwargs = json.loads(task.kwargs or '{}')
        kwargs.pop('month_end_only', None)  # "run now" means now
        registered = app.tasks.get(task.task)
        if registered is not None:
            registered.delay(**kwargs)
        else:  # a task only the worker knows about
            app.send_task(task.task, kwargs=kwargs)
        messages.success(request, f'"{task.name}" was queued. Emails appear in the log below within a minute.')
        return redirect('reports:schedules')


def _period(request):
    """(start, end, error) from ?start=YYYY-MM-DD&end=YYYY-MM-DD."""
    out = []
    for key in ('start', 'end'):
        raw = request.GET.get(key, '').strip()
        try:
            out.append(datetime.date.fromisoformat(raw) if raw else None)
        except ValueError:
            out.append(None)
    return out[0], out[1]


class ReportMixin(RoleRequiredMixin):
    action = 'view_data'

    def period_context(self):
        start, end = _period(self.request)
        today = timezone.localdate()
        presets = [('All time', None, None),
                   ('Last 7 days', today - datetime.timedelta(days=6), today),
                   ('Last 30 days', today - datetime.timedelta(days=29), today),
                   ('This month', today.replace(day=1), today)]
        return start, end, presets


class StudyProgressView(ReportMixin, TemplateView):
    """Overall study progress and progress by section: cards, charts and tables."""

    template_name = 'reports/study_progress.html'

    def get_context_data(self, **kwargs):
        start, end, presets = self.period_context()
        data = progress_data(start, end)
        charts = {
            'weekly': {'labels': data['weekly_labels'], 'counts': data['weekly_counts'], 'cumulative': data['cumulative']},
            'sections': {'labels': [f"{s['code']}" for s in data['sections']],
                         'titles': [s['title'] for s in data['sections']],
                         'complete': [s['complete'] for s in data['sections']],
                         'incomplete': [s['incomplete'] for s in data['sections']],
                         'error': [s['error'] for s in data['sections']],
                         'not_started': [s['not_started'] for s in data['sections']]},
            'child_pugh': {'labels': [c for c, _n in data['child_pugh']], 'counts': [n for _c, n in data['child_pugh']]},
            'meld': {'labels': [b for b, _n in data['meld_bins']], 'counts': [n for _b, n in data['meld_bins']]},
        }
        return {**super().get_context_data(**kwargs), 'd': data, 'charts': charts, 'start': start, 'end': end,
                'presets': presets}


class PatientProgressView(ReportMixin, TemplateView):
    """Progress of every participant: completeness per section, missing items, checks, queries and scores."""

    template_name = 'reports/patient_progress.html'
    SORTS = {'pct': lambda x: (x['pct'], x['p'].study_id), 'missing': lambda x: (-x['missing'], x['p'].study_id),
             'date': lambda x: (x['p'].interview_date, x['p'].study_id), 'id': lambda x: x['p'].study_id}

    def get_context_data(self, **kwargs):
        start, end, presets = self.period_context()
        data = progress_data(start, end)
        rows = data['patients']
        show = self.request.GET.get('show', 'all')
        if show == 'missing':
            rows = [x for x in rows if x['missing']]
        elif show == 'complete':
            rows = [x for x in rows if x['complete']]
        sort = self.request.GET.get('sort', 'pct')
        rows = sorted(rows, key=self.SORTS.get(sort, self.SORTS['pct']))
        return {**super().get_context_data(**kwargs), 'd': data, 'rows': rows, 'show': show, 'sort': sort,
                'start': start, 'end': end, 'presets': presets,
                'section_codes': [s['code'] for s in data['sections']]}


class ReportPdfView(ReportMixin, View):
    def get(self, request):
        start, end = _period(request)
        if start and not end:
            end = timezone.localdate()
        when = f'{start:%d %b %Y} - {end:%d %b %Y}' if start else f'as of {timezone.localdate():%d %b %Y}'
        pdf = build_pdf(build_summary(start, end), f'Progress and data quality report ({when})')
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="dcld_progress_{timezone.localdate():%Y%m%d}.pdf"'
        return response
