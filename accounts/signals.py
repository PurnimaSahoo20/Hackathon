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
    """Send branded welcome email to newly approved SPOC and Institution Head."""
    try:
        event_name = invitation.hackathon.name if invitation.hackathon else "HackNexus"
        org_name = invitation.hackathon.organization_name if invitation.hackathon else "HackNexus Secretariat"
        institution_head_name = invitation.institution_head_name or "Head of Institution"
        institution_head_email = invitation.institution_head_email
        institution_name = invitation.institution_name or "Your Institution"
        spoc_name = user.get_full_name() or user.username
        spoc_email = user.email
        
        dashboard_url = "https://hackathon.okcl.org/accounts/"
        website = "https://hackathon.okcl.org/"
        support_email = "support@hacknexus.com"
        support_number = "+91 99999 99999"
        
        event_admin_name = invitation.approved_by.get_full_name() if invitation.approved_by else "Event Administrator"

        subject = f"Institution Registration Confirmed – Dashboard Access & Next Steps for {event_name}"

        # To: Institution Head Email, CC: SPOC Email
        to_list = [institution_head_email] if institution_head_email else [spoc_email]
        cc_list = [spoc_email] if institution_head_email and spoc_email != institution_head_email else []

        plain_body = f"""Dear Prof./Dr./Mr./Ms. {institution_head_name},

Greetings!

We are pleased to inform you that {institution_name} has been successfully registered to participate in {event_name}.

Thank you for your interest in fostering innovation, creativity, and problem-solving among your students. We sincerely appreciate your institution's participation in this prestigious event.

As nominated by your institution, {spoc_name} has been registered as the Institutional Single Point of Contact (SPOC) and will coordinate all event-related activities on behalf of your institution.

--------------------------------------------------
Dashboard Access Credentials
--------------------------------------------------
Institution: {institution_name}
Institution SPOC: {spoc_name}
Dashboard URL: {dashboard_url}
Username: {user.email}
Temporary Password: {plain_password}

For security reasons, the SPOC is requested to change the password upon first login.

--------------------------------------------------
Next Course of Action
--------------------------------------------------
The Institutional SPOC is requested to complete the following activities:

Phase 1 – Dashboard Setup
• Log in to the Institution Dashboard.
• Change the default password.
• Verify institution profile details.
• Update institutional logo (if applicable).
• Complete SPOC profile.

Phase 2 – Student Mobilization
• Publicize {event_name} among students.
• Encourage participation across all eligible departments.
• Organize awareness sessions, if required.
• Share the student registration link with all eligible students.

Phase 3 – Student Registration Monitoring
Through the dashboard, the SPOC can:
• Monitor student registrations.
• View department-wise participation.
• Track team formation.
• Review participation statistics.
• Receive event notifications.

Phase 4 – Event Coordination
The SPOC shall:
• Serve as the official communication link between the institution and the Event Secretariat.
• Disseminate important announcements and timelines.
• Coordinate internal mentoring and support for participating teams.
• Ensure timely submission of ideas/projects as per the event schedule.
• Facilitate participation during evaluation rounds and final presentations.

--------------------------------------------------
Roles & Responsibilities of the Institutional SPOC
--------------------------------------------------
The nominated SPOC shall be responsible for:
• Acting as the official coordinator for {event_name}.
• Managing the Institution Dashboard.
• Promoting the event within the institution.
• Assisting students during registration.
• Monitoring student participation and team formation.
• Communicating important dates and guidelines.
• Coordinating with faculty mentors and departmental heads.
• Ensuring timely completion of all event milestones.
• Responding to communications from the organizing committee.
• Supporting students throughout the Hackathon/Ideathon journey.

--------------------------------------------------
Dashboard Features
--------------------------------------------------
The Institution Dashboard provides access to:
• Institution Profile
• Student Registration Status
• Team Formation
• Faculty Mentor Assignment
• Event Calendar
• Notifications & Announcements
• Submission Status
• Evaluation Progress
• Certificates & Reports
• Participation Analytics

--------------------------------------------------
Important Dates
--------------------------------------------------
Please refer to the Event Calendar available in the dashboard for:
• Student Registration Deadline
• Team Formation Timeline
• Problem Statement Release
• Idea Submission Deadline
• Mentoring Sessions
• Evaluation Schedule
• Grand Finale
• Award Ceremony

--------------------------------------------------
For any technical or operational assistance, please contact:
Event Helpdesk
Email: {support_email}
Mobile: {support_number}
Website: {website}

--------------------------------------------------
We thank {institution_name} for joining {event_name} and look forward to your enthusiastic participation. We are confident that your institution will play a significant role in nurturing innovation and empowering students to develop impactful solutions to real-world challenges.

We wish your faculty members and students every success in the event.

With best regards,

{event_admin_name}
Event Administrator
{event_name}
{org_name}
"""

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333; margin: 0; padding: 20px; background-color: #f9f9f9;">
            <table cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #dddddd; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <!-- Header -->
                <tr>
                    <td style="background: linear-gradient(135deg, #ea580c, #d97706); padding: 30px; text-align: center; color: #ffffff;">
                        <h1 style="margin: 0; font-size: 24px; font-weight: bold;">{event_name}</h1>
                        <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">Institution Registration Confirmed</p>
                    </td>
                </tr>
                <!-- Content -->
                <tr>
                    <td style="padding: 30px;">
                        <p style="margin-top: 0;">Dear Prof./Dr./Mr./Ms. <strong>{institution_head_name}</strong>,</p>
                        <p>Greetings!</p>
                        <p>We are pleased to inform you that <strong>{institution_name}</strong> has been successfully registered to participate in <strong>{event_name}</strong>.</p>
                        <p>Thank you for your interest in fostering innovation, creativity, and problem-solving among your students. We sincerely appreciate your institution's participation in this prestigious event.</p>
                        <p>As nominated by your institution, <strong>{spoc_name}</strong> has been registered as the Institutional Single Point of Contact (SPOC) and will coordinate all event-related activities on behalf of your institution.</p>
                        
                        <!-- Credentials Box -->
                        <div style="background-color: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 20px; margin: 25px 0;">
                            <h3 style="margin-top: 0; color: #ea580c; border-bottom: 1px solid #ffedd5; padding-bottom: 8px;">Dashboard Access Credentials</h3>
                            <table cellpadding="4" cellspacing="0" width="100%" style="font-size: 14px;">
                                <tr>
                                    <td width="35%"><strong>Institution:</strong></td>
                                    <td>{institution_name}</td>
                                </tr>
                                <tr>
                                    <td><strong>Institution SPOC:</strong></td>
                                    <td>{spoc_name}</td>
                                </tr>
                                <tr>
                                    <td><strong>Dashboard URL:</strong></td>
                                    <td><a href="{dashboard_url}" style="color: #ea580c; text-decoration: underline;">{dashboard_url}</a></td>
                                </tr>
                                <tr>
                                    <td><strong>Username:</strong></td>
                                    <td><code style="background: #ffedd5; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{user.email}</code></td>
                                </tr>
                                <tr>
                                    <td><strong>Temporary Password:</strong></td>
                                    <td><code style="background: #ffedd5; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{plain_password}</code></td>
                                </tr>
                            </table>
                            <p style="margin-bottom: 0; font-size: 13px; color: #666666; font-style: italic; margin-top: 12px;">For security reasons, the SPOC is requested to change the password upon first login.</p>
                        </div>
                        
                        <!-- Next Steps -->
                        <h3 style="color: #ea580c; border-bottom: 2px solid #ea580c; padding-bottom: 5px; margin-top: 30px;">Next Course of Action</h3>
                        <p>The Institutional SPOC is requested to complete the following activities:</p>
                        
                        <h4 style="color: #111827; margin-bottom: 8px;">Phase 1 – Dashboard Setup</h4>
                        <ul style="margin-top: 0; padding-left: 20px;">
                            <li>Log in to the Institution Dashboard.</li>
                            <li>Change the default password.</li>
                            <li>Verify institution profile details.</li>
                            <li>Update institutional logo (if applicable).</li>
                            <li>Complete SPOC profile.</li>
                        </ul>
                        
                        <h4 style="color: #111827; margin-bottom: 8px;">Phase 2 – Student Mobilization</h4>
                        <ul style="margin-top: 0; padding-left: 20px;">
                            <li>Publicize {event_name} among students.</li>
                            <li>Encourage participation across all eligible departments.</li>
                            <li>Organize awareness sessions, if required.</li>
                            <li>Share the student registration link with all eligible students.</li>
                        </ul>
                        
                        <h4 style="color: #111827; margin-bottom: 8px;">Phase 3 – Student Registration Monitoring</h4>
                        <p style="margin-bottom: 5px;">Through the dashboard, the SPOC can:</p>
                        <ul style="margin-top: 0; padding-left: 20px;">
                            <li>Monitor student registrations.</li>
                            <li>View department-wise participation.</li>
                            <li>Track team formation.</li>
                            <li>Review participation statistics.</li>
                            <li>Receive event notifications.</li>
                        </ul>
                        
                        <h4 style="color: #111827; margin-bottom: 8px;">Phase 4 – Event Coordination</h4>
                        <p style="margin-bottom: 5px;">The SPOC shall:</p>
                        <ul style="margin-top: 0; padding-left: 20px;">
                            <li>Serve as the official communication link between the institution and the Event Secretariat.</li>
                            <li>Disseminate important announcements and timelines.</li>
                            <li>Coordinate internal mentoring and support for participating teams.</li>
                            <li>Ensure timely submission of ideas/projects as per the event schedule.</li>
                            <li>Facilitate participation during evaluation rounds and final presentations.</li>
                        </ul>
                        
                        <!-- Roles and Responsibilities -->
                        <h3 style="color: #ea580c; border-bottom: 2px solid #ea580c; padding-bottom: 5px; margin-top: 30px;">Roles & Responsibilities of the Institutional SPOC</h3>
                        <p>The nominated SPOC shall be responsible for:</p>
                        <ul style="padding-left: 20px;">
                            <li>Acting as the official coordinator for {event_name}.</li>
                            <li>Managing the Institution Dashboard.</li>
                            <li>Promoting the event within the institution.</li>
                            <li>Assisting students during registration.</li>
                            <li>Monitoring student participation and team formation.</li>
                            <li>Communicating important dates and guidelines.</li>
                            <li>Coordinating with faculty mentors and departmental heads.</li>
                            <li>Ensuring timely completion of all event milestones.</li>
                            <li>Responding to communications from the organizing committee.</li>
                            <li>Supporting students throughout the Hackathon/Ideathon journey.</li>
                        </ul>
                        
                        <!-- Dashboard Features -->
                        <h3 style="color: #ea580c; border-bottom: 2px solid #ea580c; padding-bottom: 5px; margin-top: 30px;">Dashboard Features</h3>
                        <p>The Institution Dashboard provides access to:</p>
                        <ul style="padding-left: 20px;">
                            <li>Institution Profile</li>
                            <li>Student Registration Status</li>
                            <li>Team Formation</li>
                            <li>Faculty Mentor Assignment</li>
                            <li>Event Calendar</li>
                            <li>Notifications & Announcements</li>
                            <li>Submission Status</li>
                            <li>Evaluation Progress</li>
                            <li>Certificates & Reports</li>
                            <li>Participation Analytics</li>
                        </ul>
                        
                        <!-- Important Dates -->
                        <h3 style="color: #ea580c; border-bottom: 2px solid #ea580c; padding-bottom: 5px; margin-top: 30px;">Important Dates</h3>
                        <p>Please refer to the Event Calendar available in the dashboard for:</p>
                        <ul style="padding-left: 20px;">
                            <li>Student Registration Deadline</li>
                            <li>Team Formation Timeline</li>
                            <li>Problem Statement Release</li>
                            <li>Idea Submission Deadline</li>
                            <li>Mentoring Sessions</li>
                            <li>Evaluation Schedule</li>
                            <li>Grand Finale</li>
                            <li>Award Ceremony</li>
                        </ul>
                        
                        <!-- Helpdesk Box -->
                        <table cellpadding="15" cellspacing="0" width="100%" style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; margin: 25px 0; font-size: 14px;">
                            <tr>
                                <td>
                                    <h4 style="margin: 0 0 10px 0; color: #166534;">Event Helpdesk</h4>
                                    <p style="margin: 0; line-height: 1.8;">
                                        📧 <strong>Email:</strong> <a href="mailto:{support_email}" style="color: #166534; text-decoration: underline;">{support_email}</a><br>
                                        📞 <strong>Mobile:</strong> {support_number}<br>
                                        🌐 <strong>Website:</strong> <a href="{website}" style="color: #166534; text-decoration: underline;">{website}</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                        
                        <p>We thank <strong>{institution_name}</strong> for joining <strong>{event_name}</strong> and look forward to your enthusiastic participation. We are confident that your institution will play a significant role in nurturing innovation and empowering students to develop impactful solutions to real-world challenges.</p>
                        <p>We wish your faculty members and students every success in the event.</p>
                        
                        <!-- Signature -->
                        <p style="margin-top: 35px; border-top: 1px solid #eeeeee; padding-top: 15px;">
                            With best regards,<br><br>
                            <strong>{event_admin_name}</strong><br>
                            Event Administrator<br>
                            {event_name}<br>
                            {org_name}
                        </p>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_list,
            cc=cc_list,
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
            <a href="https://hackathon.okcl.org/accounts/"
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
