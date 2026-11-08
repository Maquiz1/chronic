import datetime

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from crf.models import Participant
from crf.tests import make_user
from quality.models import DataQuery

from .models import EmailLog
from .summary import week_range
from .tasks import send_pending_reminders, send_progress_report


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ReportTests(TestCase):
    def setUp(self):
        self.clerk = make_user('data_clerk')
        self.other_clerk = make_user('data_clerk', email='other@example.org')
        self.dm = make_user('data_manager')
        self.inv = make_user('investigator')
        self.client.force_login(self.clerk)
        old = timezone.localdate() - datetime.timedelta(days=5)
        self.client.post(reverse('crf:create'), {'hospital_id': 'M90-00-01', 'interview_date': old})
        self.p = Participant.objects.get()

    def test_progress_report_with_pdf(self):
        result = send_progress_report('week')
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, sorted([self.dm.email, self.inv.email]))
        name, content, mimetype = mail.outbox[0].attachments[0]
        self.assertEqual(mimetype, 'application/pdf')
        self.assertEqual(content[:4], b'%PDF')
        self.assertIn('Weekly progress', mail.outbox[0].subject)
        self.assertEqual(EmailLog.objects.filter(sent=True).count(), 2)
        self.assertIn('sent to 2', result)

    def test_month_end_only(self):
        self.assertEqual(send_progress_report('month', month_end_only=True) == 'not the last day of the month',
                         (timezone.localdate() + datetime.timedelta(days=1)).day != 1)

    def test_pending_reminders_go_to_the_right_people(self):
        DataQuery.objects.create(participant=self.p, section='G', message='Check INR', raised_by=self.dm)
        send_pending_reminders()
        to = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(to, sorted([self.clerk.email, self.dm.email]))  # not the other clerk, not investigators
        body = next(m.body for m in mail.outbox if m.to == [self.clerk.email])
        self.assertIn(self.p.study_id, body)
        self.assertIn('Check INR', body)

    def test_week_range(self):
        monday = datetime.date(2026, 11, 9)
        self.assertEqual(week_range(monday), (datetime.date(2026, 11, 2), datetime.date(2026, 11, 8)))
        sunday = datetime.date(2026, 11, 8)
        self.assertEqual(week_range(sunday), (datetime.date(2026, 11, 2), datetime.date(2026, 11, 8)))

    def test_setup_schedules_keeps_admin_changes(self):
        call_command('setup_schedules', stdout=open('/dev/null', 'w'))
        self.assertEqual(PeriodicTask.objects.count(), 4)
        task = PeriodicTask.objects.get(name__startswith='Weekly')
        task.enabled = False
        task.crontab = CrontabSchedule.objects.create(minute='0', hour='9', day_of_week='5')
        task.save()
        call_command('setup_schedules', stdout=open('/dev/null', 'w'))
        task.refresh_from_db()
        self.assertFalse(task.enabled)
        self.assertEqual(task.crontab.hour, '9')
        self.assertEqual(PeriodicTask.objects.count(), 4)

    def test_schedules_page_admin_only(self):
        call_command('setup_schedules', stdout=open('/dev/null', 'w'))
        self.client.force_login(self.dm)
        self.assertEqual(self.client.get(reverse('reports:schedules')).status_code, 403)
        self.client.force_login(make_user('admin'))
        r = self.client.get(reverse('reports:schedules'))
        self.assertContains(r, 'Daily pending work reminder')
        task = PeriodicTask.objects.get(name__startswith='Daily pending')
        self.client.post(reverse('reports:run', args=[task.pk]))
        self.assertTrue(EmailLog.objects.filter(kind='pending_reminder').exists())


class ReportPageTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user('investigator'))
        clerk = make_user('data_clerk')
        c = self.client
        self.client.force_login(clerk)
        today = timezone.localdate()
        for i, days in enumerate((1, 10, 40)):
            c.post(reverse('crf:create'), {'hospital_id': f'M20-00-{i:02d}', 'interview_date': today - datetime.timedelta(days=days)})
        p = Participant.objects.order_by('study_id').first()
        c.post(reverse('crf:section', args=[p.pk, 'G']), {
            'bilirubin': '72', 'bilirubin_unit': '1', 'albumin': '24', 'albumin_unit': '1', 'inr': '1.9',
            'creatinine': '421', 'creatinine_unit': '1', 'sodium': '129'})
        c.post(reverse('crf:section', args=[p.pk, 'F']), {'ascites': '1', 'ascites_grade': '1', 'hepatic_enceph': '0'})
        self.client.force_login(make_user('investigator', email='inv2@example.org'))

    def test_study_progress(self):
        r = self.client.get(reverse('reports:study'))
        self.assertEqual(r.status_code, 200)
        d = r.context['d']
        self.assertEqual(d['total'], 3)
        self.assertEqual(dict(d['child_pugh'])['C'], 1)
        self.assertEqual(sum(d['weekly_counts']), 3)
        self.assertEqual(d['cumulative'][-1], 3)
        self.assertEqual(r.context['charts']['sections']['labels'][0], 'A')
        r = self.client.get(reverse('reports:study') + '?start=' + str(timezone.localdate() - datetime.timedelta(days=7)))
        self.assertEqual(r.context['d']['total'], 1)

    def test_patient_progress_and_pdf(self):
        r = self.client.get(reverse('reports:patients') + '?show=missing&sort=missing')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['rows']), 3)
        self.assertNotContains(r, 'M20-00-0')  # investigators never see hospital IDs
        r = self.client.get(reverse('reports:pdf'))
        self.assertEqual(r.content[:4], b'%PDF')
