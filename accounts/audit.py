import datetime
import decimal
import threading
import uuid

from django.db import models


_audit_context = threading.local()

REDACTED_VALUE = '[redacted]'
SENSITIVE_FIELD_PARTS = (
    'password',
    'otp',
    'code',
    'secret',
    'token',
    'api_key',
    'apikey',
)


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _audit_context.request = request
        try:
            return self.get_response(request)
        finally:
            _audit_context.request = None


def get_current_request():
    return getattr(_audit_context, 'request', None)


def get_current_actor():
    request = get_current_request()
    if not request:
        return None

    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return user
    return None


def get_request_meta():
    request = get_current_request()
    if not request:
        return {
            'request_method': '',
            'request_path': '',
            'ip_address': None,
            'user_agent': '',
        }

    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    ip_address = forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR')

    return {
        'request_method': request.method,
        'request_path': request.get_full_path(),
        'ip_address': ip_address or None,
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
    }


def serialize_instance(instance):
    data = {}
    for field in instance._meta.concrete_fields:
        if isinstance(field, models.BinaryField):
            continue

        field_name = field.name
        value = field.value_from_object(instance)

        if _is_sensitive_field(field_name):
            data[field_name] = REDACTED_VALUE if value not in (None, '') else value
        else:
            data[field_name] = _serialize_value(value)

    return data


def diff_values(before, after):
    changes = {}
    for key in sorted(set(before) | set(after)):
        old_value = before.get(key)
        new_value = after.get(key)
        if old_value != new_value:
            changes[key] = {
                'from': old_value,
                'to': new_value,
            }
    return changes


def _is_sensitive_field(field_name):
    normalized = field_name.lower()
    return any(part in normalized for part in SENSITIVE_FIELD_PARTS)


def _serialize_value(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (decimal.Decimal, uuid.UUID)):
        return str(value)
    if hasattr(value, 'name'):
        return value.name
    return value
