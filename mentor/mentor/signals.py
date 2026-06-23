"""mentor/signals.py — create Mentor account after admin approval of MentorInvitation."""
import secrets, string, logging
from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .models import MentorInvitation

logger = logging.getLogger(__name__)

def _gen_password(length=12):
    return ''.join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(length))

def provision_mentor_account(instance, resend_email=False):
    if instance.status != 'admin_approved':
        return None
    from accounts.models import User, Role, MentorProfile
    from features.models import TeamMentor

    with transaction.atomic():
        plain_pw = _gen_password()
        role, _ = Role.objects.get_or_create(name='Mentor', defaults={'description': 'Hackathon Mentor'})
        username = (instance.mentor_email or '').strip().lower()
        existing_user = instance.created_user

        if existing_user is None:
            existing_user = User.objects.filter(email__iexact=instance.mentor_email).first()
        if existing_user is None:
            existing_user = User.objects.filter(username=username).first()

        if existing_user is None:
            try:
                user = User.objects.create_user(
                    username=username, email=instance.mentor_email,
                    password=plain_pw,
                    first_name=instance.mentor_name.split()[0] if instance.mentor_name else '',
                    last_name=' '.join(instance.mentor_name.split()[1:]) if instance.mentor_name else '',
                    phone_number=instance.mentor_phone or None,
                    role=role, is_active=True, is_verified=True,
                )
            except IntegrityError:
                user = User.objects.get(email__iexact=instance.mentor_email)
        else:
            user = existing_user
            user.email = instance.mentor_email
            user.first_name = instance.mentor_name.split()[0] if instance.mentor_name else user.first_name
            user.last_name = ' '.join(instance.mentor_name.split()[1:]) if instance.mentor_name else user.last_name
            user.phone_number = instance.mentor_phone or user.phone_number
            user.role = role
            user.is_active = True
            user.is_verified = True

        user.username = username
        user.set_password(plain_pw)
        if instance.id_proof:
            user.id_proof = instance.id_proof
        user.save()

        mentor_profile, _ = MentorProfile.objects.get_or_create(user=user)
        mentor_profile.expertise = instance.mentor_expertise
        mentor_profile.save(update_fields=['expertise'])

        if instance.registration:
            reg = instance.registration
            reg.mentor = mentor_profile
            reg.save(update_fields=['mentor'])
            if reg.created_team:
                TeamMentor.objects.get_or_create(team=reg.created_team, mentor=mentor_profile)

        MentorInvitation.objects.filter(pk=instance.pk).update(created_user=user)
        instance.created_user = user
        if resend_email or existing_user is None or instance.created_user_id is None:
            _send_mentor_welcome_email(user, plain_pw, instance)
        logger.info(f"Mentor user '{username}' provisioned from invitation {instance.pk}")
        return user


@receiver(post_save, sender=MentorInvitation)
def handle_mentor_admin_approval(sender, instance, created, **kwargs):
    try:
        provision_mentor_account(instance)
    except Exception as exc:
        logger.error(f"Mentor approval error for invite {instance.pk}: {exc}", exc_info=True)

def _send_mentor_welcome_email(user, plain_pw, invite):
    try:
        subject = "Welcome to HackNexus — Your Mentor Account is Ready"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                    padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
            <h2 style="color:#059669;">Welcome, Mentor! 🎉</h2>
            <p>Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
            <p>Your mentor account for <strong>{invite.registration.hackathon.name if invite.registration else 'HackNexus'}</strong> has been approved.</p>
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:20px;margin:20px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;width:110px;">Username</td><td style="font-weight:800;font-family:monospace">{user.email}</td></tr>
                    <tr><td style="padding:6px 0;color:#6b7280;font-size:13px;">Password</td><td style="font-weight:900;color:#059669;font-family:monospace;font-size:15px;">{plain_pw}</td></tr>
                </table>
            </div>
            <a href="http://127.0.0.1:8000/mentor/login/"
               style="background:#059669;color:white;padding:12px 24px;border-radius:8px;
                      text-decoration:none;font-weight:700;display:inline-block;">
                Login to Mentor Portal →
            </a>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">Please change your password after first login.</p>
        </div>"""
        msg = EmailMultiAlternatives(subject=subject, body=f'Username: {user.email} | Password: {plain_pw}',
                                     from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email])
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.error(f"Mentor welcome email failed: {exc}")
