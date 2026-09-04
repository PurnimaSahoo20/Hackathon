from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .views import _find_login_user
from .models import OTPVerification, Role, SuperadminProfile


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SuperAdminOtpLoginTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(name='Super Admin')
        self.user = get_user_model().objects.create_user(
            username='superadmin',
            email='superadmin@example.com',
            password='pass12345',
            role=self.role,
        )

    def test_otp_login_redirects_to_dashboard_and_creates_profile(self):
        login_response = self.client.post(reverse('login'), {
            'identifier': 'superadmin',
            'password': 'pass12345',
        })

        self.assertRedirects(
            login_response,
            reverse('verify_otp'),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session.get('pending_2fa_user_id'),
            self.user.id,
        )

        otp = OTPVerification.objects.get(user=self.user)
        verify_response = self.client.post(reverse('verify_otp'), {
            'otp': otp.code,
        })

        self.assertRedirects(
            verify_response,
            reverse('superadmin_dashboard'),
            fetch_redirect_response=False,
        )
        self.assertNotIn('pending_2fa_user_id', self.client.session)

        dashboard_response = self.client.get(reverse('superadmin_dashboard'))

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertTrue(
            SuperadminProfile.objects.filter(user=self.user).exists()
        )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class DuplicateEmailLoginTests(TestCase):
    def setUp(self):
        self.user_a = get_user_model().objects.create_user(
            username='alpha',
            email='shared@example.com',
            password='alpha-pass',
        )
        self.user_b = get_user_model().objects.create_user(
            username='beta',
            email='shared@example.com',
            password='beta-pass',
        )

    def test_login_lookup_prefers_password_matching_account_for_duplicate_emails(self):
        resolved_a = _find_login_user('shared@example.com', 'alpha-pass')
        resolved_b = _find_login_user('shared@example.com', 'beta-pass')

        self.assertEqual(resolved_a.id, self.user_a.id)
        self.assertEqual(resolved_b.id, self.user_b.id)


class InvitationValidationTests(TestCase):
    def test_clean_indian_phone_number_valid(self):
        from features.views import _clean_indian_phone_number
        self.assertEqual(_clean_indian_phone_number("9876543210"), "+91 9876543210")
        self.assertEqual(_clean_indian_phone_number("+91 9876543210"), "+91 9876543210")
        self.assertEqual(_clean_indian_phone_number("919876543210"), "+91 9876543210")
        self.assertEqual(_clean_indian_phone_number(" 91 98765-43210 "), "+91 9876543210")
        self.assertEqual(_clean_indian_phone_number("7008123456"), "+91 7008123456")
        
    def test_clean_indian_phone_number_invalid(self):
        from features.views import _clean_indian_phone_number
        with self.assertRaises(ValueError):
            _clean_indian_phone_number("1234567890")
        with self.assertRaises(ValueError):
            _clean_indian_phone_number("987654321")
        with self.assertRaises(ValueError):
            _clean_indian_phone_number("98765432100")
        with self.assertRaises(ValueError):
            _clean_indian_phone_number("abc9876543210")

    def test_clean_indian_contact_number_valid(self):
        from features.views import _clean_indian_contact_number
        self.assertEqual(_clean_indian_contact_number("0674250000"), "+91 0674250000")
        self.assertEqual(_clean_indian_contact_number("+91 0674250000"), "+91 0674250000")
        self.assertEqual(_clean_indian_contact_number("910674250000"), "+91 0674250000")
        
    def test_clean_indian_contact_number_invalid(self):
        from features.views import _clean_indian_contact_number
        with self.assertRaises(ValueError):
            _clean_indian_contact_number("12345")


class InvitationRegistrationViewTests(TestCase):
    def setUp(self):
        from accounts.models import JuryInvitation, SpocInvitation
        self.jury_invite = JuryInvitation.objects.create(
            email='testjury@example.com',
            token='testjurytoken123',
            status='invited'
        )
        self.spoc_invite = SpocInvitation.objects.create(
            email='testspoc@example.com',
            token='testspoctoken123',
            status='invited'
        )

    def test_jury_register_form_get(self):
        response = self.client.get(reverse('jury_register_form', args=[self.jury_invite.token]))
        self.assertEqual(response.status_code, 200)

    def test_jury_register_form_post_invalid_phone(self):
        post_data = {
            'first_name': 'JuryFirst',
            'last_name': 'JuryLast',
            'phone_number': '1234567890',  # Invalid: starts with 1
            'gender': 'Male',
            'organization': 'JuryOrg',
            'designation': 'Judge',
            'domain': 'AI/ML',
        }
        response = self.client.post(reverse('jury_register_form', args=[self.jury_invite.token]), post_data)
        self.assertEqual(response.status_code, 200)
        self.jury_invite.refresh_from_db()
        self.assertEqual(self.jury_invite.status, 'invited')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class OnboardingApprovalWorkflowTests(TestCase):
    """
    Tests covering the complete approval, rejection, resubmission,
    history tracking, and security lifecycle across SPOC, Jury, and Expert roles.
    """
    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.models import Role, SpocInvitation, JuryInvitation, ExpertInvitation, InvitationReviewHistory
        from events.models import Hackathon

        self.superadmin_role = Role.objects.create(name='Super Admin')
        self.admin_user = get_user_model().objects.create_user(
            username='admin_reviewer',
            email='admin_reviewer@example.com',
            password='Password@123',
            role=self.superadmin_role,
        )
        Role.objects.get_or_create(name='SPOC')
        Role.objects.get_or_create(name='Jury')
        Role.objects.get_or_create(name='Expert')

        self.hackathon = Hackathon.objects.create(
            name='National Hackathon 2026',
            organization_name='BPUT Innovation Cell',
        )

        self.sample_id_file = SimpleUploadedFile(
            'id_proof.pdf',
            b'%PDF-1.4 sample pdf content for id proof testing',
            content_type='application/pdf'
        )

    def test_case_1_invitation_submission_admin_approves(self):
        """
        TEST CASE 1:
        Invitation -> Form submission -> Admin approves -> Approval email & user account created.
        """
        from accounts.models import SpocInvitation, SpocProfile, InvitationReviewHistory
        from django.core import mail

        spoc_invite = SpocInvitation.objects.create(
            email='spoc_case1@example.com',
            token='spoctoken_case1',
            hackathon=self.hackathon,
            status='invited',
        )

        # 1. User fills and submits form
        post_data = {
            'first_name': 'Aarav',
            'last_name': 'Patnaik',
            'phone_number': '+91 9876543210',
            'gender': 'Male',
            'institution_name': 'Case1 Institute of Tech',
            'institution_email': 'info@case1inst.edu',
            'institution_address': 'Plot 100, Infocity Avenue, Chandaka',
            'institution_location': 'Bhubaneswar',
            'institution_head_name': 'Prof. B. Mishra',
            'institution_head_email': 'principal@case1inst.edu',
            'institution_contact': '+91 0674250000',
            'id_proof': self.sample_id_file,
        }
        res = self.client.post(reverse('spoc_register_form', args=[spoc_invite.token]), post_data)
        self.assertEqual(res.status_code, 200)

        spoc_invite.refresh_from_db()
        self.assertEqual(spoc_invite.status, 'pending')

        # Check initial submission history recorded
        history_init = InvitationReviewHistory.objects.filter(spoc_invitation=spoc_invite).first()
        self.assertIsNotNone(history_init)
        self.assertEqual(history_init.action, 'initial_submission')
        self.assertEqual(history_init.attempt_number, 1)

        # 2. Admin logs in and approves
        self.client.force_login(self.admin_user)
        mail.outbox = []
        approve_res = self.client.post(reverse('approve_spoc_invitation', args=[spoc_invite.id]))
        self.assertEqual(approve_res.status_code, 302)

        spoc_invite.refresh_from_db()
        self.assertEqual(spoc_invite.status, 'approved')
        self.assertIsNotNone(spoc_invite.created_user)
        self.assertTrue(SpocProfile.objects.filter(user=spoc_invite.created_user).exists())

        # Check approval history
        approve_history = InvitationReviewHistory.objects.filter(spoc_invitation=spoc_invite, action='approved').first()
        self.assertIsNotNone(approve_history)
        self.assertEqual(approve_history.reviewed_by, self.admin_user)

        # Check approval email sent
        self.assertGreater(len(mail.outbox), 0)
        self.assertIn('Registration Confirmed', mail.outbox[0].subject)

    def test_case_2_reject_resubmit_approve_cycle(self):
        """
        TEST CASE 2:
        Invitation -> Form submission -> Admin rejects -> Rejection email -> User edits -> Resubmits -> Admin approves.
        """
        from accounts.models import JuryInvitation, JuryProfile, InvitationReviewHistory
        from django.core import mail

        jury_invite = JuryInvitation.objects.create(
            email='jury_case2@example.com',
            token='jurytoken_case2',
            hackathon=self.hackathon,
            status='invited',
        )

        # 1. Initial Submission
        post_data_1 = {
            'first_name': 'Sunita',
            'last_name': 'Rout',
            'phone_number': '+91 9437012345',
            'gender': 'Female',
            'organization': 'ABC University',
            'designation': 'Assistant Professor',
            'domain': 'AI/ML, Data Science',
            'id_proof': self.sample_id_file,
        }
        self.client.post(reverse('jury_register_form', args=[jury_invite.token]), post_data_1)
        jury_invite.refresh_from_db()
        self.assertEqual(jury_invite.status, 'pending')

        # 2. Admin Rejection
        self.client.force_login(self.admin_user)
        mail.outbox = []
        reject_res = self.client.post(reverse('reject_jury_invitation', args=[jury_invite.id]), {
            'rejection_reason': 'Please provide higher resolution ID proof and specify primary domain.'
        })
        self.assertEqual(reject_res.status_code, 302)

        jury_invite.refresh_from_db()
        self.assertEqual(jury_invite.status, 'rejected')
        self.assertEqual(jury_invite.rejection_reason, 'Please provide higher resolution ID proof and specify primary domain.')

        # Verify rejection email sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('needs correction', mail.outbox[0].subject)
        self.assertIn(jury_invite.token, mail.outbox[0].body)

        # 3. User accesses form again (GET) -> Form loads pre-filled and shows rejection reason
        get_res = self.client.get(reverse('jury_register_form', args=[jury_invite.token]))
        self.assertEqual(get_res.status_code, 200)
        self.assertContains(get_res, 'Sunita')
        self.assertContains(get_res, 'Please provide higher resolution ID proof')

        # 4. User modifies and Resubmits
        from django.core.files.uploadedfile import SimpleUploadedFile
        updated_id_file = SimpleUploadedFile('clear_id.pdf', b'%PDF-1.4 clear id content', content_type='application/pdf')
        post_data_2 = {
            'first_name': 'Sunita',
            'last_name': 'Rout',
            'phone_number': '+91 9437012345',
            'gender': 'Female',
            'organization': 'ABC Institute of Technology',
            'designation': 'Professor & Head',
            'domain': 'Artificial Intelligence',
            'id_proof': updated_id_file,
        }
        resubmit_res = self.client.post(reverse('jury_register_form', args=[jury_invite.token]), post_data_2)
        self.assertEqual(resubmit_res.status_code, 200)

        jury_invite.refresh_from_db()
        self.assertEqual(jury_invite.status, 'pending')

        # 5. Admin Approves the Resubmission
        mail.outbox = []
        approve_res = self.client.post(reverse('approve_jury_invitation', args=[jury_invite.id]))
        self.assertEqual(approve_res.status_code, 302)

        jury_invite.refresh_from_db()
        self.assertEqual(jury_invite.status, 'approved')
        self.assertTrue(JuryProfile.objects.filter(user=jury_invite.created_user).exists())

        # Check full history records
        history_actions = list(InvitationReviewHistory.objects.filter(jury_invitation=jury_invite).values_list('action', flat=True))
        self.assertIn('initial_submission', history_actions)
        self.assertIn('rejected', history_actions)
        self.assertIn('resubmitted', history_actions)
        self.assertIn('approved', history_actions)

    def test_case_3_unlimited_multiple_rejection_resubmission_cycles(self):
        """
        TEST CASE 3:
        Invitation -> Form submission -> Reject -> Resubmit -> Reject again -> Resubmit -> Approve.
        """
        from accounts.models import ExpertInvitation, ExpertProfile, InvitationReviewHistory
        from django.core import mail

        expert_invite = ExpertInvitation.objects.create(
            email='expert_case3@example.com',
            token='experttoken_case3',
            hackathon=self.hackathon,
            status='invited',
        )

        # --- Cycle 1: Submit -> Reject ---
        self.client.post(reverse('expert_register_form', args=[expert_invite.token]), {
            'first_name': 'Debashis',
            'last_name': 'Mohanty',
            'phone_number': '+91 9861011223',
            'gender': 'Male',
            'organization': 'Tech Corp',
            'designation': 'Architect',
            'domain': 'Cloud Computing',
            'id_proof': self.sample_id_file,
        })
        expert_invite.refresh_from_db()
        self.assertEqual(expert_invite.status, 'pending')

        self.client.force_login(self.admin_user)
        rej_res1 = self.client.post(reverse('reject_expert_invitation', args=[expert_invite.id]), {
            'rejection_reason': 'Attempt 1: Incorrect organization designation.'
        })
        self.assertEqual(rej_res1.status_code, 302)
        expert_invite.refresh_from_db()
        self.assertEqual(expert_invite.status, 'rejected')

        # --- Cycle 2: Resubmit -> Reject Again ---
        self.client.post(reverse('expert_register_form', args=[expert_invite.token]), {
            'first_name': 'Debashis',
            'last_name': 'Mohanty',
            'phone_number': '+91 9861011223',
            'gender': 'Male',
            'organization': 'Tech Corp Global',
            'designation': 'Principal Cloud Architect',
            'domain': 'Cloud Computing',
            'id_proof': self.sample_id_file,
        })
        expert_invite.refresh_from_db()
        self.assertEqual(expert_invite.status, 'pending')

        rej_res2 = self.client.post(reverse('reject_expert_invitation', args=[expert_invite.id]), {
            'rejection_reason': 'Attempt 2: Please provide full LinkedIn profile link.'
        })
        self.assertEqual(rej_res2.status_code, 302)
        expert_invite.refresh_from_db()
        self.assertEqual(expert_invite.status, 'rejected')

        # --- Cycle 3: Resubmit -> Finally Approve ---
        self.client.post(reverse('expert_register_form', args=[expert_invite.token]), {
            'first_name': 'Debashis',
            'last_name': 'Mohanty',
            'phone_number': '+91 9861011223',
            'gender': 'Male',
            'organization': 'Tech Corp Global',
            'designation': 'Principal Cloud Architect',
            'domain': 'Cloud Computing, DevOps',
            'linkedin_url': 'https://linkedin.com/in/debashis-cloud',
            'id_proof': self.sample_id_file,
        })
        expert_invite.refresh_from_db()
        self.assertEqual(expert_invite.status, 'pending')

        app_res = self.client.post(reverse('approve_expert_invitation', args=[expert_invite.id]))
        self.assertEqual(app_res.status_code, 302)
        expert_invite.refresh_from_db()
        self.assertEqual(expert_invite.status, 'approved')
        self.assertTrue(ExpertProfile.objects.filter(user=expert_invite.created_user).exists())

        # Verify full chronological audit trail
        history_logs = InvitationReviewHistory.objects.filter(expert_invitation=expert_invite).order_by('created_at')
        actions = [log.action for log in history_logs]
        self.assertEqual(actions, ['initial_submission', 'rejected', 'resubmitted', 'rejected', 'resubmitted', 'approved'])

    def test_case_4_invalid_or_wrong_token_access_denied(self):
        """
        TEST CASE 4:
        User attempts to access another user's form or invalid token -> Access denied.
        """
        bad_res_spoc = self.client.get(reverse('spoc_register_form', args=['nonexistent_token_999']))
        self.assertEqual(bad_res_spoc.status_code, 200)
        self.assertContains(bad_res_spoc, 'Invalid or expired registration link')

        bad_res_jury = self.client.get(reverse('jury_register_form', args=['nonexistent_token_999']))
        self.assertEqual(bad_res_jury.status_code, 200)
        self.assertContains(bad_res_jury, 'Invalid or expired registration link')

        bad_res_expert = self.client.get(reverse('expert_register_form', args=['nonexistent_token_999']))
        self.assertEqual(bad_res_expert.status_code, 200)
        self.assertContains(bad_res_expert, 'Invalid or expired registration link')

    def test_case_5_already_approved_user_resubmission_blocked(self):
        """
        TEST CASE 5:
        Already approved user attempts to resubmit -> Prevent unauthorized resubmission.
        """
        from accounts.models import JuryInvitation
        approved_invite = JuryInvitation.objects.create(
            email='already_approved@example.com',
            token='approvedtoken_555',
            status='approved',
        )

        # GET should be blocked
        res_get = self.client.get(reverse('jury_register_form', args=[approved_invite.token]))
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, 'already been approved')

        # POST should not alter status
        res_post = self.client.post(reverse('jury_register_form', args=[approved_invite.token]), {
            'first_name': 'Hacker',
            'last_name': 'Attempt',
        })
        self.assertEqual(res_post.status_code, 200)
        approved_invite.refresh_from_db()
        self.assertEqual(approved_invite.status, 'approved')

    def test_case_6_admin_rejection_without_reason_rejected_by_validation(self):
        """
        TEST CASE 6:
        Admin rejects without providing a rejection reason -> Handle according to validation rules.
        """
        from accounts.models import SpocInvitation
        spoc_invite = SpocInvitation.objects.create(
            email='spoc_reason_test@example.com',
            token='spoctoken_reason_test',
            status='pending',
            first_name='Kiran',
            last_name='Nayak',
            institution_name='Test College',
        )

        self.client.force_login(self.admin_user)
        # Attempt rejection with empty reason
        res = self.client.post(reverse('reject_spoc_invitation', args=[spoc_invite.id]), {
            'rejection_reason': '   '
        })
        self.assertEqual(res.status_code, 302)

        # Status must remain pending
        spoc_invite.refresh_from_db()
        self.assertEqual(spoc_invite.status, 'pending')

    def test_case_7_multiple_concurrent_users_isolated(self):
        """
        TEST CASE 7:
        Multiple users simultaneously submit/resubmit -> Ensure records are associated with the correct user.
        """
        from accounts.models import JuryInvitation, InvitationReviewHistory

        user1 = JuryInvitation.objects.create(email='jurya@example.com', token='token_jurya', status='invited')
        user2 = JuryInvitation.objects.create(email='juryb@example.com', token='token_juryb', status='invited')

        # User 1 submits
        self.client.post(reverse('jury_register_form', args=[user1.token]), {
            'first_name': 'UserOne',
            'last_name': 'LastOne',
            'phone_number': '+91 9876543201',
            'gender': 'Male',
            'organization': 'Org 1',
            'designation': 'Judge 1',
            'domain': 'AI',
            'id_proof': self.sample_id_file,
        })

        # User 2 submits
        self.client.post(reverse('jury_register_form', args=[user2.token]), {
            'first_name': 'UserTwo',
            'last_name': 'LastTwo',
            'phone_number': '+91 9876543202',
            'gender': 'Female',
            'organization': 'Org 2',
            'designation': 'Judge 2',
            'domain': 'IoT',
            'id_proof': self.sample_id_file,
        })

        user1.refresh_from_db()
        user2.refresh_from_db()

        self.assertEqual(user1.first_name, 'UserOne')
        self.assertEqual(user2.first_name, 'UserTwo')
        self.assertEqual(user1.status, 'pending')
        self.assertEqual(user2.status, 'pending')

        # History is isolated to respective records
        self.assertEqual(InvitationReviewHistory.objects.filter(jury_invitation=user1).count(), 1)
        self.assertEqual(InvitationReviewHistory.objects.filter(jury_invitation=user2).count(), 1)



