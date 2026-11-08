import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from reports.schedules import SCHEDULES


class Command(BaseCommand):
    help = ('Create the scheduled tasks (report emails, reminders, export clean-up). Existing tasks keep the '
            'schedule and on/off state set in Django admin.')

    def handle(self, *args, **options):
        for name, task_path, kwargs, (minute, hour, day_of_month, day_of_week), description in SCHEDULES:
            task = PeriodicTask.objects.filter(name=name).first()
            if task:
                task.task, task.kwargs, task.description = task_path, json.dumps(kwargs), description
                task.save(update_fields=['task', 'kwargs', 'description'])
                self.stdout.write(f'Kept schedule: {task.name} -> {task.crontab}')
                continue
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=minute, hour=hour, day_of_month=day_of_month, day_of_week=day_of_week, month_of_year='*',
                timezone=settings.TIME_ZONE)
            PeriodicTask.objects.create(name=name, task=task_path, kwargs=json.dumps(kwargs), crontab=schedule,
                                        description=description, enabled=True)
            self.stdout.write(self.style.SUCCESS(f'Created: {name} -> {schedule}'))
