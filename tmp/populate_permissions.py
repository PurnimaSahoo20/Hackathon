import os
import sys
import django

# Add the project root to the sys.path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hackathon.settings')
django.setup()

from accounts.models import AdminPermission

def populate_permissions():
    # 1. Clear existing permissions
    print("Clearing existing AdminPermissions...")
    AdminPermission.objects.all().delete()

    # 2. Define the 14 functionalities
    permissions_data = [
        ("SPOC & College Management", "spoc_college_mgt", "Invite and manage institutions and SPOCs"),
        ("Jury Onboarding & Management", "jury_onboarding_mgt", "Invite and manage jury evaluation workflow"),
        ("Media & Sponsorship Management", "media_sponsorship_mgt", "Handle podcasts, documentaries, and sponsors"),
        ("Social Media & Creative Management", "social_media_creative_mgt", "Branding, promotion, and creative assets"),
        ("Venue & Logistics Management", "venue_logistics_mgt", "Accommodation, food, and venue allocation"),
        ("Financial Management", "financial_mgt", "Budget, expenses, and sponsorship funds"),
        ("Awards & Certification Management", "awards_certification_mgt", "Certificates, trophies, and awards"),
        ("Accommodation & Health Support Management", "accommodation_health_mgt", "Guest stay and emergency healthcare"),
        ("Announcement & Communication System", "announcement_communication_sys", "Official announcements and group messaging"),
        ("Team & Event Monitoring", "team_event_monitoring", "Track progress and registrations"),
        ("Problem Statement & Content Management", "problem_statement_content_mgt", "Manage and update problem statements and resources"),
        ("Evaluation Coordination", "evaluation_coordination", "Assign jury and monitor scoring"),
        ("Reporting & Result Management", "reporting_result_mgt", "Generate reports and publish results"),
        ("Feedback & Support Management", "feedback_support_mgt", "Handle queries and support tickets"),
    ]

    print("Creating 14 standard AdminPermissions...")
    for name, codename, desc in permissions_data:
        AdminPermission.objects.create(name=name, codename=codename, description=desc)
        print(f" - Created: {name}")

    print("Done!")

if __name__ == "__main__":
    populate_permissions()
