import json

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView
from django_celery_beat.models import PeriodicTask

from accounts.mixins import RoleRequiredMixin
from config.celery import app

from .models import EmailLog


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
