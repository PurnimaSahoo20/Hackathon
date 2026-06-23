"""
OneDrive (Microsoft Graph) media storage backend — delegated auth, proxied serving.
 
Files are stored under ``ONEDRIVE_BASE_FOLDER`` (default: ``assetMonitoringMediaFiles/media``)
inside the signed-in user's OneDrive for Business drive. A Django ``FileField`` ``name``
(a relative path such as ``site_readiness/project_2/.../x.jpg``) maps 1:1 to the OneDrive
item path ``<base>/<name>`` — so existing DB values keep resolving once the bytes are
migrated to the same relative path.
 
Auth is delegated OAuth2 with a refresh token, managed by MSAL with a persistent token
cache file. Bootstrap the cache once with::
 
    python manage.py onedrive_auth
 
Serving is proxied: ``url(name)`` returns ``<MEDIA_URL><name>``, handled by the media
proxy view, so existing frontend code using ``.url`` works unchanged.
"""
from __future__ import annotations
 
import os
import threading
import time
from urllib.parse import quote
 
import msal
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
 
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
    """
 
    _lock = threading.Lock()
    _token = None          # cached access token (class-wide)
    _token_expiry = 0.0    # epoch seconds when the cached token expires
 
    def __init__(self):
        self.tenant_id = settings.ONEDRIVE_TENANT_ID
        self.client_id = settings.ONEDRIVE_CLIENT_ID
        self.scopes = settings.ONEDRIVE_SCOPES
        self.cache_path = settings.ONEDRIVE_TOKEN_CACHE
        self.base_folder = settings.ONEDRIVE_BASE_FOLDER.strip("/")
 
    # --- token / cache ---------------------------------------------------
    def _load_cache(self):
        cache = msal.SerializableTokenCache()
        if os.path.exists(self.cache_path):
            with open(self.cache_path, "r") as fh:
                cache.deserialize(fh.read())
        return cache
 
    def _save_cache(self, cache):
        if cache.has_state_changed:
            directory = os.path.dirname(self.cache_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.cache_path, "w") as fh:
                fh.write(cache.serialize())
 
    def _build_app(self, cache):
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        return msal.PublicClientApplication(
            self.client_id, authority=authority, token_cache=cache
        )
 
    def get_token(self):
        # Fast path: reuse the in-memory token until ~1 min before expiry.
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        with self._lock:
            if self._token and time.time() < self._token_expiry - 60:
                return self._token
            cache = self._load_cache()
            app = self._build_app(cache)
            accounts = app.get_accounts()
            result = None
            if accounts:
                result = app.acquire_token_silent(self.scopes, account=accounts[0])
            self._save_cache(cache)
            if not result or "access_token" not in result:
                raise OneDriveError(
                    "No valid OneDrive token. Run `python manage.py onedrive_auth` "
                    "to sign in and create the token cache."
                )
            OneDriveClient._token = result["access_token"]
            OneDriveClient._token_expiry = time.time() + int(result.get("expires_in", 3600))
            return self._token
 
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
 
