"""
FILE: accounts/signals.py  (CREATE this file — it does NOT exist yet)

Django post_save signal:
  When a SpocInvitation is saved with status='approved',
  this signal automatically:
    1. Creates a User account
    2. Generates a random password
    3. Creates SpocProfile + Institution + SpocInstitutionMap
    4. Sends a welcome email with login credentials

Register this in accounts/apps.py (instructions at the bottom).
"""

import secrets
import string
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver                                            
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.db.models.signals import pre_delete, pre_save

logger = logging.getLogger(__name__)

TRACKED_APP_LABELS = {'accounts', 'events', 'features'}


def _generate_password(length=12):
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _normalized_institution_name(name):
    return ' '.join((name or '').split())


def _sync_institution_details(invitation, institution):
    from .models import InstitutionExtended

    defaults = {
        'email': invitation.institution_email,
        'address': invitation.institution_address,
        'institution_head_name': invitation.institution_head_name,
        'institution_head_email': invitation.institution_head_email,
        'contact_no': invitation.institution_contact,
        'logo': invitation.institution_logo,
    }
    extended, _ = InstitutionExtended.objects.get_or_create(
        institution=institution,
        defaults=defaults,
    )

    changed_fields = []
    for field_name, value in defaults.items():
        if value and getattr(extended, field_name) != value:
            setattr(extended, field_name, value)
            changed_fields.append(field_name)
    if changed_fields:
        extended.save(update_fields=changed_fields)


def _resolve_institution_for_invitation(invitation, admin_profile=None):
    from .models import Institution

    institution_name = _normalized_institution_name(invitation.institution_name)
    if not institution_name:
        raise ValueError("Institution name is required before approving a SPOC.")

    invitation.institution_name = institution_name

    institution = Institution.objects.filter(name__iexact=institution_name).first()
    if institution is None:
        institution = Institution.objects.create(
            name=institution_name,
            location=invitation.institution_location or '',
            approved_by=admin_profile,
        )
    else:
        changed_fields = []
        if institution.name != institution_name:
            institution.name = institution_name
            changed_fields.append('name')
        if invitation.institution_location and institution.location != invitation.institution_location:
            institution.location = invitation.institution_location
            changed_fields.append('location')
        if admin_profile and institution.approved_by_id != admin_profile.id:
            institution.approved_by = admin_profile
            changed_fields.append('approved_by')
        if changed_fields:
            institution.save(update_fields=changed_fields)

    _sync_institution_details(invitation, institution)
    return institution


def _should_audit(sender):
    return (
        sender._meta.app_label in TRACKED_APP_LABELS and
        sender._meta.label_lower != 'accounts.auditlog'
    )


def _get_actor_snapshot(actor):
    if not actor:
        return {
            'actor': None,
            'actor_username': '',
            'actor_email': '',
        }

    return {
        'actor': actor,
        'actor_username': actor.get_username(),
        'actor_email': getattr(actor, 'email', '') or '',
    }


def _write_audit_log(sender, instance, action, changes, snapshot):
    if not _should_audit(sender):
        return

    try:
        from .audit import get_current_actor, get_request_meta
        from .models import AuditLog

        actor = get_current_actor()
        actor_data = _get_actor_snapshot(actor)
        request_data = get_request_meta()

        AuditLog.objects.create(
            **actor_data,
            action=action,
            app_label=sender._meta.app_label,
            model_name=sender._meta.model_name,
            object_pk=str(instance.pk or ''),
            object_repr=str(instance),
            changes=changes,
            snapshot=snapshot,
            **request_data,
        )
    except Exception:
        logger.exception(
            "Failed to write audit log for %s.%s pk=%s",
            sender._meta.app_label,
            sender._meta.model_name,
            instance.pk,
        )


@receiver(pre_save)
def capture_previous_values(sender, instance, raw=False, **kwargs):
    if raw or not _should_audit(sender) or not instance.pk:
        return

    try:
        from .audit import serialize_instance

        previous = sender.objects.filter(pk=instance.pk).first()
        instance._audit_previous_values = serialize_instance(previous) if previous else {}
    except Exception:
        logger.exception(
            "Failed to capture previous audit values for %s.%s pk=%s",
            sender._meta.app_label,
            sender._meta.model_name,
            instance.pk,
        )


@receiver(post_save)
def log_save(sender, instance, created, raw=False, **kwargs):
    if raw or not _should_audit(sender):
        return

    from .audit import diff_values, serialize_instance
    from .models import AuditLog

    after = serialize_instance(instance)

    if created:
        _write_audit_log(
            sender=sender,
            instance=instance,
            action=AuditLog.ACTION_CREATE,
            changes={'created': after},
            snapshot=after,
        )
        return

    before = getattr(instance, '_audit_previous_values', {})
    changes = diff_values(before, after)
    if not changes:
        return

    _write_audit_log(
        sender=sender,
        instance=instance,
        action=AuditLog.ACTION_UPDATE,
        changes=changes,
        snapshot=after,
    )


@receiver(pre_delete)
def log_delete(sender, instance, **kwargs):
    if not _should_audit(sender):
        return

    from .audit import serialize_instance
    from .models import AuditLog

    before = serialize_instance(instance)
    _write_audit_log(
        sender=sender,
        instance=instance,
        action=AuditLog.ACTION_DELETE,
        changes={'deleted': before},
        snapshot=before,
    )


@receiver(post_save, sender='accounts.SpocInvitation')
def handle_spoc_approval(sender, instance, created, **kwargs):
    """
    Triggered every time a SpocInvitation is saved.
    If status just became 'approved' and no user has been created yet,
    create the full user account.
    """
    # Only run when status is approved and user not yet created
    if instance.status != 'approved' or instance.created_user is not None:
        return

    from .models import User, Role, SpocProfile, SpocInstitutionMap

    try:
        with transaction.atomic():
            # 1. Prepare credentials
            plain_password = _generate_password()
            username = (instance.email or '').strip().lower()

            # 2. Get or create SPOC role
            spoc_role, _ = Role.objects.get_or_create(
                name='SPOC',
                defaults={'description': 'Single Point of Contact for an institution'}
            )

            # 3. Create User
            user = User.objects.create_user(
                username=username,
                email=instance.email,
                password=plain_password,
                first_name=instance.first_name,
                last_name=instance.last_name,
                phone_number=instance.phone_number,
                gender=instance.gender,
                date_of_birth=instance.date_of_birth,
                role=spoc_role,
                is_active=True,
                is_verified=True,
            )
            if instance.id_proof:
                user.id_proof = instance.id_proof
                user.save()

            admin_profile = None
            if instance.approved_by_id and hasattr(instance.approved_by, 'admin_profile'):
                admin_profile = instance.approved_by.admin_profile
            institution = _resolve_institution_for_invitation(instance, admin_profile)

            # 4. Create SpocProfile
            spoc_profile = SpocProfile.objects.create(
                user=user,
                institution_name=instance.institution_name,
                approved_by=admin_profile,
            )

            # 6. Map SPOC ↔ Institution
            SpocInstitutionMap.objects.get_or_create(
                spoc=spoc_profile, institution=institution
            )

            # 7. Link invitation to created user (prevents re-running)
            # Use update() to avoid re-triggering this signal
            sender.objects.filter(pk=instance.pk).update(created_user=user)

            # 8. Send welcome email
            _send_spoc_welcome_email(user, plain_password, instance)

            logger.info(
                f"SPOC user '{username}' created from invitation {instance.pk}"
            )

    except Exception as exc:
        logger.error(
            f"Error processing SPOC approval for invitation {instance.pk}: {exc}",
            exc_info=True
        )


def _send_spoc_welcome_email(user, plain_password, invitation):
    """Send branded welcome email to newly approved SPOC."""
    try:
        subject = "Welcome to HackNexus — Your SPOC Account is Ready"

        plain_body = (
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Your SPOC account has been approved.\n\n"
            f"Login credentials:\n"
            f"  Username (Email) : {user.email}\n"
            f"  Password : {plain_password}\n\n"
            f"Institution: {invitation.institution_name}\n\n"
            f"Please login at: http://127.0.0.1:8000/accounts/\n\n"
            f"Change your password after first login.\n\n"
            f"— HackNexus Team"
        )

        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                    padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
            <h2 style="color:#ea580c;margin-bottom:4px;">Welcome to HackNexus 🎉</h2>
            <p style="color:#6b7280;font-size:13px;margin-top:0;">
                Your SPOC account has been approved by the administrator.
            </p>
            <hr style="border:none;border-top:1px solid #f3f4f6;margin:20px 0;">
            <p style="color:#374151;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
            <p style="color:#374151;">You've been approved as the SPOC for
                <strong>{invitation.institution_name}</strong>.
                Here are your login credentials:
            </p>
            <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;
                        padding:20px;margin:20px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:8px 0;color:#6b7280;font-size:13px;width:110px;">Username</td>
                        <td style="padding:8px 0;font-weight:800;color:#111827;font-family:monospace;">{user.email}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#6b7280;font-size:13px;">Password</td>
                        <td style="padding:8px 0;font-weight:800;color:#ea580c;font-family:monospace;font-size:15px;">{plain_password}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#6b7280;font-size:13px;">Role</td>
                        <td style="padding:8px 0;font-weight:700;color:#374151;">SPOC</td>
                    </tr>
                </table>
            </div>
            <a href="http://127.0.0.1:8000/accounts/"
               style="background:#ea580c;color:white;padding:12px 24px;
                      border-radius:8px;text-decoration:none;font-weight:700;
                      display:inline-block;margin-top:8px;">
                Login to HackNexus →
            </a>
            <hr style="border:none;border-top:1px solid #f3f4f6;margin:24px 0;">
            <p style="color:#9ca3af;font-size:12px;">
                Please change your password after your first login.<br>
                Institution: {invitation.institution_name}
            </p>
        </div>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)

    except Exception as exc:
        logger.error(
            f"Welcome email failed for SPOC {user.email}: {exc}",
            exc_info=True
        )
        
@receiver(post_save, sender='features.TeamRegistration')
def handle_team_approval(sender, instance, created, **kwargs):
    """
    Fires every time a TeamRegistration is saved.
    Only acts when status == 'approved' and no Team has been created yet.
    """
    if instance.status != 'approved' or instance.created_team is not None:
        return

    from features.models import Team, TeamMember, TeamStatusLog
    from accounts.models import User

    try:
        with transaction.atomic():
            leader_details = instance.leader_details or {}

            # Carry leader profile fields forward where our data model supports them.
            leader = instance.team_leader
            leader_changed = []
            if leader_details.get('role_in_team'):
                role_in_team = leader_details.get('role_in_team')
            else:
                role_in_team = 'Leader'
            if leader_details.get('aadhaar_proof'):
                leader_aadhaar_proof = leader_details.get('aadhaar_proof')
            else:
                leader_aadhaar_proof = None
            if leader_details.get('college_id_proof'):
                leader_college_id_proof = leader_details.get('college_id_proof')
            else:
                leader_college_id_proof = None
            if leader_details.get('id_proof'):
                leader.id_proof = leader_details.get('id_proof')
                leader_changed.append('id_proof')
            if leader_details.get('cast'):
                # No dedicated model field yet; kept in leader_details JSON only.
                pass
            if leader_details.get('tshirt_size'):
                pass
            if leader_details.get('aadhaar_number'):
                pass
            if leader_details.get('bank_account'):
                pass
            if leader_details.get('ifsc'):
                pass
            if leader_details.get('bank_name'):
                pass
            if leader_details.get('gender'):
                leader.gender = leader_details.get('gender')
                leader_changed.append('gender')
            if leader_details.get('date_of_birth'):
                leader.date_of_birth = leader_details.get('date_of_birth')
                leader_changed.append('date_of_birth')
            if leader_details.get('phone_number'):
                leader.phone_number = leader_details.get('phone_number')
                leader_changed.append('phone_number')
            if leader_changed:
                leader.save(update_fields=list(dict.fromkeys(leader_changed)))

            # 1. Create the Team record
            team = Team.objects.create(
                team_name=instance.team_name,
                hackathon=instance.hackathon,
                institution=instance.institution,
                team_leader=instance.team_leader,
                problem_statement=instance.problem_statement,
                declared_member_count=instance.get_member_count(),
                leader_role_in_team=role_in_team,
                status='spoc_approved',  # enters the active flow
            )
            if leader_aadhaar_proof:
                team.leader_aadhaar_proof = leader_aadhaar_proof
            if leader_college_id_proof:
                team.leader_college_id_proof = leader_college_id_proof
            if leader_aadhaar_proof or leader_college_id_proof:
                team.save(update_fields=['leader_aadhaar_proof', 'leader_college_id_proof'])

            # 2. Create TeamMember records from members_data JSON
            for member_dict in (instance.members_data or []):
                user_id = member_dict.get('user_id')
                if user_id:
                    try:
                        member_user = User.objects.get(id=user_id)
                        member_changed = []
                        if member_dict.get('first_name'):
                            member_user.first_name = member_dict.get('first_name')
                            member_changed.append('first_name')
                        if member_dict.get('last_name'):
                            member_user.last_name = member_dict.get('last_name')
                            member_changed.append('last_name')
                        if member_dict.get('phone_number'):
                            member_user.phone_number = member_dict.get('phone_number')
                            member_changed.append('phone_number')
                        if member_dict.get('gender'):
                            member_user.gender = member_dict.get('gender')
                            member_changed.append('gender')
                        if member_dict.get('date_of_birth'):
                            member_user.date_of_birth = member_dict.get('date_of_birth')
                            member_changed.append('date_of_birth')
                        if member_dict.get('id_proof'):
                            member_user.id_proof = member_dict.get('id_proof')
                            member_changed.append('id_proof')
                        if member_changed:
                            member_user.save(update_fields=list(dict.fromkeys(member_changed)))

                        TeamMember.objects.get_or_create(
                            team=team,
                            user=member_user,
                            defaults={
                                'role_in_team': member_dict.get('role_in_team') or member_dict.get('role', 'Member'),
                                'aadhaar_proof': member_dict.get('aadhaar_proof') or None,
                                'college_id_proof': member_dict.get('college_id_proof') or None,
                            }
                        )
                    except User.DoesNotExist:
                        logger.warning(
                            f"TeamRegistration {instance.pk}: user_id {user_id} not found"
                        )

            # 3. Log the approval in TeamStatusLog
            TeamStatusLog.objects.create(
                team=team,
                old_status='pending',
                new_status='spoc_approved',
                changed_by=instance.reviewed_by,
                note=f"Team approved from registration #{instance.pk}",
            )

            # 4. Link the registration to the new team (prevents re-running)
            sender.objects.filter(pk=instance.pk).update(created_team=team)

            # 5. Send approval email to team leader
            _send_team_approval_email(instance, team)

            logger.info(
                f"Team '{team.team_name}' created from registration {instance.pk}"
            )

    except Exception as exc:
        logger.error(
            f"Error processing team approval for registration {instance.pk}: {exc}",
            exc_info=True
        )


def _send_team_approval_email(registration, team):
    """Send approval notification to the team leader."""
    leader = registration.team_leader
    try:
        subject = f"🎉 Your Team '{team.team_name}' Has Been Approved — HackNexus"

        plain = (
            f"Hello {leader.get_full_name() or leader.username},\n\n"
            f"Great news! Your team '{team.team_name}' has been approved for "
            f"'{team.hackathon.name}'.\n\n"
            f"You can now access your full team dashboard and begin working on your "
            f"problem statement.\n\n"
            f"Team Details:\n"
            f"  Team Name : {team.team_name}\n"
            f"  Hackathon : {team.hackathon.name}\n"
            f"  Members   : {registration.get_member_count()}\n\n"
            f"— HackNexus Team"
        )

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                    padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
            <h2 style="color:#059669;margin-bottom:4px;">Team Approved! 🎉</h2>
            <p style="color:#374151;">
                Hello <strong>{leader.get_full_name() or leader.username}</strong>,
            </p>
            <p style="color:#374151;">
                Your team <strong>"{team.team_name}"</strong> has been approved for
                <strong>{team.hackathon.name}</strong>.
            </p>
            <div style="background:#ecfdf5;border:1px solid #d1fae5;border-radius:10px;
                        padding:20px;margin:20px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-size:13px;width:120px;">Team Name</td>
                        <td style="font-weight:800;color:#111827;">{team.team_name}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-size:13px;">Hackathon</td>
                        <td style="font-weight:700;">{team.hackathon.name}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-size:13px;">Total Members</td>
                        <td style="font-weight:700;">{registration.get_member_count()}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#6b7280;font-size:13px;">Institution</td>
                        <td style="font-weight:700;">{team.institution.name if team.institution else '—'}</td>
                    </tr>
                </table>
            </div>
            <p style="color:#374151;">
                You can now log into HackNexus and access your team dashboard to:
                add/remove members, select your problem statement, and submit your work.
            </p>
            <a href="http://127.0.0.1:8000/accounts/"
               style="background:#059669;color:white;padding:12px 24px;border-radius:8px;
                      text-decoration:none;font-weight:700;display:inline-block;margin-top:8px;">
                Go to Dashboard →
            </a>
            <hr style="border:none;border-top:1px solid #f3f4f6;margin:24px 0;">
            <p style="color:#9ca3af;font-size:12px;">
                If you have questions, contact your SPOC or the event administrator.
            </p>
        </div>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[leader.email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)

    except Exception as exc:
        logger.error(
            f"Team approval email failed for leader {leader.email}: {exc}",
            exc_info=True
        )


def _send_team_rejection_email(registration, note=''):
    """Send rejection notification to the team leader."""
    leader = registration.team_leader
    try:
        subject = f"Team Registration Update — {registration.team_name}"
        plain = (
            f"Hello {leader.get_full_name() or leader.username},\n\n"
            f"Unfortunately, your team registration for '{registration.hackathon.name}' "
            f"could not be approved.\n\n"
            f"Reason: {note or 'Please contact the administrator for details.'}\n\n"
            f"You may re-register after addressing the issues mentioned.\n\n"
            f"— HackNexus Team"
        )
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[leader.email],
        )
        msg.send(fail_silently=True)
    except Exception as exc:
        logger.error(f"Team rejection email failed: {exc}", exc_info=True)
