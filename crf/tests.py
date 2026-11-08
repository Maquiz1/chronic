import datetime
import re
from decimal import Decimal
from io import BytesIO

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from accounts.models import User
from quality import checks
from quality.models import DataQuery

from . import derived, spec
from .dictionary import build_workbook
from .models import SECTION_MODELS, Participant

PASSWORD = 'Liver-Study-2026!'


def make_user(role, email=None):
    return User.objects.create_user(email or f'{role}@example.org', PASSWORD, first_name=role.title(),
                                    last_name='User', role=role, is_active=True, email_verified=True)


class AccountsFlowTests(TestCase):
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_register_confirm_approve_login(self):
        admin = make_user('admin')
        r = self.client.post(reverse('accounts:register'), {
            'first_name': 'Asha', 'last_name': 'M', 'email': 'Asha@Example.org', 'phone': '', 'institution': 'MUHAS',
            'position': 'Resident', 'password1': PASSWORD, 'password2': PASSWORD})
        self.assertContains(r, 'Check your email')
        user = User.objects.get(email='asha@example.org')
        self.assertFalse(user.is_active)
        # Cannot log in before confirming
        r = self.client.post(reverse('login'), {'username': 'asha@example.org', 'password': PASSWORD})
        self.assertContains(r, 'confirmation link')
        link = re.search(r'https?://\S+/accounts/verify/\S+/', mail.outbox[0].body).group(0)
        self.client.get(link.split('localhost:8000')[-1] if 'localhost' in link else link)
        user.refresh_from_db()
        self.assertTrue(user.is_active and user.email_verified)
        self.assertIn(admin.email, mail.outbox[-1].to)  # approver notified
        # Logged in but no role: only the pending page
        self.assertTrue(self.client.login(email='asha@example.org', password=PASSWORD))
        self.assertRedirects(self.client.get(reverse('crf:list')), reverse('accounts:pending'))
        # Admin approves
        self.client.force_login(admin)
        self.client.post(reverse('accounts:user_edit', args=[user.pk]), {
            'first_name': 'Asha', 'last_name': 'M', 'phone': '', 'institution': 'MUHAS', 'position': 'Resident',
            'role': 'data_clerk', 'is_active': 'on'})
        user.refresh_from_db()
        self.assertEqual(user.role, 'data_clerk')
        self.assertEqual(mail.outbox[-1].to, [user.email])
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('crf:list')).status_code, 200)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_and_change(self):
        user = make_user('data_clerk')
        self.client.post(reverse('accounts:password_reset'), {'email': user.email})
        self.assertEqual(len(mail.outbox), 1)
        path = re.search(r'/accounts/reset/\S+/', mail.outbox[0].body).group(0)
        r = self.client.get(path, follow=True)
        self.client.post(r.redirect_chain[-1][0], {'new_password1': 'New-Pass-2026!', 'new_password2': 'New-Pass-2026!'})
        self.assertTrue(self.client.login(email=user.email, password='New-Pass-2026!'))
        r = self.client.post(reverse('accounts:password_change'), {
            'old_password': 'New-Pass-2026!', 'new_password1': 'Third-Pass-2026!', 'new_password2': 'Third-Pass-2026!'})
        self.assertRedirects(r, reverse('accounts:profile'))
        self.assertTrue(User.objects.get(pk=user.pk).check_password('Third-Pass-2026!'))

    def test_data_manager_cannot_create_admins(self):
        dm = make_user('data_manager')
        pending = User.objects.create_user('new@example.org', PASSWORD, first_name='N', last_name='U', is_active=True)
        self.client.force_login(dm)
        self.client.post(reverse('accounts:user_edit', args=[pending.pk]), {
            'first_name': 'N', 'last_name': 'U', 'role': 'admin', 'is_active': 'on'})
        pending.refresh_from_db()
        self.assertEqual(pending.role, '')
        admin = make_user('admin')
        self.assertEqual(self.client.get(reverse('accounts:user_edit', args=[admin.pk])).status_code, 403)


class EntryTests(TestCase):
    def setUp(self):
        self.clerk = make_user('data_clerk')
        self.client.force_login(self.clerk)
        today = timezone.localdate()
        r = self.client.post(reverse('crf:create'), {'hospital_id': 'm10-20-30', 'interview_date': today,
                                                     'admission_date': today - datetime.timedelta(days=2),
                                                     'phone_number': '0712000000'})
        self.p = Participant.objects.get()
        self.assertEqual(self.p.study_id, 'CLD-0001')
        self.assertEqual(self.p.hospital_id, 'M10-20-30')  # stored in capitals
        self.assertRedirects(r, reverse('crf:section', args=[self.p.pk, 'A']))

    def section_url(self, code):
        return reverse('crf:section', args=[self.p.pk, code])

    def test_hospital_id_required_and_unique(self):
        today = timezone.localdate()
        r = self.client.post(reverse('crf:create'), {'interview_date': today})
        self.assertContains(r, 'This field is required')
        r = self.client.post(reverse('crf:create'), {'hospital_id': ' M10 - 20 - 30 ', 'interview_date': today})
        self.assertContains(r, 'is already registered as')
        self.assertContains(r, reverse('crf:detail', args=[self.p.pk]))
        r = self.client.post(reverse('crf:create'), {'hospital_id': '<b>', 'interview_date': today})
        self.assertContains(r, 'Use 3-30 letters')
        self.assertEqual(Participant.objects.count(), 1)
        self.client.post(reverse('crf:create'), {'hospital_id': 'M10-20-31', 'interview_date': today})
        self.assertEqual(Participant.objects.count(), 2)
        r = self.client.get(reverse('crf:list') + '?q=20-31')
        self.assertContains(r, 'CLD-0002')
        self.assertNotContains(r, 'CLD-0001')

    def test_partial_save_then_complete_later(self):
        # Only haemoglobin known today; INR not done; the rest pending.
        r = self.client.post(self.section_url('G'), {'hb': '9.8', 'nd__inr': 'on', 'save': '1'})
        self.assertRedirects(r, reverse('crf:detail', args=[self.p.pk]))
        g = SECTION_MODELS['G'].objects.get(participant=self.p)
        self.assertEqual(g.hb, Decimal('9.8'))
        self.assertEqual(g.not_done, ['inr'])
        status = checks.section_status('G', Participant.objects.get(pk=self.p.pk).values())
        self.assertEqual(status['state'], 'incomplete')
        missing = [f.name for f in status['missing']]
        self.assertIn('platelets', missing)
        self.assertNotIn('inr', missing)
        self.assertNotIn('bilirubin_unit', missing)  # unit only expected once bilirubin is entered
        # Results arrive later
        self.client.post(self.section_url('G'), {'hb': '9.8', 'bilirubin': '68.4', 'bilirubin_unit': '1', 'inr': '1.9'})
        g.refresh_from_db()
        self.assertEqual(g.inr, Decimal('1.90'))
        self.assertEqual(g.not_done, [])

    def test_impossible_value_refused_unit_aware(self):
        r = self.client.post(self.section_url('G'), {'creatinine': '421', 'creatinine_unit': '2'})  # 421 mg/dL
        self.assertContains(r, 'Impossible value')
        self.assertFalse(SECTION_MODELS['G'].objects.exists())
        self.client.post(self.section_url('G'), {'creatinine': '421', 'creatinine_unit': '1'})  # 421 µmol/L is fine
        self.assertEqual(SECTION_MODELS['G'].objects.get().creatinine, Decimal('421.0'))

    def test_skip_rules_clear_hidden_answers(self):
        self.client.post(self.section_url('F'), {'hepatic_enceph': '1', 'he_grade': '3'})
        d = SECTION_MODELS['F'].objects.get()
        self.assertEqual(d.he_grade, 3)
        self.client.post(self.section_url('F'), {'hepatic_enceph': '0', 'he_grade': '3'})
        d.refresh_from_db()
        self.assertIsNone(d.he_grade)

    def test_locked_record_cannot_be_edited(self):
        self.p.lock(make_user('data_manager'))
        r = self.client.post(self.section_url('A'), {'age_years': '40'})
        self.assertRedirects(r, reverse('crf:detail', args=[self.p.pk]))
        self.assertFalse(SECTION_MODELS['A'].objects.exists())

    def test_investigator_sees_no_phone_and_cannot_enter(self):
        self.client.force_login(make_user('investigator'))
        r = self.client.get(reverse('crf:detail', args=[self.p.pk]))
        self.assertNotContains(r, '0712000000')
        self.assertNotContains(r, 'M10-20-30')
        self.assertEqual(self.client.get(self.section_url('A')).status_code, 403)
        r = self.client.post(reverse('exports:start'), {'dataset': 'combined', 'mode': 'codes', 'format': 'xlsx'})
        wb = load_workbook(BytesIO(self.client.get(reverse('exports:download', args=[r.json()['job']])).content))
        header = [c.value for c in wb['all_sections'][1]]
        self.assertNotIn('phone_number', header)
        self.assertNotIn('hospital_id', header)
        r = self.client.post(reverse('exports:start'), {'dataset': 'combined', 'mode': 'codes', 'format': 'xlsx',
                                                        'identifiable': '1'})
        self.assertEqual(r.status_code, 403)

    def test_query_cycle(self):
        dm = make_user('data_manager')
        self.client.force_login(dm)
        self.client.post(reverse('quality:query_create', args=[self.p.pk]),
                         {'section': 'G', 'field': 'inr', 'message': 'Check INR against the lab slip.'})
        q = DataQuery.objects.get()
        self.client.force_login(self.clerk)
        self.client.post(reverse('quality:query_answer', args=[q.pk]), {'response': 'Corrected to 1.9.'})
        q.refresh_from_db()
        self.assertEqual(q.status, 'answered')
        self.assertEqual(self.client.post(reverse('quality:query_close', args=[q.pk])).status_code, 403)
        self.client.force_login(dm)
        self.client.post(reverse('quality:query_close', args=[q.pk]))
        q.refresh_from_db()
        self.assertEqual(q.status, 'closed')

    def test_pages_render(self):
        self.client.post(self.section_url('C'), {'sym_jaundice': 'on', 'symptom_duration_days': '10'})
        self.client.force_login(make_user('admin'))
        for name in ('dashboard', 'crf:list', 'exports:page', 'reports:schedules', 'quality:overview', 'quality:pending', 'quality:issues',
                     'quality:queries', 'accounts:users', 'accounts:roles', 'accounts:profile'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for code in ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'K', 'L'):
            self.assertEqual(self.client.get(self.section_url(code)).status_code, 200, code)
        self.assertEqual(self.client.get(reverse('crf:history', args=[self.p.pk])).status_code, 200)


class ScoreTests(TestCase):
    def test_meld_na_and_child_pugh(self):
        v = {'creatinine': Decimal('1.9'), 'creatinine_unit': 2, 'bilirubin': Decimal('4.2'), 'bilirubin_unit': 2,
             'inr': Decimal('1.6'), 'sodium': 128, 'albumin': Decimal('26'), 'albumin_unit': 1,
             'ascites': 1, 'ascites_grade': 1, 'hepatic_enceph': 1, 'he_grade': 2}
        self.assertEqual(derived.meld(v), 23.3)
        self.assertEqual(derived.meld_na(v), 28)
        # bilirubin 4.2 mg/dL = 3, albumin 2.6 g/dL = 3, INR 1.6 = 1, ascites moderate = 2, HE grade II = 2
        self.assertEqual(derived.cp_score(v), 11)
        self.assertEqual(derived.cp_class(v), 'C')
        self.assertEqual(derived.k_child_c(v), 1)
        self.assertEqual(derived.k_meld15(v), 1)

    def test_v02_scores(self):
        self.assertEqual(derived.cp_ascites_pts({'ascites': 0}), 1)
        self.assertEqual(derived.cp_ascites_pts({'ascites': 1, 'ascites_grade': 2}), 3)
        self.assertIsNone(derived.cp_ascites_pts({'ascites': 1}))
        self.assertEqual(derived.cp_enceph_pts({'hepatic_enceph': 1, 'he_grade': 0}), 1)
        hcc = {'img_hcc': 1, 'hcc_vascular_invasion': 0, 'hcc_extrahepatic': 0}
        self.assertEqual(derived.hcc_milan({**hcc, 'hcc_lesions': 1, 'hcc_size_cm': Decimal('4.5')}), 1)
        self.assertEqual(derived.hcc_milan({**hcc, 'hcc_lesions': 3, 'hcc_size_cm': Decimal('3.5')}), 0)
        self.assertEqual(derived.hcc_milan({**hcc, 'hcc_lesions': 1, 'hcc_size_cm': 2, 'hcc_extrahepatic': 1}), 0)
        self.assertIsNone(derived.hcc_milan({'img_hcc': 0}))
        self.assertEqual(derived.lt_indicated({'k_recurrent_variceal': 1}), 1)
        self.assertIsNone(derived.lt_indicated({'k_recurrent_variceal': 0}))  # scores unknown

    def test_imaging_skip_rule_and_not_done(self):
        today = timezone.localdate()
        self.client.force_login(make_user('data_clerk'))
        self.client.post(reverse('crf:create'), {'hospital_id': 'IMG-01', 'interview_date': today})
        p = Participant.objects.get()
        url = reverse('crf:section', args=[p.pk, 'G'])
        # No modality ticked: imaging findings are cleared and not expected
        self.client.post(url, {'img_hcc': '1', 'nd__img_modality': 'on'})
        g = SECTION_MODELS['G'].objects.get()
        self.assertIsNone(g.img_hcc)
        self.assertIn('img_modality', g.not_done)
        missing = [f.name for f in checks.section_status('G', Participant.objects.get().values())['missing']]
        self.assertNotIn('img_hcc', missing)
        self.assertNotIn('img_modality', missing)
        # Ultrasound done, HCC seen: lesion details become expected
        self.client.post(url, {'img_modality_us': 'on', 'img_hcc': '1'})
        missing = [f.name for f in checks.section_status('G', Participant.objects.get().values())['missing']]
        self.assertIn('hcc_lesions', missing)
        self.assertEqual(SECTION_MODELS['G'].objects.get().img_hcc, 1)

    def test_unit_conversion(self):
        self.assertEqual(derived.creatinine_mgdl({'creatinine': Decimal('88.4'), 'creatinine_unit': 1}), 1.0)
        self.assertEqual(derived.bilirubin_mgdl({'bilirubin': Decimal('34.2'), 'bilirubin_unit': 1}), 2.0)
        self.assertIsNone(derived.meld({'inr': 1}))

    def test_checks_find_contradictions_and_wrong_units(self):
        v = {'interview_date': timezone.localdate(), 'admission_date': timezone.localdate(),
             'hepatic_enceph': 1, 'he_grade': 0, 'hbsag': 1, 'hbv': 0, 'albumin': Decimal('8'), 'albumin_unit': 1,
             'bilirubin': Decimal('2.0'), 'bilirubin_unit': 2, 'direct_bilirubin': Decimal('51'),
             'direct_bilirubin_unit': 1, 'bp_systolic': 90, 'bp_diastolic': 95}
        rules = {i.rule for i in checks.all_issues(v)}
        self.assertIn('he_grade0', rules)
        self.assertIn('hbsag_history', rules)
        self.assertIn('direct_bili', rules)  # 51 µmol/L = 3 mg/dL, above the total of 2 mg/dL
        self.assertIn('bp', rules)
        self.assertIn('check', rules)  # 8 g/L is probably a g/dL value or a typo


class DictionaryTests(TestCase):
    def test_workbook_matches_spec(self):
        wb = build_workbook()
        self.assertEqual(wb.sheetnames, ['README', 'Sections', 'Data Dictionary', 'Choices', 'Derived Scores',
                                         'Reference Ranges', 'Decisions', 'Change Log'])
        names = [r[3] for r in wb['Data Dictionary'].iter_rows(min_row=2, values_only=True)]
        for _s, f in spec.all_fields():
            self.assertIn(f.name, names)
        decisions = {r[0] for r in wb['Decisions'].iter_rows(min_row=3, values_only=True)}
        used = {f.decision for _s, f in spec.all_fields() if f.decision} | {f.decision for f in spec.HEADER if f.decision}
        used |= {d.decision for d in spec.DERIVED if d.decision}
        self.assertFalse(used - decisions, 'Decision IDs used in spec.py but missing from decisions.py')
