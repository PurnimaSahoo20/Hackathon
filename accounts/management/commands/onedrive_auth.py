"""Sign in to OneDrive and persist the delegated token cache.

Supports two authentication modes:

1. **Device-code flow** (default) — works on any machine, including headless servers::

       python manage.py onedrive_auth

   Prints a URL and a code; open the URL in any browser, enter the code,
   and sign in with the OneDrive account whose drive should hold the media.

2. **Interactive browser flow** — faster on machines with a browser::

       python manage.py onedrive_auth --interactive

   Opens a browser window directly for sign-in.

The resulting refresh token is stored in ONEDRIVE_TOKEN_CACHE and refreshed
automatically by the OneDriveClient during normal operation. You only need
to run this command:
  - Once for initial setup
  - If the refresh token expires (after ~90 days of inactivity)
"""
import os
import shutil
from pathlib import Path

import msal
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Authenticate with OneDrive and store the token cache. "
        "Use --interactive for browser-based auth, or default device-code flow."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--interactive',
            action='store_true',
            help=(
                'Use interactive browser login instead of device-code flow. '
                'Requires a browser on this machine and http://localhost '
                'redirect URI configured in Azure AD app registration.'
            ),
        )

    def handle(self, *args, **options):
        tenant = settings.ONEDRIVE_TENANT_ID
        client_id = settings.ONEDRIVE_CLIENT_ID
        scopes = settings.ONEDRIVE_SCOPES
        cache_path = Path(settings.ONEDRIVE_TOKEN_CACHE)
        use_interactive = options.get('interactive', False)

        if not tenant or not client_id:
            self.stderr.write(self.style.ERROR(
                "Set ONEDRIVE_TENANT_ID and ONEDRIVE_CLIENT_ID in .env first."
            ))
            return

        # Load existing cache (preserves any existing tokens)
        cache = msal.SerializableTokenCache()
        if cache_path.exists():
            try:
                cache.deserialize(cache_path.read_text(encoding="utf-8"))
                self.stdout.write(
                    "Loaded existing token cache. "
                    "Existing tokens will be preserved."
                )
            except Exception:
                self.stdout.write(self.style.WARNING(
                    "Existing cache is corrupted. Starting with a fresh cache."
                ))
                cache = msal.SerializableTokenCache()

        app = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant}",
            token_cache=cache,
        )

        # Try silent acquisition first — maybe the cache already has a valid token
        accounts = app.get_accounts()
        if accounts:
            self.stdout.write(
                f"Found cached account: {accounts[0].get('username', 'unknown')}. "
                f"Attempting silent token refresh..."
            )
            result = app.acquire_token_silent(scopes=scopes, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache(cache, cache_path)
                account = accounts[0].get('username', 'unknown')
                self.stdout.write(self.style.SUCCESS(
                    f"Token refreshed silently for {account}. "
                    f"No re-authentication needed! Cache saved to {cache_path}"
                ))
                return

            self.stdout.write(self.style.WARNING(
                "Silent refresh failed. Proceeding with full authentication..."
            ))

        # Authenticate based on selected mode
        if use_interactive:
            result = self._interactive_auth(app, scopes)
        else:
            result = self._device_code_auth(app, scopes)

        if not result:
            return  # Error already printed

        if "access_token" not in result:
            self.stderr.write(self.style.ERROR(
                f"Authentication failed: "
                f"{result.get('error_description', result)}"
            ))
            return

        # Save the cache with backup
        self._save_cache(cache, cache_path)

        account = (
            (result.get("id_token_claims") or {})
            .get("preferred_username", "unknown")
        )
        expires_in = result.get("expires_in", 3600)

        self.stdout.write(self.style.SUCCESS(
            f"\n{'=' * 50}\n"
            f"Successfully authenticated as: {account}\n"
            f"Token cache saved to: {cache_path}\n"
            f"Access token expires in: {expires_in} seconds\n"
            f"Refresh token: will auto-renew for ~90 days\n"
            f"{'=' * 50}\n\n"
            f"Your application will now automatically refresh tokens.\n"
            f"No manual action needed unless the refresh token expires\n"
            f"(after ~90 days of inactivity)."
        ))

    def _device_code_auth(self, app, scopes):
        """Authenticate via device-code flow (works on headless servers)."""
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            self.stderr.write(self.style.ERROR(
                f"Failed to start device flow: {flow}"
            ))
            return None

        self.stdout.write(self.style.WARNING(
            f"\n{'=' * 50}\n{flow['message']}\n{'=' * 50}\n"
        ))

        # Blocks until user completes auth in browser or flow expires
        result = app.acquire_token_by_device_flow(flow)
        return result

    def _interactive_auth(self, app, scopes):
        """Authenticate via interactive browser flow."""
        self.stdout.write(
            "Opening browser for authentication...\n"
            "If the browser doesn't open automatically, check your "
            "Azure AD app registration for http://localhost redirect URI."
        )

        try:
            result = app.acquire_token_interactive(scopes=scopes)
            return result
        except Exception as e:
            self.stderr.write(self.style.ERROR(
                f"Interactive authentication failed: {e}\n\n"
                f"This usually means:\n"
                f"  1. No browser available on this machine, OR\n"
                f"  2. http://localhost redirect URI not configured in Azure AD\n\n"
                f"Try using device-code flow instead:\n"
                f"  python manage.py onedrive_auth"
            ))
            return None

    def _save_cache(self, cache, cache_path):
        """Save the token cache with a backup of the previous version."""
        try:
            if cache_path.exists():
                backup_path = cache_path.with_suffix('.backup.json')
                shutil.copy2(str(cache_path), str(backup_path))
                self.stdout.write(
                    f"Previous cache backed up to {backup_path}"
                )

            directory = cache_path.parent
            if directory and not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)

            cache_path.write_text(cache.serialize(), encoding="utf-8")
        except Exception as e:
            self.stderr.write(self.style.ERROR(
                f"Failed to save token cache: {e}"
            ))
