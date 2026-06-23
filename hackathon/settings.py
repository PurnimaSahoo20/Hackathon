"""
Django settings for hackathon project.
"""

from django.apps import config
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _clean_env(name, default=''):
    value = os.getenv(name, default)
    if value is None:
        return default
    return value.strip().strip('"').strip("'")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key-change-this')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'accounts',
    'events',
    'features',
    'spoc.spoc.apps.SpocConfig',
    'mentor.mentor.apps.MentorConfig',
    'team.team.apps.TeamConfig',
    'jury',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.audit.AuditLogMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'hackathon.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.admin_permissions',
                'events.context_processors.active_event',
            ],
        },
    },
]

WSGI_APPLICATION = 'hackathon.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'Hackathon'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Manually added
AUTH_USER_MODEL = 'accounts.User'

# Auth settings
LOGIN_URL = '/accounts/'                     # Where @login_required redirects unauthenticated users
LOGIN_REDIRECT_URL = '/accounts/dashboard/'  # After successful Django auth (fallback)
LOGOUT_REDIRECT_URL = '/'                    # After logout

# -----------------------------------------------
# Email Configuration (SMTP via Gmail)
# -----------------------------------------------

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = _clean_env('EMAIL_HOST', 'smtp-mail.outlook.com')
EMAIL_PORT = int(_clean_env('EMAIL_PORT', '587'))
EMAIL_USE_TLS = _clean_env('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = _clean_env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = _clean_env('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = _clean_env(
    'DEFAULT_FROM_EMAIL',
    EMAIL_HOST_USER or 'HackNexus <no-reply@hacknexus.com>',
)

 
# Media Files
MEDIA_URL = '/media/'
# Local media folder — used when OneDrive storage is OFF, and as the source for
# `manage.py migrate_media_to_onedrive`.
MEDIA_ROOT = _clean_env('MEDIA_ROOT', default=str(BASE_DIR / 'media'))
 
# File Storage
# Django 5.x uses the STORAGES setting (DEFAULT_FILE_STORAGE was removed in 5.1).
# Flip USE_ONEDRIVE_STORAGE=True (and complete `manage.py onedrive_auth`) to push
# uploads to OneDrive via Microsoft Graph; otherwise files stay on the local disk.
USE_ONEDRIVE_STORAGE = _clean_env('USE_ONEDRIVE_STORAGE', default=False)
 
if USE_ONEDRIVE_STORAGE:
    _default_storage_backend = 'accounts.services.onedrive_storage.OneDriveMediaStorage'
else:
    _default_storage_backend = 'django.core.files.storage.FileSystemStorage'
 
STORAGES = {
    'default': {'BACKEND': _default_storage_backend},
    # Compressed (gzip/brotli) static serving via WhiteNoise. NOT the *manifest* variant —
    # that would rename Vite's already-hashed files and break index.html's references.
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
 

# OneDrive (Microsoft Graph) — delegated auth + proxied serving.
# Files land under <user OneDrive>/<ONEDRIVE_BASE_FOLDER>/<relative media path>.
ONEDRIVE_TENANT_ID = _clean_env('ONEDRIVE_TENANT_ID', default='')
ONEDRIVE_CLIENT_ID = _clean_env('ONEDRIVE_CLIENT_ID', default='')
# Space-separated delegated scopes (offline_access is added by MSAL automatically).
# Files.ReadWrite covers the signed-in user's own OneDrive and needs no admin consent;
# use Files.ReadWrite.All only to target a shared/other drive.
ONEDRIVE_SCOPES = _clean_env('ONEDRIVE_SCOPES', default='Files.ReadWrite').split()
ONEDRIVE_BASE_FOLDER = _clean_env('ONEDRIVE_BASE_FOLDER', default='assetMonitoringMediaFiles/media')
ONEDRIVE_TOKEN_CACHE = _clean_env(
    'ONEDRIVE_TOKEN_CACHE', default=str(BASE_DIR / '.onedrive_token_cache.json')
)



# CORS
CORS_ALLOW_ALL_ORIGINS = _clean_env('CORS_ALLOW_ALL_ORIGINS', default=True, cast=bool)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in _clean_env(
        'CSRF_TRUSTED_ORIGINS',
        default='http://hackathon.okcl.org',
    ).split(',')
    if origin.strip()
]