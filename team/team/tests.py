from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from events.models import Hackathon
from features.models import TeamRegistration
from team.team.models import TeamMemberInvite
from accounts.models import TeamleadProfile

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TeamRemoveMemberTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='lead_user',
            email='lead@example.com',
            password='password123',
        )
        self.profile = TeamleadProfile.objects.create(user=self.user)
        
        self.hackathon = Hackathon.objects.create(
            name='Test Hackathon',
            organization_name='Test Org',
            registration_close=timezone.localdate() + timezone.timedelta(days=5)
        )
        
        self.reg = TeamRegistration.objects.create(
            hackathon=self.hackathon,
            team_name='Test Team',
            team_leader=self.user,
            members_data=[
                {
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'email': 'john@example.com',
                    'role': 'Member',
                },
                {
                    'first_name': 'Jane',
                    'last_name': 'Smith',
                    'email': 'jane@example.com',
                    'role': 'Co-Lead',
                }
            ]
        )
        
        self.invite = TeamMemberInvite.objects.create(
            registration=self.reg,
            inviter=self.user,
            email='jane@example.com',
            token='some-token-value-1234',
        )

    def test_remove_member_success(self):
        self.client.login(username='lead_user', password='password123')
        
        response = self.client.post(reverse('team_remove_member', args=[1]))
        self.assertRedirects(response, reverse('team_details'))
        
        self.reg.refresh_from_db()
        self.assertEqual(len(self.reg.members_data), 1)
        self.assertEqual(self.reg.members_data[0]['email'], 'john@example.com')
        self.assertFalse(TeamMemberInvite.objects.filter(email='jane@example.com').exists())

    def test_remove_member_invalid_index(self):
        self.client.login(username='lead_user', password='password123')
        
        response = self.client.post(reverse('team_remove_member', args=[5]))
        self.assertRedirects(response, reverse('team_details'))
        
        self.reg.refresh_from_db()
        self.assertEqual(len(self.reg.members_data), 2)


from django.core.files.uploadedfile import SimpleUploadedFile

class TeamAgeValidationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='lead_user',
            email='lead@example.com',
            password='password123',
        )
        self.profile = TeamleadProfile.objects.create(user=self.user)
        
        self.hackathon = Hackathon.objects.create(
            name='Test Hackathon',
            organization_name='Test Org',
            registration_close=timezone.localdate() + timezone.timedelta(days=5)
        )
        
        self.reg = TeamRegistration.objects.create(
            hackathon=self.hackathon,
            team_name='Test Team',
            team_leader=self.user,
            leader_details={
                'photo': 'mock_photo.png',
                'college_id_proof': 'mock_id.pdf',
                'aadhaar_proof': 'mock_aadhaar.pdf',
                'passbook_proof': 'mock_passbook.pdf',
            },
            members_data=[
                {
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'email': 'john@example.com',
                    'role': 'Member',
                    'phone_number': '9876543210',
                    'date_of_birth': '2000-01-01',
                    'gender': 'Male',
                    'cast': 'General',
                    'tshirt_size': 'M',
                    'aadhaar_number': '123456789012',
                    'bank_account': '12345678901',
                    'ifsc': 'SBIN0001234',
                    'bank_name': 'SBI',
                    'photo': 'photo.jpg',
                    'college_id_proof': 'id.pdf',
                    'aadhaar_proof': 'aadhaar.pdf',
                    'passbook_proof': 'passbook.pdf',
                }
            ]
        )

    def test_team_lead_under_18(self):
        self.client.login(username='lead_user', password='password123')
        
        # Team lead born 15 years ago
        fifteen_years_ago = (timezone.localdate() - timezone.timedelta(days=15*365)).strftime('%Y-%m-%d')
        
        data = {
            'team_name': 'Test Team',
            'leader_first_name': 'Lead',
            'leader_last_name': 'User',
            'leader_phone_number': '9876543210',
            'leader_date_of_birth': fifteen_years_ago,
            'leader_gender': 'Male',
            'leader_cast': 'General',
            'leader_tshirt_size': 'M',
            'leader_aadhaar_number': '999999999999',
            'leader_bank_account': '999999999999',
            'leader_ifsc': 'SBIN0001234',
            'leader_bank_name': 'SBI',
        }
        
        response = self.client.post(reverse('team_details'), data)
        self.assertEqual(response.status_code, 200) # Rerenders with error
        self.assertContains(response, 'Team Lead must be at least 18 years old.')

    def test_team_lead_above_18(self):
        self.client.login(username='lead_user', password='password123')
        
        # Team lead born 20 years ago
        twenty_years_ago = (timezone.localdate() - timezone.timedelta(days=20*365)).strftime('%Y-%m-%d')
        
        data = {
            'team_name': 'Test Team',
            'leader_first_name': 'Lead',
            'leader_last_name': 'User',
            'leader_phone_number': '9876543210',
            'leader_date_of_birth': twenty_years_ago,
            'leader_gender': 'Male',
            'leader_cast': 'General',
            'leader_tshirt_size': 'M',
            'leader_aadhaar_number': '999999999999',
            'leader_bank_account': '999999999999',
            'leader_ifsc': 'SBIN0001234',
            'leader_bank_name': 'SBI',
        }
        
        response = self.client.post(reverse('team_details'), data)
        self.assertRedirects(response, reverse('team_details'))

    def test_add_member_under_18(self):
        self.client.login(username='lead_user', password='password123')
        fifteen_years_ago = (timezone.localdate() - timezone.timedelta(days=15*365)).strftime('%Y-%m-%d')
        
        photo = SimpleUploadedFile("photo.jpg", b"file_content", content_type="image/jpeg")
        college_id = SimpleUploadedFile("id.pdf", b"file_content", content_type="application/pdf")
        aadhaar_proof = SimpleUploadedFile("aadhaar.pdf", b"file_content", content_type="application/pdf")
        passbook = SimpleUploadedFile("passbook.pdf", b"file_content", content_type="application/pdf")

        data = {
            'first_name': 'Young',
            'last_name': 'Member',
            'email': 'young@example.com',
            'phone_number': '9876543211',
            'date_of_birth': fifteen_years_ago,
            'gender': 'Male',
            'cast': 'General',
            'tshirt_size': 'M',
            'aadhaar_number': '123456789013',
            'bank_account': '123456789013',
            'ifsc': 'SBIN0001234',
            'bank_name': 'SBI',
            'photo': photo,
            'college_id_proof': college_id,
            'aadhaar_proof': aadhaar_proof,
            'passbook_proof': passbook,
        }
        
        response = self.client.post(reverse('team_add_member'), data)
        self.assertRedirects(response, reverse('team_details') + '?show_add_member=1')
        
        self.reg.refresh_from_db()
        self.assertEqual(len(self.reg.members_data), 1)

    def test_edit_member_under_18(self):
        self.client.login(username='lead_user', password='password123')
        fifteen_years_ago = (timezone.localdate() - timezone.timedelta(days=15*365)).strftime('%Y-%m-%d')

        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'phone_number': '9876543210',
            'date_of_birth': fifteen_years_ago,
            'gender': 'Male',
            'cast': 'General',
            'tshirt_size': 'M',
            'aadhaar_number': '123456789012',
            'bank_account': '12345678901',
            'ifsc': 'SBIN0001234',
            'bank_name': 'SBI',
        }
        
        response = self.client.post(reverse('team_edit_member', args=[0]), data)
        self.assertRedirects(response, reverse('team_details') + '?show_edit_member=0')
        
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.members_data[0]['date_of_birth'], '2000-01-01')


from features.models import Team

class TeamTravelRestrictionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='lead_user',
            email='lead@example.com',
            password='password123',
        )
        self.profile = TeamleadProfile.objects.create(user=self.user)
        
        self.hackathon = Hackathon.objects.create(
            name='Test Hackathon',
            organization_name='Test Org',
            number_of_rounds=3,
            registration_close=timezone.localdate() + timezone.timedelta(days=5)
        )
        
        self.reg = TeamRegistration.objects.create(
            hackathon=self.hackathon,
            team_name='Test Team',
            team_leader=self.user,
        )

    def test_travel_blocked_when_no_team_exists(self):
        self.client.login(username='lead_user', password='password123')
        
        response = self.client.get(reverse('team_travel'))
        self.assertRedirects(response, reverse('team_dashboard'))

    def test_travel_blocked_when_not_in_final_round(self):
        self.client.login(username='lead_user', password='password123')
        
        self.team = Team.objects.create(
            team_name='Test Team',
            hackathon=self.hackathon,
            team_leader=self.user,
            current_round=1,
        )
        
        response = self.client.get(reverse('team_travel'))
        self.assertRedirects(response, reverse('team_dashboard'))
        
        add_response = self.client.post(reverse('team_add_travel'), {})
        self.assertRedirects(add_response, reverse('team_dashboard'))

    def test_travel_active_when_in_final_round(self):
        self.client.login(username='lead_user', password='password123')
        
        self.team = Team.objects.create(
            team_name='Test Team',
            hackathon=self.hackathon,
            team_leader=self.user,
            current_round=3,
        )
        
        response = self.client.get(reverse('team_travel'))
        self.assertEqual(response.status_code, 200)

    def test_add_group_travel_ticket(self):
        self.client.login(username='lead_user', password='password123')
        self.team = Team.objects.create(
            team_name='Test Team',
            hackathon=self.hackathon,
            team_leader=self.user,
            current_round=3,
        )
        data = {
            'origin': 'Bhubaneswar',
            'destination': 'Delhi',
            'journey_date': '2026-08-01',
            'travel_mode': 'train',
            'ticket_type': 'group',
            'ticket_number': '1234567890',
            'ticket_amount': '2500.00',
        }
        response = self.client.post(reverse('team_add_travel'), data)
        self.assertRedirects(response, reverse('team_travel'))
        
        from team.team.models import TeamTravelDetail
        entry = TeamTravelDetail.objects.filter(registration=self.reg).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.traveler_name, "Group / Whole Team")
        self.assertEqual(entry.origin, "Bhubaneswar")

    def test_add_individual_travel_ticket_success(self):
        self.client.login(username='lead_user', password='password123')
        self.team = Team.objects.create(
            team_name='Test Team',
            hackathon=self.hackathon,
            team_leader=self.user,
            current_round=3,
        )
        data = {
            'origin': 'Bhubaneswar',
            'destination': 'Delhi',
            'journey_date': '2026-08-01',
            'travel_mode': 'train',
            'ticket_type': 'individual',
            'travelers': ['lead_user', 'Member One'],
            'ticket_number': '1234567890',
            'ticket_amount': '2500.00',
        }
        response = self.client.post(reverse('team_add_travel'), data)
        self.assertRedirects(response, reverse('team_travel'))
        
        from team.team.models import TeamTravelDetail
        entry = TeamTravelDetail.objects.filter(registration=self.reg).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.traveler_name, "lead_user, Member One")

    def test_add_individual_travel_ticket_no_travelers(self):
        self.client.login(username='lead_user', password='password123')
        self.team = Team.objects.create(
            team_name='Test Team',
            hackathon=self.hackathon,
            team_leader=self.user,
            current_round=3,
        )
        data = {
            'origin': 'Bhubaneswar',
            'destination': 'Delhi',
            'journey_date': '2026-08-01',
            'travel_mode': 'train',
            'ticket_type': 'individual',
            'travelers': [],
            'ticket_number': '1234567890',
            'ticket_amount': '2500.00',
        }
        response = self.client.post(reverse('team_add_travel'), data)
        self.assertRedirects(response, reverse('team_travel'))
        
        from team.team.models import TeamTravelDetail
        self.assertEqual(TeamTravelDetail.objects.filter(registration=self.reg).count(), 0)


from django.core.files.uploadedfile import SimpleUploadedFile
from features.models import Team
from events.models import CreativeMaterial

class TeamMemoriesUploadTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='lead_user',
            email='lead@example.com',
            password='password123',
        )
        self.profile = TeamleadProfile.objects.create(user=self.user)
        
        self.hackathon = Hackathon.objects.create(
            name='Test Hackathon',
            organization_name='Test Org',
            number_of_rounds=2,
            registration_close=timezone.localdate() + timezone.timedelta(days=5)
        )
        
        self.reg = TeamRegistration.objects.create(
            hackathon=self.hackathon,
            team_name='Test Team',
            team_leader=self.user,
        )
        
        self.team = Team.objects.create(
            team_name='Test Team',
            hackathon=self.hackathon,
            team_leader=self.user,
            current_round=1,  # Not qualified final round yet (number_of_rounds is 2)
        )
        self.reg.created_team = self.team
        self.reg.save()

    def test_upload_memories_unauthorized(self):
        self.client.login(username='lead_user', password='password123')
        
        # Team is in round 1, final round is 2. Cannot upload.
        mock_file = SimpleUploadedFile("image.png", b"file_content", content_type="image/png")
        data = {
            'title': 'Fun Memory',
            'file': mock_file,
        }
        response = self.client.post(reverse('team_memories'), data)
        self.assertRedirects(response, reverse('team_memories'))
        self.assertEqual(CreativeMaterial.objects.count(), 0)

    def test_upload_memories_authorized_success(self):
        self.client.login(username='lead_user', password='password123')
        
        # Promote team to round 3 (which is > number_of_rounds = 2, meaning qualified final round)
        self.team.current_round = 3
        self.team.save()
        
        mock_file = SimpleUploadedFile("image.jpg", b"file_content", content_type="image/jpeg")
        data = {
            'title': 'Winning Moment',
            'file': mock_file,
        }
        response = self.client.post(reverse('team_memories'), data)
        self.assertRedirects(response, reverse('team_memories'))
        
        self.assertEqual(CreativeMaterial.objects.count(), 1)
        material = CreativeMaterial.objects.first()
        self.assertEqual(material.title, 'Winning Moment')
        self.assertTrue(material.is_published)
        self.assertEqual(material.landing_sections, ['gallery'])

