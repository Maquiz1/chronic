import datetime
import re
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from accounts.models import User
from accounts.roles import set_roles, user_can
from quality import checks
from quality.models import DataQuery

from . import derived, spec
from .dictionary import build_workbook
from .models import SECTION_MODELS, Participant

PASSWORD = 'Liver-Study-2026!'


def make_user(*roles, email=None):
    """Active user holding the given roles: make_user('data_manager'), make_user('data_clerk', 'investigator')."""
    user = User.objects.create_user(email or f'{"_".join(roles)}@example.org', PASSWORD, first_name=roles[0].title(),
                                    last_name='User', is_active=True, email_verified=True)
    set_roles(user, roles)
    return user


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
        self.assertIn('Muhimbili National Hospital', mail.outbox[0].body)  # every email says what the study is
        self.assertIn(f'[{settings.SITE_NAME}]', mail.outbox[0].subject)
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
            'roles': ['data_clerk'], 'is_active': 'on'})
        user = User.objects.get(pk=user.pk)
        self.assertEqual(user.role_codes, {'data_clerk'})
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
        r = self.client.post(reverse('accounts:user_edit', args=[pending.pk]), {
            'first_name': 'N', 'last_name': 'U', 'roles': ['admin'], 'is_active': 'on'})
        self.assertContains(r, 'is not one of the available choices')
        self.assertEqual(User.objects.get(pk=pending.pk).role_codes, set())
        admin = make_user('admin')
        self.assertEqual(self.client.get(reverse('accounts:user_edit', args=[admin.pk])).status_code, 403)
        other_dm = make_user('data_manager', email='dm2@example.org')
        self.assertEqual(self.client.get(reverse('accounts:user_edit', args=[other_dm.pk])).status_code, 403)

    def test_deactivate_and_reactivate(self):
        admin, clerk = make_user('admin'), make_user('data_clerk')
        other = Client()
        other.force_login(clerk)
        self.assertEqual(other.get(reverse('crf:list')).status_code, 200)
        self.client.force_login(admin)
        self.client.post(reverse('accounts:user_activation', args=[clerk.pk]))
        clerk.refresh_from_db()
        self.assertFalse(clerk.is_active)
        self.assertEqual(clerk.deactivated_by, admin)
        # Their open session ends at the next click, and they cannot log in
        self.assertRedirects(other.get(reverse('crf:list')), reverse('login'))
        r = self.client.get(reverse('accounts:users') + '?status=inactive')
        self.assertContains(r, clerk.email)
        self.assertNotContains(self.client.get(reverse('accounts:users')), clerk.email)  # default: active only
        self.client.post(reverse('accounts:user_activation', args=[clerk.pk]), {'activate': '1'})
        self.assertTrue(User.objects.get(pk=clerk.pk).is_active)
        # Nobody deactivates themselves; a Data Manager cannot deactivate an Admin
        self.assertEqual(self.client.post(reverse('accounts:user_activation', args=[admin.pk])).status_code, 403)
        self.client.force_login(make_user('data_manager'))
        self.assertEqual(self.client.post(reverse('accounts:user_activation', args=[admin.pk])).status_code, 403)

    def test_position_dropdown(self):
        self.client.force_login(make_user('admin'))
        r = self.client.get(reverse('accounts:user_create'))
        self.assertContains(r, '<option value="Medical Doctor (MD)">')
        old = User.objects.create_user('legacy@example.org', PASSWORD, first_name='L', last_name='G', is_active=True,
                                       position='Resident')
        set_roles(old, ['data_clerk'])
        r = self.client.post(reverse('accounts:user_edit', args=[old.pk]), {
            'first_name': 'L', 'last_name': 'G', 'position': 'Resident', 'roles': ['data_clerk']})
        self.assertRedirects(r, reverse('accounts:users'))  # an old free-text title still saves

    def test_multiple_roles_combine_permissions(self):
        both = make_user('data_clerk', 'investigator')
        self.assertEqual(both.role_codes, {'data_clerk', 'investigator'})
        self.assertTrue(user_can(both, 'enter_data'))           # from Data Clerk
        self.assertTrue(user_can(both, 'export_deidentified'))  # from Investigator
        self.assertFalse(user_can(both, 'raise_query'))
        self.assertEqual(both.role_labels, 'Data Clerk, Investigator')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_who_can_create_whom(self):
        url = reverse('accounts:user_create')
        data = {'first_name': 'New', 'last_name': 'Person', 'phone': '', 'institution': '', 'position': ''}
        self.client.force_login(make_user('data_manager'))
        r = self.client.get(url)
        self.assertContains(r, 'Research Scientist')
        self.assertContains(r, 'value="investigator"')
        self.assertNotContains(r, 'value="data_manager"')
        r = self.client.post(url, {**data, 'email': 'a@example.org', 'roles': ['data_manager']})
        self.assertFalse(User.objects.filter(email='a@example.org').exists())
        self.client.post(url, {**data, 'email': 'b@example.org', 'roles': ['data_clerk', 'investigator']})
        created = User.objects.get(email='b@example.org')
        self.assertEqual(created.role_codes, {'data_clerk', 'investigator'})
        # The new person chooses a password from the email, then logs in
        path = re.search(r'/accounts/reset/\S+/', mail.outbox[-1].body).group(0)
        r = self.client.get(path, follow=True)
        self.client.logout()
        r = self.client.get(path, follow=True)
        self.client.post(r.redirect_chain[-1][0], {'new_password1': 'Chosen-Pass-2026!', 'new_password2': 'Chosen-Pass-2026!'})
        self.assertTrue(self.client.login(email='b@example.org', password='Chosen-Pass-2026!'))
        # Admin: can create Data Managers, not Admins
        self.client.force_login(make_user('admin'))
        self.client.post(url, {**data, 'email': 'c@example.org', 'roles': ['data_manager']})
        self.assertEqual(User.objects.get(email='c@example.org').role_codes, {'data_manager'})
        self.client.post(url, {**data, 'email': 'd@example.org', 'roles': ['admin']})
        self.assertFalse(User.objects.filter(email='d@example.org').exists())
        # Superuser: can create Admins
        su = User.objects.create_superuser('root@example.org', PASSWORD, first_name='R', last_name='S')
        self.client.force_login(su)
        self.client.post(url, {**data, 'email': 'e@example.org', 'roles': ['admin']})
        self.assertEqual(User.objects.get(email='e@example.org').role_codes, {'admin'})


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
        self.assertContains(r, "is already registered as")
        self.assertContains(r, reverse('crf:detail', args=[self.p.pk]))
        r = self.client.post(reverse('crf:create'), {'hospital_id': '<b>', 'interview_date': today})
        self.assertContains(r, 'starts with A or M')
        r = self.client.post(reverse('crf:create'), {'hospital_id': 'B10-20-33', 'interview_date': today})
        self.assertContains(r, 'starts with A or M')
        r = self.client.post(reverse('crf:create'), {'hospital_id': 'M10-20-3', 'interview_date': today})
        self.assertContains(r, 'starts with A or M')
        r = self.client.post(reverse('crf:create'), {'hospital_id': 'M71-35-77/4', 'interview_date': today})
        self.assertContains(r, 'looks like the IP Number')
        self.assertEqual(Participant.objects.count(), 1)
        self.client.post(reverse('crf:create'), {'hospital_id': 'a102031', 'interview_date': today})
        self.assertEqual(Participant.objects.count(), 2)
        self.assertEqual(Participant.objects.get(study_id='CLD-0002').hospital_id, 'A10-20-31')
        r = self.client.get(reverse('crf:list') + '?mrn=2031')  # dashes optional when searching
        self.assertContains(r, 'CLD-0002')
        self.assertNotContains(r, 'CLD-0001')
        self.assertContains(r, '<th>MRN</th>')
        self.assertNotContains(r, 'Interviewer')
        self.client.force_login(make_user('investigator'))
        r = self.client.get(reverse('crf:list') + '?mrn=20-31')  # investigators cannot see or filter by MRN
        self.assertContains(r, 'CLD-0001')
        self.assertNotContains(r, '<th>MRN</th>')

    def test_partial_save_then_complete_later(self):
        # Only haemoglobin known today; INR not done; the rest pending.
        r = self.client.post(self.section_url('G'), {'hb': '9.8', 'nd__inr': 'on', 'save': '1'})
        self.assertRedirects(r, self.section_url('G'))
        g = SECTION_MODELS['G'].objects.get(participant=self.p)
        self.assertEqual(g.hb, Decimal('9.8'))
        self.assertEqual(g.not_done, ['inr'])
        status = checks.section_status('G', Participant.objects.get(pk=self.p.pk).values())
        self.assertEqual(status['state'], 'incomplete')
        missing = [f.name for f in status['missing']]
        self.assertIn('platelets', missing)
        self.assertNotIn('inr', missing)
        # Results arrive later
        self.client.post(self.section_url('G'), {'hb': '9.8', 'bilirubin': '68.4', 'inr': '1.9'})
        g.refresh_from_db()
        self.assertEqual(g.inr, Decimal('1.90'))
        self.assertEqual(g.not_done, [])

    def test_impossible_value_refused(self):
        r = self.client.post(self.section_url('G'), {'creatinine': '5000'})  # µmol/L
        self.assertContains(r, 'Impossible value')
        self.assertFalse(SECTION_MODELS['G'].objects.exists())
        self.client.post(self.section_url('G'), {'creatinine': '421'})  # 421 µmol/L is fine
        self.assertEqual(SECTION_MODELS['G'].objects.get().creatinine, Decimal('421.0'))

    def test_lab_values_as_printed_by_mnh(self):
        # Jeeva prints enzymes with 2 decimals; electrolytes may have 1
        r = self.client.post(self.section_url('G'), {'alt': '33.69', 'ast': '137.37', 'alp': '156.03', 'ggt': '79.80',
                                                     'sodium': '134.5', 'potassium': '4.25', 'chloride': '101.2',
                                                     'hb': '4.404', 'wbc': '1.353', 'platelets': '37.90'})
        self.assertEqual(r.status_code, 302)
        g = SECTION_MODELS['G'].objects.get()
        self.assertEqual((g.alt, g.sodium, g.potassium), (Decimal('33.69'), Decimal('134.5'), Decimal('4.25')))
        self.assertEqual((g.hb, g.wbc, g.platelets), (Decimal('4.404'), Decimal('1.353'), Decimal('37.90')))

    def test_other_comorbidity_yes_no(self):
        self.client.post(self.section_url('E'), {'other_comorbidity': '0', 'other_comorbidity_specify': 'Asthma'})
        e = SECTION_MODELS['E'].objects.get()
        self.assertEqual((e.other_comorbidity, e.other_comorbidity_specify), (0, ''))  # cleared: not asked when No
        missing = [f.name for f in checks.section_status('E', Participant.objects.get(pk=self.p.pk).values())['missing']]
        self.assertNotIn('other_comorbidity_specify', missing)
        self.client.post(self.section_url('E'), {'other_comorbidity': '1'})
        missing = [f.name for f in checks.section_status('E', Participant.objects.get(pk=self.p.pk).values())['missing']]
        self.assertIn('other_comorbidity_specify', missing)  # Yes: specify becomes expected

    def test_other_cause_yes_no(self):
        self.client.post(self.section_url('D'), {'other_cause': '0', 'other_cause_specify': 'Schistosomiasis'})
        self.assertEqual(SECTION_MODELS['D'].objects.get().other_cause_specify, '')
        self.client.post(self.section_url('D'), {'other_cause': '1'})
        missing = [f.name for f in checks.section_status('D', Participant.objects.get(pk=self.p.pk).values())['missing']]
        self.assertIn('other_cause_specify', missing)

    def test_result_and_imaging_dates_saved_and_flagged(self):
        today = timezone.localdate()
        r = self.client.post(self.section_url('G'), {
            'lab_sample_date': today, 'lab_result_date': today - datetime.timedelta(days=2),
            'img_modality_us': 'on', 'imaging_date': today + datetime.timedelta(days=3)}, follow=True)
        g = SECTION_MODELS['G'].objects.get()
        self.assertEqual(g.imaging_date, today + datetime.timedelta(days=3))  # saved, not refused
        self.assertContains(r, 'Saved, but check the dates')
        rules = {i.rule for i in checks.all_issues(Participant.objects.get(pk=self.p.pk).values())}
        self.assertTrue({'result_before_sample', 'img_future'} <= rules)
        # No imaging modality: the imaging date is not asked and is cleared
        self.client.post(self.section_url('G'), {'nd__img_modality': 'on', 'imaging_date': today})
        self.assertIsNone(SECTION_MODELS['G'].objects.get().imaging_date)

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
        self.assertRedirects(r, self.section_url('A'))
        self.assertFalse(SECTION_MODELS['A'].objects.exists())
        r = self.client.get(self.section_url('A'))
        self.assertContains(r, 'Verified and locked')
        self.assertNotContains(r, 'name="save"')

    def test_investigator_sees_no_phone_and_cannot_enter(self):
        self.client.force_login(make_user('investigator'))
        r = self.client.get(reverse('crf:detail', args=[self.p.pk]))
        self.assertNotContains(r, '0712000000')
        self.assertNotContains(r, 'M10-20-30')
        r = self.client.get(self.section_url('A'))  # view only
        self.assertContains(r, 'View only')
        self.assertNotContains(r, 'name="save"')
        self.assertEqual(self.client.post(self.section_url('A'), {'age_years': '40'}).status_code, 403)
        r = self.client.get(reverse('crf:form_list', args=['A']))
        self.assertContains(r, 'View')
        self.assertNotContains(r, '>Update<')
        self.assertNotContains(r, '>Enter<')
        r = self.client.get(reverse('crf:detail', args=[self.p.pk]))
        self.assertNotContains(r, 'Edit header')
        self.assertNotContains(r, 'Verify &amp; lock')
        r = self.client.post(reverse('exports:start'), {'dataset': 'combined', 'mode': 'codes', 'format': 'xlsx'})
        wb = load_workbook(BytesIO(self.client.get(reverse('exports:download', args=[r.json()['job']])).content))
        header = [c.value for c in wb['all_sections'][1]]
        self.assertNotIn('phone_number', header)
        self.assertNotIn('hospital_id', header)
        r = self.client.post(reverse('exports:start'), {'dataset': 'combined', 'mode': 'codes', 'format': 'xlsx',
                                                        'identifiable': '1'})
        self.assertEqual(r.status_code, 403)

    def test_save_stays_on_section_and_save_close(self):
        r = self.client.post(self.section_url('A'), {'age_years': '40', 'save': '1'})
        self.assertRedirects(r, self.section_url('A'))
        r = self.client.post(self.section_url('A'), {'age_years': '41', 'save_close': '1', 'back': '/records/forms/A/'})
        self.assertRedirects(r, '/records/forms/A/')

    def test_soft_delete_and_restore(self):
        self.client.post(self.section_url('B'), {'ever_dx_cld': '1'})
        dm, admin = make_user('data_manager'), make_user('admin')
        self.client.force_login(dm)
        # Delete one form: counts as not started, answers kept
        self.client.post(reverse('crf:section_delete', args=[self.p.pk, 'B']), {'reason': 'wrong patient'})
        self.assertIsNone(Participant.objects.get().section('B'))
        self.assertEqual(SECTION_MODELS['B'].objects.get().ever_dx_cld, 1)
        self.assertContains(self.client.get(self.section_url('B')), 'This section was deleted')
        self.assertEqual(self.client.get(reverse('crf:deleted')).status_code, 403)  # restore is for Admins
        # Delete the participant: gone from lists, hospital ID cannot be reused
        self.client.post(reverse('crf:delete', args=[self.p.pk]), {'confirm_id': 'CLD-0001', 'reason': 'duplicate'})
        self.assertFalse(Participant.objects.exists())
        self.assertNotContains(self.client.get(reverse('crf:list')), reverse('crf:detail', args=[self.p.pk]))
        r = self.client.post(reverse('crf:create'), {'hospital_id': 'M10-20-30', 'interview_date': timezone.localdate()})
        self.assertContains(r, 'which was deleted')
        # Admin restores both
        self.client.force_login(admin)
        r = self.client.get(reverse('crf:deleted'))
        self.assertContains(r, 'CLD-0001')
        self.client.post(reverse('crf:restore_participant', args=[self.p.pk]))
        self.client.post(reverse('crf:restore_section', args=[self.p.pk, 'B']))
        p = Participant.objects.get()
        self.assertEqual(p.section('B').ever_dx_cld, 1)

    def test_form_list(self):
        self.client.post(self.section_url('G'), {'hb': '9.8'})
        r = self.client.get(reverse('crf:form_list', args=['G']))
        self.assertContains(r, 'CLD-0001')
        self.assertContains(r, 'M10-20-30')  # Data Clerks see hospital IDs
        self.assertContains(r, '>Update<')
        r = self.client.get(reverse('crf:form_list', args=['G']) + '?show=complete')
        self.assertNotContains(r, 'CLD-0001')
        self.assertEqual(self.client.get(reverse('crf:form_list', args=['I'])).status_code, 404)

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
        v = {'creatinine': Decimal('168.0'), 'bilirubin': Decimal('71.82'),  # 1.9 and 4.2 mg/dL
             'inr': Decimal('1.6'), 'sodium': 128, 'albumin': Decimal('26'),
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
        self.client.post(reverse('crf:create'), {'hospital_id': 'M11-00-01', 'interview_date': today})
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
        self.assertEqual(derived.creatinine_mgdl({'creatinine': Decimal('88.4')}), 1.0)
        self.assertEqual(derived.bilirubin_mgdl({'bilirubin': Decimal('34.2')}), 2.0)
        self.assertIsNone(derived.meld({'inr': 1}))

    def test_checks_find_contradictions_and_wrong_units(self):
        v = {'interview_date': timezone.localdate(), 'admission_date': timezone.localdate(),
             'hepatic_enceph': 1, 'he_grade': 0, 'hbsag': 1, 'hbv': 0, 'albumin': Decimal('8'),
             'bilirubin': Decimal('34.2'), 'direct_bilirubin': Decimal('51'), 'bp_systolic': 90, 'bp_diastolic': 95}
        rules = {i.rule for i in checks.all_issues(v)}
        self.assertNotIn('he_grade0', rules)  # grade 0 accepted (D39)
        self.assertIn('hbsag_history', rules)
        self.assertIn('direct_bili', rules)  # 51 µmol/L = 3 mg/dL, above the total of 2 mg/dL
        self.assertIn('bp', rules)
        self.assertIn('check', rules)  # 8 g/L is probably a g/dL value or a typo


class DictionaryTests(TestCase):
    def test_workbook_matches_spec(self):
        wb = build_workbook()
        self.assertEqual(wb.sheetnames, ['README', 'Sections', 'Data Dictionary', 'Choices', 'Derived Scores',
                                         'Reference Ranges', 'Data Checks', 'Decisions', 'Change Log'])
        names = [r[3] for r in wb['Data Dictionary'].iter_rows(min_row=2, values_only=True)]
        for _s, f in spec.all_fields():
            self.assertIn(f.name, names)
        decisions = {r[0] for r in wb['Decisions'].iter_rows(min_row=3, values_only=True)}
        used = {f.decision for _s, f in spec.all_fields() if f.decision} | {f.decision for f in spec.HEADER if f.decision}
        used |= {d.decision for d in spec.DERIVED if d.decision}
        self.assertFalse(used - decisions, 'Decision IDs used in spec.py but missing from decisions.py')


class RoleSplitTests(TestCase):
    def test_research_scientist_enters_investigator_views(self):
        today = timezone.localdate()
        rs = make_user('research_scientist')
        self.client.force_login(rs)
        self.client.post(reverse('crf:create'), {'hospital_id': 'M11-00-02', 'interview_date': today})
        p = Participant.objects.get()
        self.client.post(reverse('crf:section', args=[p.pk, 'A']), {'age_years': '50'})
        self.assertEqual(SECTION_MODELS['A'].objects.get().age_years, 50)
        self.assertTrue(user_can(rs, 'export_deidentified'))
        inv = make_user('investigator')
        self.client.force_login(inv)
        self.assertEqual(self.client.post(reverse('crf:section', args=[p.pk, 'A']), {'age_years': '60'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('crf:create')).status_code, 403)
        self.assertContains(self.client.get(reverse('crf:section', args=[p.pk, 'A'])), 'View only')
        dm = make_user('data_manager')
        self.client.force_login(dm)
        r = self.client.get(reverse('accounts:user_create'))
        for code in ('data_clerk', 'research_scientist', 'investigator'):
            self.assertContains(r, f'value="{code}"')
        self.assertNotContains(r, 'value="data_manager"')


class DateTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user('data_clerk'))
        self.today = timezone.localdate()
        self.adm = self.today - datetime.timedelta(days=10)
        self.client.post(reverse('crf:create'), {'hospital_id': 'M11-00-03', 'interview_date': self.today - datetime.timedelta(days=8),
                                                 'admission_date': self.adm})
        self.p = Participant.objects.get()
        self.url = reverse('crf:section', args=[self.p.pk, 'L'])

    def test_outcome_shows_matching_date_and_fills_length_of_stay(self):
        died = self.adm + datetime.timedelta(days=6)
        self.client.post(self.url, {'outcome': '2', 'death_date': died, 'discharge_date': self.adm})
        row = SECTION_MODELS['L'].objects.get()
        self.assertEqual(row.death_date, died)
        self.assertIsNone(row.discharge_date)  # skip rule: not asked when the patient died
        self.assertEqual(row.los_days, 6)       # filled from the dates
        f = spec.FIELD_BY_NAME['discharge_date'][1]
        self.assertEqual(spec.relevance_text(f), '${outcome} = 1')

    def test_impossible_dates_saved_and_flagged(self):
        """Dates are never refused: they are saved, the user is told, and they appear under the date checks."""
        before = self.adm - datetime.timedelta(days=1)
        r = self.client.post(self.url, {'outcome': '1', 'discharge_date': before}, follow=True)
        self.assertEqual(SECTION_MODELS['L'].objects.get().discharge_date, before)
        self.assertContains(r, 'Saved, but check the dates')
        self.client.post(self.url, {'outcome': '2', 'death_date': self.adm + datetime.timedelta(days=1)})
        self.client.post(reverse('crf:section', args=[self.p.pk, 'G']), {'lab_sample_date': self.adm + datetime.timedelta(days=3)})
        self.client.post(reverse('crf:edit', args=[self.p.pk]), {'hospital_id': 'M11-00-03', 'interview_date': '2016-05-01',
                                                               'admission_date': '2016-06-01'})
        p = Participant.objects.get()
        self.assertEqual(p.interview_date, datetime.date(2016, 5, 1))
        rules = {i.rule for i in checks.all_issues(p.values())}
        self.assertTrue({'lab_after_death', 'date_old', 'adm_after_int'} <= rules)
        self.client.force_login(make_user('data_manager'))
        r = self.client.get(reverse('quality:issues') + '?category=Dates&participant=CLD-0001')
        self.assertContains(r, 'Laboratory sample is after the date of death')
        self.assertContains(r, 'Admission date is after the interview date')

    def test_date_warnings_and_filter(self):
        self.client.post(self.url, {'outcome': '2', 'death_date': self.adm + datetime.timedelta(days=1), 'los_days': '9'})
        rules = {i.rule for i in checks.all_issues(Participant.objects.get().values())}
        self.assertIn('death_before_int', rules)
        self.assertIn('los_dates', rules)
        self.client.force_login(make_user('data_manager'))
        r = self.client.get(reverse('quality:issues') + '?category=Dates&participant=CLD-0001')
        self.assertContains(r, 'Date of death is before the interview date')
        self.assertContains(r, 'Open section L')
        r = self.client.get(reverse('quality:issues') + '?category=Consistency&participant=CLD-0001')
        self.assertNotContains(r, 'Date of death is before')

    def test_dictionary_lists_checks(self):
        wb = build_workbook()
        rules = [row[0] for row in wb['Data Checks'].iter_rows(min_row=2, values_only=True)]
        self.assertIn('death_before_int', rules)
        self.assertIn('lab_after_death', rules)


class SidebarCountTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.dm = make_user('data_manager')
        self.client.force_login(self.dm)

    def test_badges_show_and_update_after_saving(self):
        today = timezone.localdate()
        self.client.post(reverse('crf:create'), {'hospital_id': 'M55-00-01', 'interview_date': today,
                                                 'admission_date': today + datetime.timedelta(days=3)})
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'class="side-badge danger" title="Errors">2<')  # admission in the future and after the interview
        self.assertContains(r, 'title="Records still waiting for investigation results (Section G)">1<')
        p = Participant.objects.get()
        DataQuery.objects.create(participant=p, section='A', field='age', message='Check', raised_by=self.dm)
        r = self.client.get(reverse('dashboard'))  # saving the query cleared the cached numbers
        self.assertContains(r, 'title="Open queries">1<')
        self.client.force_login(make_user('investigator'))
        self.assertContains(self.client.get(reverse('dashboard')), 'title="Open queries">1<')
