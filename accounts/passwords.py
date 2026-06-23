import re
import secrets
import string

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


PORTAL_PASSWORD_HELP_TEXT = (
    "Use at least 8 characters with 1 uppercase letter, 1 lowercase letter, "
    "1 number, and 1 special character."
)


def generate_password(length=12):
    """Generate a password that satisfies the portal validation rules."""
    if length < 8:
        length = 8

    alphabet = string.ascii_letters + string.digits + "!@#$%"

    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        try:
            validate_portal_password(password)
            return password
        except ValidationError:
            continue


def validate_portal_password(password, user=None):
    errors = []

    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        errors.extend(exc.messages)

    checks = [
        (r"[A-Z]", "Password must include at least one uppercase letter."),
        (r"[a-z]", "Password must include at least one lowercase letter."),
        (r"\d", "Password must include at least one number."),
        (r"[^A-Za-z0-9]", "Password must include at least one special character."),
    ]

    for pattern, message in checks:
        if not re.search(pattern, password or ""):
            errors.append(message)

    if errors:
        raise ValidationError(errors)
