"""
URL configuration for hackathon project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

import events.views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),

    # New modular app URL prefixes (alias — all view names preserved)
    path('events/', include('events.urls')),
    path('features/', include('features.urls')),

    path('spoc/', include('spoc.spoc.urls')),
    path('mentor/', include('mentor.mentor.urls')),
    path('team/', include('team.team.urls')),
    path('jury/', include('jury.urls')),



    # Root URL → Public Landing Page
    path('', events.views.landing_page, name='landing_page'),
]

if settings.USE_ONEDRIVE_STORAGE:
    # Serve media by streaming from OneDrive at the same /media/<path> URLs.
    from accounts.serve_media import serve_media
    urlpatterns += [path('media/<path:path>', serve_media, name='media-proxy')]
else:
    # Local disk serving (dev).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
 