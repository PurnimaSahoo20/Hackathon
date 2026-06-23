import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hackathon.settings')
django.setup()

from accounts.models import AdminPermission

PERMISSIONS = [
    ('Admin Authentication & Dashboard Access', 'admin_auth', 'Secure login and dashboard access'),
    ('SPOC & College Management', 'spoc_college', 'Invite and manage institutions and SPOCs'),
    ('Jury Onboarding & Management', 'jury_mgt', 'Invite and manage jury evaluation workflow'),
    ('Media & Sponsorship Management', 'media_sponsorship', 'Handle podcasts, documentaries, and sponsors'),
    ('Social Media & Creative Management', 'social_creative', 'Branding, promotion, and creative assets'),
    ('Venue & Logistics Management', 'venue_logistics', 'Accommodation, food, and venue allocation'),
    ('Financial Management', 'financial_mgt', 'Budget, expenses, and sponsorship funds'),
    ('Awards & Certification Management', 'awards_cert', 'Certificates, trophies, and awards'),
    ('Accommodation & Health Support', 'acc_health', 'Guest stay and emergency healthcare'),
    ('Announcement & Communication', 'communication', 'Official announcements and group messaging'),
    ('Team & Event Monitoring', 'team_monitoring', 'Track progress and registrations'),
    ('Problem Statement Management', 'ps_content', 'Manage and update problem statements and resources'),
    ('Evaluation Coordination', 'eval_coordination', 'Assign jury and monitor scoring'),
    ('Reporting & Result Management', 'reporting_result', 'Generate reports and publish results'),
    ('Feedback & Support Management', 'feedback_support', 'Handle queries and support tickets')
]

def seed_permissions():
    print("Seeding Administrative Permissions...")
    for name, codename, desc in PERMISSIONS:
        perm, created = AdminPermission.objects.get_or_create(
            codename=codename,
            defaults={'name': name, 'description': desc}
        )
        if created:
            print(f"Created: {name}")
        else:
            print(f"Existing: {name}")

if __name__ == "__main__":
    seed_permissions()
