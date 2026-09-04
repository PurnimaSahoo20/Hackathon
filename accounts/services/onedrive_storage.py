"""
OneDrive (Microsoft Graph) media storage backend — delegated auth, proxied serving.

Files are stored under ``ONEDRIVE_BASE_FOLDER`` (default: ``hackathonMediaFiles/media``)
inside the signed-in user's OneDrive for Business drive. A Django ``FileField`` ``name``
(a relative path such as ``site_readiness/project_2/.../x.jpg``) maps 1:1 to the OneDrive
item path ``<base>/<name>`` — so existing DB values keep resolving once the bytes are
migrated to the same relative path.

Auth is delegated OAuth2 with a refresh token, managed by MSAL with a persistent token
cache file. Bootstrap the cache once with::

    python manage.py onedrive_auth

Token lifecycle (fully automatic after initial bootstrap):
    1. Access tokens expire after ~1 hour
    2. MSAL's acquire_token_silent() uses the cached refresh token to obtain
       new access tokens — no user interaction needed
    3. Refresh tokens are rolling (~90 days) — each use extends the lifetime
    4. Only if the refresh token itself expires does re-authentication occur,
       which is handled automatically via interactive browser login

Serving is proxied: ``url(name)`` returns ``<MEDIA_URL><name>``, handled by the media
proxy view, so existing frontend code using ``.url`` works unchanged.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import quote

import msal
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

logger = logging.getLogger(__name__)

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
# Microsoft Graph allows a simple upload up to 4 MiB; larger files need an upload session.
SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024
# Upload-session chunks must be multiples of 320 KiB; 10 MiB is a safe, aligned size.
UPLOAD_CHUNK = 10 * 1024 * 1024


class OneDriveError(Exception):
    """Raised for any non-success response from Microsoft Graph."""


class OneDriveClient:
    """Thin Microsoft Graph client with a cached, auto-refreshing delegated token.

    The access token is cached process-wide (class attributes) so concurrent requests
    share one token; refreshes happen transparently via the MSAL token cache on disk.

    Token acquisition flow:
        Request → get_token()
            → Step 1: Check in-memory cache (valid for ~1 hour)
            → Step 2: acquire_token_silent() — MSAL uses cached refresh token
                       to get a new access token (no user interaction)
            → Step 3: acquire_token_interactive() — opens browser for re-auth
                       (only when refresh token itself has expired)
            → Each successful acquisition saves the cache to disk
    """

    _lock = threading.Lock()
    _token = None          # cached access token (class-wide)
    _token_expiry = 0.0    # epoch seconds when the cached token expires

    def __init__(self):
        self.tenant_id = settings.ONEDRIVE_TENANT_ID
        self.client_id = settings.ONEDRIVE_CLIENT_ID
        self.scopes = settings.ONEDRIVE_SCOPES
        self.cache_path = Path(settings.ONEDRIVE_TOKEN_CACHE)
        self.base_folder = settings.ONEDRIVE_BASE_FOLDER.strip("/")

    # --- token / cache ---------------------------------------------------
    def _load_cache(self):
        """Load the MSAL token cache from disk.

        The cache contains refresh tokens, account info, and (possibly stale)
        access tokens. MSAL uses the refresh token to silently acquire new
        access tokens without user interaction.
        """
        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                cache.deserialize(
                    self.cache_path.read_text(encoding="utf-8")
                )
            except Exception:
                logger.warning(
                    "OneDrive token cache is corrupted or unreadable. "
                    "A fresh authentication will be attempted."
                )
                # Return a fresh cache — the fallback auth flow will populate it
                cache = msal.SerializableTokenCache()
        return cache

    def _save_cache(self, cache):
        """Persist the MSAL token cache to disk with backup.

        Called after every successful token acquisition so the updated
        refresh token (rolling lifetime) is preserved. A backup copy is
        kept in case the write is interrupted.
        """
        if cache.has_state_changed:
            try:
                # Create a backup before overwriting
                if self.cache_path.exists():
                    backup_path = self.cache_path.with_suffix('.backup.json')
                    shutil.copy2(str(self.cache_path), str(backup_path))

                directory = self.cache_path.parent
                if directory and not directory.exists():
                    directory.mkdir(parents=True, exist_ok=True)

                self.cache_path.write_text(
                    cache.serialize(), encoding="utf-8"
                )
                logger.debug("OneDrive token cache saved successfully.")
            except Exception as e:
                logger.error(f"Failed to save OneDrive token cache: {e}")

    def _build_app(self, cache):
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        return msal.PublicClientApplication(
            self.client_id, authority=authority, token_cache=cache
        )

    def _update_token(self, result):
        """Store the new access token in the class-level in-memory cache."""
        OneDriveClient._token = result["access_token"]
        OneDriveClient._token_expiry = time.time() + int(
            result.get("expires_in", 3600)
        )

    def get_token(self):
        """Get a valid access token, refreshing automatically if needed.

        MSAL handles the full token lifecycle:
        - If a valid access token is in memory → use it (fast path)
        - If expired → MSAL uses the cached refresh token to get a new one
        - If refresh token is also expired → interactive browser login
        """
        # Fast path: reuse the in-memory token until ~1 min before expiry.
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        with self._lock:
            # Double-check after acquiring lock (another thread may have refreshed)
            if self._token and time.time() < self._token_expiry - 60:
                return self._token

            cache = self._load_cache()
            app = self._build_app(cache)
            accounts = app.get_accounts()

            # ----- Step 1: Silent acquisition (uses refresh token) -----
            # This is the normal path. MSAL checks the cache for a valid
            # access token; if expired, it uses the refresh token to obtain
            # a new one from Microsoft. No user interaction required.
            if accounts:
                result = app.acquire_token_silent(
                    scopes=self.scopes,
                    account=accounts[0],
                )
                if result and "access_token" in result:
                    self._save_cache(cache)
                    self._update_token(result)
                    logger.debug(
                        "OneDrive access token refreshed silently via MSAL cache."
                    )
                    return self._token
                else:
                    error_info = result.get("error_description", "") if result else ""
                    logger.warning(
                        "MSAL silent token acquisition failed. "
                        "The refresh token may have expired. "
                        f"Attempting re-authentication... ({error_info})"
                    )

            # ----- Step 2: Interactive login (opens browser) -----
            # This runs only when the refresh token has expired or the cache
            # has no accounts. It opens a browser window for the user to
            # sign in. Works on dev machines with a browser available.
            # Note: Requires http://localhost as a redirect URI in the
            # Azure AD app registration (Platform: Mobile & desktop apps).
            result = self._attempt_interactive_login(app)
            if result and "access_token" in result:
                self._save_cache(cache)
                self._update_token(result)
                account_name = (
                    result.get("id_token_claims", {})
                    .get("preferred_username", "unknown")
                )
                logger.info(
                    f"OneDrive re-authenticated via interactive login as {account_name}. "
                    f"Token cache updated."
                )
                return self._token

            # ----- Step 3: All automatic methods failed -----
            raise OneDriveError(
                "OneDrive authentication failed. All automatic refresh methods "
                "have been exhausted.\n"
                "This means:\n"
                "  - No valid refresh token exists in the cache\n"
                "  - Interactive browser login was not possible\n\n"
                "To fix this, run:\n"
                "  python manage.py onedrive_auth\n\n"
                "This will open a device-code or browser flow to re-authenticate."
            )

    def _attempt_interactive_login(self, app):
        """Attempt interactive browser login for re-authentication.

        Opens a browser window for the user to sign in with their Microsoft
        account. MSAL starts a temporary local HTTP server to receive the
        OAuth redirect callback.

        This works on development machines with a browser available.
        On headless servers, this will fail gracefully and the error message
        will direct the admin to use the management command instead.
        """
        try:
            logger.info(
                "Opening browser for OneDrive re-authentication..."
            )
            print(
                "\n" + "=" * 60 + "\n"
                "ONEDRIVE RE-AUTHENTICATION REQUIRED\n"
                "A browser window will open for you to sign in.\n"
                "=" * 60 + "\n"
            )
            result = app.acquire_token_interactive(scopes=self.scopes)

            if result and "access_token" in result:
                return result
            else:
                error = result.get("error", "unknown_error") if result else "no_result"
                description = (
                    result.get("error_description", "Authentication failed.")
                    if result else "No result returned."
                )
                logger.warning(
                    f"Interactive authentication failed: {error}: {description}"
                )
                return None
        except Exception as e:
            logger.warning(
                f"Interactive authentication not available (possibly headless "
                f"environment): {e}"
            )
            return None
 
    def _headers(self, extra=None):
        headers = {"Authorization": f"Bearer {self.get_token()}"}
        if extra:
            headers.update(extra)
        return headers
 
    # --- path helpers ----------------------------------------------------
    def _encoded_path(self, name):
        full = f"{self.base_folder}/{name.lstrip('/')}"
        # Percent-encode each segment but keep the slashes as path separators.
        return quote(full, safe="/")
 
    def _root_url(self, name):
        return f"{GRAPH_ROOT}/me/drive/root:/{self._encoded_path(name)}"
 
    # --- operations ------------------------------------------------------
    def upload(self, name, data: bytes):
        """Upload bytes to ``<base>/<name>``, creating intermediate folders as needed."""
        if len(data) <= SIMPLE_UPLOAD_LIMIT:
            resp = requests.put(
                f"{self._root_url(name)}:/content",
                headers=self._headers({"Content-Type": "application/octet-stream"}),
                data=data,
                timeout=120,
            )
            if resp.status_code not in (200, 201):
                raise OneDriveError(f"Upload failed ({resp.status_code}): {resp.text[:300]}")
            return name
        return self._upload_session(name, data)
 
    def _upload_session(self, name, data):
        create = requests.post(
            f"{self._root_url(name)}:/createUploadSession",
            headers=self._headers({"Content-Type": "application/json"}),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=60,
        )
        if create.status_code not in (200, 201):
            raise OneDriveError(
                f"Upload session failed ({create.status_code}): {create.text[:300]}"
            )
        upload_url = create.json()["uploadUrl"]
        total = len(data)
        start = 0
        while start < total:
            end = min(start + UPLOAD_CHUNK, total)
            chunk = data[start:end]
            resp = requests.put(
                upload_url,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end - 1}/{total}",
                },
                data=chunk,
                timeout=300,
            )
            if resp.status_code not in (200, 201, 202):
                raise OneDriveError(
                    f"Chunk upload failed ({resp.status_code}): {resp.text[:300]}"
                )
            start = end
        return name
 
    def get_metadata(self, name):
        """Return the item's metadata dict, or ``None`` if it does not exist."""
        resp = requests.get(self._root_url(name), headers=self._headers(), timeout=60)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise OneDriveError(f"Metadata failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()
 
    def download(self, name):
        """Return the full file content as bytes."""
        resp = requests.get(
            f"{self._root_url(name)}:/content", headers=self._headers(), timeout=300
        )
        if resp.status_code == 404:
            raise OneDriveError(f"Not found: {name}")
        if resp.status_code != 200:
            raise OneDriveError(f"Download failed ({resp.status_code}): {resp.text[:300]}")
        return resp.content
 
    def download_stream(self, name):
        """Return a streaming ``requests.Response`` for proxying, or ``None`` if missing."""
        resp = requests.get(
            f"{self._root_url(name)}:/content",
            headers=self._headers(),
            stream=True,
            timeout=300,
            allow_redirects=True,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise OneDriveError(f"Download failed ({resp.status_code}): {resp.text[:300]}")
        return resp
 
    def delete(self, name):
        resp = requests.delete(self._root_url(name), headers=self._headers(), timeout=60)
        if resp.status_code not in (204, 404):
            raise OneDriveError(f"Delete failed ({resp.status_code}): {resp.text[:300]}")
 
 
@deconstructible
class OneDriveMediaStorage(Storage):
    """Django storage backend that persists media to OneDrive via Microsoft Graph."""
 
    def __init__(self):
        self.client = OneDriveClient()
 
    def _save(self, name, content):
        content.seek(0)
        data = content.read()
        if not isinstance(data, bytes):
            data = data.encode()
        self.client.upload(name, data)
        return name
 
    def _open(self, name, mode="rb"):
        return ContentFile(self.client.download(name), name=name)
 
    def exists(self, name):
        return self.client.get_metadata(name) is not None
 
    def delete(self, name):
        if name:
            self.client.delete(name)
 
    def size(self, name):
        meta = self.client.get_metadata(name)
        return meta.get("size", 0) if meta else 0
 
    def url(self, name):
        base = settings.MEDIA_URL
        if not base.endswith("/"):
            base += "/"
        return f"{base}{quote(name.lstrip('/'), safe='/')}"
 
    # Filesystem-only metadata is not available from Graph cheaply; not needed by the app.
    def get_accessed_time(self, name):
        raise NotImplementedError("OneDrive storage does not expose accessed time.")
 
    def get_created_time(self, name):
        raise NotImplementedError("OneDrive storage does not expose created time.")
 
    def get_modified_time(self, name):
        raise NotImplementedError("OneDrive storage does not expose modified time.")
 
    def listdir(self, path):
        raise NotImplementedError("OneDrive storage does not support listdir().")
 
