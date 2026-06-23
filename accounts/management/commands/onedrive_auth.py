"""Sign in to OneDrive once (device-code flow) and persist the delegated token cache.
 
Run on a machine with a browser available::
 
    python manage.py onedrive_auth
 
It prints a URL and a code; open the URL, enter the code, and sign in with the
OneDrive for Business account whose drive should hold the media. The resulting refresh
token is stored in ONEDRIVE_TOKEN_CACHE and refreshed automatically thereafter.
"""
import os
 
import msal
from django.conf import settings
from django.core.management.base import BaseCommand
 
 
class Command(BaseCommand):
    help = "Authenticate with OneDrive (device-code flow) and store the token cache."
 
    def handle(self, *args, **options):
        tenant = settings.ONEDRIVE_TENANT_ID
        client_id = settings.ONEDRIVE_CLIENT_ID
        scopes = settings.ONEDRIVE_SCOPES
        cache_path = settings.ONEDRIVE_TOKEN_CACHE
 
        if not tenant or not client_id:
            self.stderr.write(self.style.ERROR(
                "Set ONEDRIVE_TENANT_ID and ONEDRIVE_CLIENT_ID in .env first."
            ))
            return
 
        cache = msal.SerializableTokenCache()
        if os.path.exists(cache_path):
            with open(cache_path, "r") as fh:
                cache.deserialize(fh.read())
 
        app = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant}",
            token_cache=cache,
        )
 
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            self.stderr.write(self.style.ERROR(f"Failed to start device flow: {flow}"))
            return
 
        self.stdout.write(self.style.WARNING(flow["message"]))
        result = app.acquire_token_by_device_flow(flow)  # blocks until you finish in the browser
 
        if "access_token" not in result:
            self.stderr.write(self.style.ERROR(
                f"Authentication failed: {result.get('error_description', result)}"
            ))
            return
 
        directory = os.path.dirname(cache_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(cache_path, "w") as fh:
            fh.write(cache.serialize())
 
        account = (result.get("id_token_claims") or {}).get("preferred_username", "unknown")
        self.stdout.write(self.style.SUCCESS(
            f"Signed in as {account}. Token cache saved to {cache_path}"
        ))
