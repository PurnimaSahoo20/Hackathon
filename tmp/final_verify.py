import os
import django
from django.conf import settings
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hackathon.settings')
django.setup()

from accounts.models import User, Role, AdminProfile
from accounts.views import superadmin_dashboard, _redirect_by_role

# Helper to mock messages
def setup_request(user):
    factory = RequestFactory()
    request = factory.get('/')
    request.user = user
    setattr(request, '_messages', FallbackStorage(request))
    return request

# 1. Create a superuser and a normal admin
super_role, _ = Role.objects.get_or_create(name='Super Admin')
admin_role, _ = Role.objects.get_or_create(name='Admin')

super_user, _ = User.objects.get_or_create(username='test_super_perm', is_superuser=True)
admin_user, _ = User.objects.get_or_create(username='test_admin_perm', is_superuser=False, role=admin_role)
AdminProfile.objects.get_or_create(user=admin_user)

print("--- Testing Redirection ---")
print(f"Super Admin redirect: {_redirect_by_role(super_user).url}")
print(f"Admin redirect: {_redirect_by_role(admin_user).url}")

print("\n--- Testing Superadmin Dashboard Access ---")
# Superuser access
req_super = setup_request(super_user)
resp_super = superadmin_dashboard(req_super)
print(f"Super User status: {resp_super.status_code}") # Should be 200

# Normal admin access (should be blocked)
req_admin = setup_request(admin_user)
resp_admin = superadmin_dashboard(req_admin)
print(f"Admin User status (should be 302/redirect): {resp_admin.status_code}")
print(f"Admin User redirect target: {resp_admin.url}")

if resp_super.status_code == 200 and resp_admin.status_code == 302:
    print("\nVERIFICATION SUCCESSFUL")
else:
    print("\nVERIFICATION FAILED")
