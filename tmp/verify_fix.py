import os
import django
from django.conf import settings
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hackathon.settings')
django.setup()

from accounts.models import User, SuperadminProfile, Role
from accounts.views import superadmin_dashboard, _redirect_by_role

# 1. Create a superuser if it doesn't exist
username = 'test_super'
password = 'testpassword123'
user, created = User.objects.get_or_create(username=username, is_superuser=True, is_staff=True)
if created:
    user.set_password(password)
    user.save()

# Ensure it doesn't have a profile yet (simulation of createsuperuser)
SuperadminProfile.objects.filter(user=user).delete()

print(f"Created/found superuser: {user.username}")
print(f"Has SuperadminProfile: {hasattr(user, 'superadmin_profile')}")

# 2. Test _redirect_by_role
redirect_res = _redirect_by_role(user)
print(f"Redirect destination: {redirect_res.url}")

# 3. Test superadmin_dashboard (ensure it creates the profile)
factory = RequestFactory()
request = factory.get('/accounts/dashboard/')
request.user = user

# Add messages middleware support
setattr(request, '_messages', FallbackStorage(request))

response = superadmin_dashboard(request)
print(f"Dashboard response status: {response.status_code}")
print(f"Has SuperadminProfile now: {hasattr(user, 'superadmin_profile')}")

if hasattr(user, 'superadmin_profile'):
    print("SUCCESS: Profile auto-created and access granted.")
else:
    print("FAILURE: Profile not created.")

# Cleanup
# SuperadminProfile.objects.filter(user=user).delete()
# user.delete()
