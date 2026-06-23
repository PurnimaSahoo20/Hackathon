"""Proxy view that streams media files from OneDrive at the existing /media/ URLs.
 
Keeps the frontend contract intact: ``FileField.url`` still returns ``/media/<path>``,
and this view fetches the bytes from OneDrive (Microsoft Graph) on demand and streams
them back. Access is left open to match the previous local ``static()`` serving; wrap
it with an auth check if you later want media behind login.
 
Images and PDFs are served ``inline`` so they render in the browser; everything else is
sent as an ``attachment`` download.
"""
import mimetypes
 
from django.http import Http404, StreamingHttpResponse
from django.views.decorators.cache import cache_control
 
from accounts.services.onedrive_storage import OneDriveClient, OneDriveError
 
# Content types the browser should display in-page rather than download.
INLINE_TYPES = {"application/pdf"}
 
 
def _is_inline(content_type):
    return content_type in INLINE_TYPES or content_type.startswith("image/")
 
 
@cache_control(private=True, max_age=3600)
def serve_media(request, path):
    client = OneDriveClient()
    try:
        upstream = client.download_stream(path)
    except OneDriveError:
        raise Http404("Media not found")
    if upstream is None:
        raise Http404("Media not found")
 
    filename = path.rsplit("/", 1)[-1]
    # Trust the file extension over OneDrive's CDN, which often returns octet-stream.
    content_type = (
        mimetypes.guess_type(filename)[0]
        or upstream.headers.get("Content-Type")
        or "application/octet-stream"
    )
 
    response = StreamingHttpResponse(
        upstream.iter_content(chunk_size=64 * 1024),
        content_type=content_type,
    )
    if "Content-Length" in upstream.headers:
        response["Content-Length"] = upstream.headers["Content-Length"]
 
    disposition = "inline" if _is_inline(content_type) else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response
 
 