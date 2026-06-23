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
