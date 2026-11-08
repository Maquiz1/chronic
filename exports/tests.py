import csv
import datetime
import io
from io import BytesIO

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from crf import spec
from crf.models import Participant
from crf.tests import make_user

from .models import ExportJob


class ExportTests(TestCase):
    def setUp(self):
        self.dm = make_user('data_manager')
        self.client.force_login(self.dm)
        today = timezone.localdate()
        self.client.post(reverse('crf:create'), {'hospital_id': 'M01-02-03', 'interview_date': today,
                                                 'admission_date': today - datetime.timedelta(days=1),
                                                 'phone_number': '0712000000'})
        self.p = Participant.objects.get()
        self.client.post(reverse('crf:section', args=[self.p.pk, 'G']), {'hb': '9.8', 'inr': '1.9', 'nd__ggt': 'on'})
        self.client.post(reverse('crf:section', args=[self.p.pk, 'F']), {'hepatic_enceph': '1', 'he_grade': '2'})

    def export(self, **params):
        r = self.client.post(reverse('exports:start'), {'mode': 'codes', 'format': 'xlsx', **params})
        self.assertEqual(r.status_code, 200, r.content)
        status = self.client.get(r.json()['status_url']).json()
        self.assertEqual(status['status'], 'done')  # tasks run immediately in tests
        return self.client.get(status['file'])

    def test_section_codes_and_labels(self):
        wb = load_workbook(BytesIO(self.export(dataset='G').content))
        self.assertEqual(wb.sheetnames, ['section_G', 'notes'])
        header = [c.value for c in wb['section_G'][1]]
        self.assertIn('inr', header)
        self.assertIn('apri', header)
        self.assertNotIn('age_years', header)
        row = dict(zip(header, [c.value for c in wb['section_G'][2]]))
        self.assertEqual(row['inr'], 1.9)
        self.assertEqual(row['not_done_items'], 'ggt')
        wb = load_workbook(BytesIO(self.export(dataset='F', mode='labels').content))
        header = [c.value for c in wb['section_F'][1]]
        row = dict(zip(header, [c.value for c in wb['section_F'][2]]))
        self.assertEqual(row['F9 Hepatic encephalopathy'], 'Present')
        self.assertEqual(row['F9a If present: grade (West Haven)'], 'Grade II')

    def test_all_combined_csv_and_identifiable(self):
        wb = load_workbook(BytesIO(self.export(dataset='all', format='csv').content))  # "all" is always Excel
        self.assertEqual(wb.sheetnames, [f'section_{s.code}' for s in spec.SECTIONS] + ['notes'])
        self.assertIn('meld_na', [c.value for c in wb['section_J'][1]])
        r = self.export(dataset='combined', format='csv', identifiable='1')
        self.assertTrue(r['Content-Disposition'].endswith('.csv"'))
        rows = list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
        self.assertIn('hospital_id', rows[0])
        self.assertIn('age_years', rows[0])
        self.assertEqual(rows[1][rows[0].index('hospital_id')], 'M01-02-03')

    def test_only_owner_downloads_and_bad_requests(self):
        r = self.client.post(reverse('exports:start'), {'dataset': 'G', 'mode': 'codes', 'format': 'xlsx'})
        job = r.json()['job']
        self.client.force_login(make_user('investigator'))
        self.assertEqual(self.client.get(reverse('exports:download', args=[job])).status_code, 404)
        r = self.client.post(reverse('exports:start'), {'dataset': 'Z', 'mode': 'codes', 'format': 'xlsx'})
        self.assertEqual(r.status_code, 400)
        self.client.force_login(make_user('data_clerk'))
        self.assertEqual(self.client.post(reverse('exports:start'), {'dataset': 'G'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('exports:page')).status_code, 200)  # codebooks only

    def test_expired_exports_deleted(self):
        self.export(dataset='G')
        ExportJob.objects.update(created_at=timezone.now() - datetime.timedelta(hours=25))
        from .tasks import delete_expired_exports
        self.assertEqual(delete_expired_exports(), 1)

    def test_codebooks(self):
        r = self.client.get(reverse('exports:codebook', args=['G', 'pdf']))
        self.assertEqual(r.content[:4], b'%PDF')
        self.assertIn('Codebook_v', r['Content-Disposition'])
        wb = load_workbook(BytesIO(self.client.get(reverse('exports:codebook', args=['G', 'xlsx'])).content))
        self.assertEqual({row[1] for row in wb['Data Dictionary'].iter_rows(min_row=2, values_only=True)}, {'G'})
        self.assertIn('Reference Ranges', wb.sheetnames)
        wb = load_workbook(BytesIO(self.client.get(reverse('exports:codebook', args=['a', 'xlsx'])).content))
        self.assertNotIn('Reference Ranges', wb.sheetnames)
        self.assertEqual(self.client.get(reverse('exports:codebook', args=['all', 'pdf'])).status_code, 200)
        self.assertEqual(self.client.get(reverse('exports:codebook', args=['Q', 'pdf'])).status_code, 404)
