"""
spoc/views.py

All views for the SPOC portal:
  - login / OTP (2FA via email)
  - dashboard
  - team registrations (pending, approved, rejected)
  - modification requests
  - results
  - messages
  - announcements / activity log
"""
import logging
import random
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.views.decorators.http import require_POST
from django.urls import reverse

from accounts.passwords import PORTAL_PASSWORD_HELP_TEXT, validate_portal_password

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
#  HELPERS
# ────────────────────────────────────────────────────────────

def _spoc_required(request):
    """Return True if logged-in user is a SPOC."""
    return (
        request.user.is_authenticated and
        hasattr(request.user, 'spoc_profile')
    )


def _get_spoc(request):
    """Return the SpocProfile for the logged-in user or None."""
    if hasattr(request.user, 'spoc_profile'):
        return request.user.spoc_profile
    return None


def _get_spoc_institution(spoc):
    from accounts.models import SpocInstitutionMap

    mapping = SpocInstitutionMap.objects.filter(spoc=spoc).select_related('institution').first()
    return mapping.institution if mapping else None


def _registration_deadline_passed(reg):
    close_date = getattr(getattr(reg, 'hackathon', None), 'registration_close', None)
    return bool(close_date and timezone.localdate() > close_date)


def _ready_for_spoc_review_filter():
    return (
        Q(mentor_invitations__status__in=['spoc_pending', 'spoc_approved', 'admin_approved', 'active']) |
        Q(hackathon__registration_close__lt=timezone.localdate())
    )


def _send_otp_email(user, otp_code):
    subject = 'HackNexus SPOC — Your Login Verification Code'
    plain = (
        f"Hello {user.get_full_name() or user.username},\n\n"
        f"Your 4-digit verification code is: {otp_code}\n\n"
        f"This code is valid for 10 minutes. Do not share it.\n\n"
        f"— HackNexus Team"
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;
                padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
        <h2 style="color:#ea580c;">HackNexus SPOC 2FA</h2>
        <p style="color:#374151;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
        <p style="color:#374151;">Use the code below to complete your SPOC login:</p>
        <div style="background:#fff7ed;border:2px dashed #ea580c;border-radius:8px;
                    padding:24px;text-align:center;margin:24px 0;">
            <span style="font-size:36px;font-weight:900;letter-spacing:12px;color:#ea580c;">{otp_code}</span>
        </div>
        <p style="color:#6b7280;font-size:13px;">Expires in <strong>10 minutes</strong>.</p>
        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
        <p style="color:#9ca3af;font-size:12px;">If you did not attempt login, ignore this email.</p>
    </div>
    """
    try:
        msg = EmailMultiAlternatives(
            subject=subject, body=plain,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.error(f"SPOC OTP email failed for {user.email}: {exc}")


# ────────────────────────────────────────────────────────────
#  AUTH
# ────────────────────────────────────────────────────────────

@never_cache
def spoc_login(request):
    next_url = request.GET.get('next', '')
    login_url = reverse('login')
    if next_url:
        return redirect(f'{login_url}?next={next_url}')
    return redirect('login')


@never_cache
def spoc_verify_otp(request):
    user_id = request.session.get('spoc_pending_2fa_user_id')
    if not user_id:
        return redirect('spoc_login')

    from accounts.models import User, OTPVerification
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('spoc_login')

    if request.method == 'POST':
        otp_code = request.POST.get('otp', '').strip()
        record = OTPVerification.objects.filter(
            user=user, code=otp_code, is_verified=False
        ).order_by('-created_at').first()

        if record and not record.is_expired():
            record.is_verified = True
            record.save()
            del request.session['spoc_pending_2fa_user_id']
            login(request, user)
            messages.success(request, 'Login successful!')
            return redirect('spoc_dashboard')
        else:
            messages.error(request, 'Invalid or expired OTP. Please try again.')

    return render(request, 'spoc/verify_otp.html', {'email': user.email})


@login_required(login_url='/spoc/login/')
def spoc_logout(request):
    logout(request)
    return redirect('landing_page')


# ────────────────────────────────────────────────────────────
#  DASHBOARD
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_dashboard(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from features.models import TeamRegistration
    from .models import SpocDashboardActivity

    institution = None
    institution = _get_spoc_institution(spoc)

    # Stats
    regs = TeamRegistration.objects.filter(institution=institution) if institution else TeamRegistration.objects.none()
    total_teams = regs.count()
    pending_teams = regs.filter(
        status='pending',
    ).filter(
        _ready_for_spoc_review_filter()
    ).distinct().count()
    approved_teams = regs.filter(status='approved').count()

    # Notifications
    from .models import SpocNotification
    notifs = SpocNotification.objects.filter(spoc=spoc, is_read=False)[:5]
    notif_count = SpocNotification.objects.filter(spoc=spoc, is_read=False).count()
    recent_activities = SpocDashboardActivity.objects.filter(spoc=spoc)[:8]
    account_steps = [
        'Invitation Received',
        'Registered & Login',
        'Admin Approved',
        'Managing Teams',
        'Letter Submitted',
        'Complete',
    ]

    context = {
        'spoc': spoc,
        'institution': institution,
        'total_teams': total_teams,
        'pending_teams': pending_teams,
        'approved_teams': approved_teams,
        'notif_count': notif_count,
        'notifications': notifs,
        'recent_activities': recent_activities,
        'account_steps': account_steps,
    }
    return render(request, 'spoc/dashboard.html', context)


# ────────────────────────────────────────────────────────────
#  TEAMS
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_teams(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from features.models import TeamRegistration

    institution = _get_spoc_institution(spoc)

    pending_regs = (
        TeamRegistration.objects.filter(
            institution=institution,
            status='pending',
        )
        .filter(_ready_for_spoc_review_filter())
        .select_related('team_leader', 'hackathon', 'problem_statement', 'institution')
        .distinct()
        .order_by('-registered_at')
    ) if institution else TeamRegistration.objects.none()

    approved_regs = (
        TeamRegistration.objects.filter(institution=institution, status='approved')
        .select_related('team_leader', 'hackathon', 'problem_statement')
        .order_by('-registered_at')
    ) if institution else TeamRegistration.objects.none()

    rejected_regs = (
        TeamRegistration.objects.filter(institution=institution, status='rejected')
        .select_related('team_leader', 'hackathon')
        .order_by('-registered_at')
    ) if institution else TeamRegistration.objects.none()

    context = {
        'spoc': spoc,
        'institution': institution,
        'pending_regs': pending_regs,
        'approved_regs': approved_regs,
        'rejected_regs': rejected_regs,
    }
    return render(request, 'spoc/teams.html', context)


@login_required(login_url='/spoc/login/')
@never_cache
def spoc_team_detail(request, reg_id):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from features.models import TeamRegistration
    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    reg = get_object_or_404(TeamRegistration, id=reg_id, institution=institution)
    mentor_invite = reg.mentor_invitations.exclude(
        status__in=['invited']
    ).order_by('-accepted_at', '-invited_at').first()
    context = {
        'spoc': spoc,
        'reg': reg,
        'members': reg.members_data or [],
        'leader_details': reg.leader_details or {},
        'mentor_invite': mentor_invite,
        'registration_deadline_passed': _registration_deadline_passed(reg),
        'can_approve_team': not reg.hackathon.registration_close or _registration_deadline_passed(reg),
    }
    return render(request, 'spoc/team_detail.html', context)


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_approve_team(request, reg_id):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from features.models import TeamRegistration
    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    reg = get_object_or_404(TeamRegistration, id=reg_id, institution=institution)
    if reg.status != 'pending':
        messages.warning(request, f"Registration is already '{reg.status}'.")
        return redirect('spoc_teams')

    if reg.hackathon.registration_close and not _registration_deadline_passed(reg):
        messages.error(request, 'This team can be approved only after the registration deadline has passed and the final data is locked.')
        return redirect('spoc_team_detail', reg_id=reg_id)

    auth_letter = request.FILES.get('auth_letter')
    if not auth_letter:
        messages.error(request, 'Please upload the authorization letter to approve.')
        return redirect('spoc_team_detail', reg_id=reg_id)

    # Save auth letter
    from .models import SpocTeamApproval
    approval, _ = SpocTeamApproval.objects.get_or_create(spoc=spoc, registration=reg)
    approval.auth_letter = auth_letter
    approval.status = 'approved'
    approval.decided_at = timezone.now()
    approval.save()

    # Update registration status
    reg.status = 'approved'
    reg.reviewed_by = request.user
    reg.reviewed_at = timezone.now()
    reg.save()

    # Activity notification
    from .models import SpocDashboardActivity
    SpocDashboardActivity.objects.create(
        spoc=spoc,
        icon='✅', color='#059669',
        text=f"<strong>{reg.team_name}</strong> approved — Team Dashboard activated"
    )

    # Email team leader
    _send_team_status_email(reg, 'approved')
    messages.success(request, f"Team '{reg.team_name}' approved and letter uploaded.")
    return redirect('spoc_teams')


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_reject_team(request, reg_id):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from features.models import TeamRegistration
    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    reg = get_object_or_404(TeamRegistration, id=reg_id, institution=institution)
    reason = request.POST.get('rejection_reason', '').strip()
    if not reason:
        messages.error(request, 'Rejection reason is required.')
        return redirect('spoc_team_detail', reg_id=reg_id)

    reg.status = 'rejected'
    reg.rejection_note = reason
    reg.reviewed_by = request.user
    reg.reviewed_at = timezone.now()
    reg.save()

    from .models import SpocDashboardActivity
    SpocDashboardActivity.objects.create(
        spoc=spoc,
        icon='❌', color='#dc2626',
        text=f"<strong>{reg.team_name}</strong> rejected — {reason[:60]}"
    )

    _send_team_status_email(reg, 'rejected', reason)
    messages.success(request, f"Team '{reg.team_name}' rejected.")
    return redirect('spoc_teams')


def _send_team_status_email(reg, status, reason=''):
    leader = reg.team_leader
    try:
        if status == 'approved':
            subject = f"🎉 Your Team '{reg.team_name}' is Approved — HackNexus"
            html = f"""
            <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                        padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
                <h2 style="color:#059669;">Team Approved! 🎉</h2>
                <p>Hello <strong>{leader.get_full_name() or leader.username}</strong>,</p>
                <p>Your team <strong>"{reg.team_name}"</strong> has been approved by the SPOC for
                   <strong>{reg.hackathon.name}</strong>.</p>
                <p>Your Team Dashboard is now fully active. You can log in and start working!</p>
                <a href="http://127.0.0.1:8000/team/login/"
                   style="background:#059669;color:white;padding:12px 24px;border-radius:8px;
                          text-decoration:none;font-weight:700;display:inline-block;margin-top:12px;">
                    Go to Team Dashboard →
                </a>
            </div>"""
        else:
            subject = f"Team Registration Update — {reg.team_name}"
            html = f"""
            <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                        padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
                <h2 style="color:#dc2626;">Registration Not Approved</h2>
                <p>Hello <strong>{leader.get_full_name() or leader.username}</strong>,</p>
                <p>Your team <strong>"{reg.team_name}"</strong> was not approved.</p>
                <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin:16px 0;">
                    <strong>Reason:</strong> {reason or 'Please contact your SPOC for details.'}
                </div>
                <p>You may re-register after addressing the issues mentioned above.</p>
            </div>"""
        msg = EmailMultiAlternatives(
            subject=subject, body='See HTML version.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[leader.email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    except Exception as exc:
        logger.error(f"Team status email failed: {exc}")


# ────────────────────────────────────────────────────────────
#  MODIFICATIONS
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_modifications(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from .models import SpocModificationDecision
    pending = SpocModificationDecision.objects.filter(spoc=spoc, status='pending')
    resolved = SpocModificationDecision.objects.filter(spoc=spoc).exclude(status='pending')[:10]
    context = {'spoc': spoc, 'pending': pending, 'resolved': resolved}
    return render(request, 'spoc/modifications.html', context)


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_approve_modification(request, mod_id):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from .models import SpocModificationDecision
    mod = get_object_or_404(SpocModificationDecision, id=mod_id)
    auth_letter = request.FILES.get('auth_letter')

    mod.status = 'approved'
    mod.decided_at = timezone.now()
    if auth_letter:
        mod.auth_letter = auth_letter
    mod.save()

    messages.success(request, f"Modification for '{mod.team_name}' approved.")
    return redirect('spoc_modifications')


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_reject_modification(request, mod_id):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from .models import SpocModificationDecision
    mod = get_object_or_404(SpocModificationDecision, id=mod_id)
    reason = request.POST.get('rejection_reason', '').strip()
    mod.status = 'rejected'
    mod.rejection_reason = reason
    mod.decided_at = timezone.now()
    mod.save()
    messages.success(request, f"Modification for '{mod.team_name}' rejected.")
    return redirect('spoc_modifications')


# ────────────────────────────────────────────────────────────
#  RESULTS
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_results(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from features.models import TeamRegistration

    institution = _get_spoc_institution(spoc)

    approved_regs = (
        TeamRegistration.objects.filter(institution=institution, status='approved')
        .select_related('team_leader', 'hackathon', 'problem_statement')
    ) if institution else TeamRegistration.objects.none()

    context = {'spoc': spoc, 'institution': institution, 'approved_regs': approved_regs}
    return render(request, 'spoc/results.html', context)


# ────────────────────────────────────────────────────────────
#  MESSAGES
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_messages(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from .models import SpocMessage
    from accounts.models import User

    # Get all unique conversations
    sent = SpocMessage.objects.filter(sender=request.user).values_list('recipient_id', flat=True)
    received = SpocMessage.objects.filter(recipient=request.user).values_list('sender_id', flat=True)
    conv_user_ids = set(list(sent) + list(received))
    conv_users = User.objects.filter(id__in=conv_user_ids)

    unread_count = SpocMessage.objects.filter(recipient=request.user, is_read=False).count()

    context = {
        'spoc': spoc,
        'conv_users': conv_users,
        'unread_count': unread_count,
    }
    return render(request, 'spoc/messages.html', context)


@login_required(login_url='/spoc/login/')
def spoc_conversation(request, user_id):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from .models import SpocMessage
    from accounts.models import User

    other_user = get_object_or_404(User, id=user_id)
    thread = SpocMessage.objects.filter(
        sender__in=[request.user, other_user],
        recipient__in=[request.user, other_user],
    ).order_by('sent_at')

    # Mark received as read
    SpocMessage.objects.filter(sender=other_user, recipient=request.user, is_read=False).update(is_read=True)

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            SpocMessage.objects.create(sender=request.user, recipient=other_user, body=body)
        return redirect('spoc_conversation', user_id=user_id)

    context = {'spoc': _get_spoc(request), 'other_user': other_user, 'thread': thread}
    return render(request, 'spoc/conversation.html', context)


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_send_message(request):
    if not _spoc_required(request):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    from .models import SpocMessage
    from accounts.models import User

    recipient_id = request.POST.get('recipient_id')
    body = request.POST.get('body', '').strip()
    if not recipient_id or not body:
        return JsonResponse({'error': 'Missing fields'}, status=400)

    try:
        recipient = User.objects.get(id=recipient_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    msg = SpocMessage.objects.create(sender=request.user, recipient=recipient, body=body)
    return JsonResponse({'id': msg.id, 'sent_at': msg.sent_at.isoformat()})


# ────────────────────────────────────────────────────────────
#  ANNOUNCEMENTS & ACTIVITY
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_announcements(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from events.models import Hackathon
    # Fetch hackathons visible to this SPOC
    hackathons = Hackathon.objects.filter(status='Live').order_by('-created_at')
    context = {'spoc': spoc, 'hackathons': hackathons}
    return render(request, 'spoc/announcements.html', context)


@login_required(login_url='/spoc/login/')
@never_cache
def spoc_activity_log(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from .models import SpocDashboardActivity
    activities = SpocDashboardActivity.objects.filter(spoc=spoc)[:50]
    context = {'spoc': spoc, 'activities': activities}
    return render(request, 'spoc/activity_log.html', context)


# ────────────────────────────────────────────────────────────
#  PROFILE
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_profile(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from accounts.models import SpocInstitutionMap
    institution_map = SpocInstitutionMap.objects.filter(spoc=spoc).select_related('institution').first()

    if request.method == 'POST':
        user = request.user
        form_type = request.POST.get('form_type', 'profile')

        if form_type == 'password':
            current_password = request.POST.get('current_password', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()

            if not current_password or not new_password or not confirm_password:
                messages.error(request, 'All password fields are required.')
            elif not user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New password and confirm password do not match.')
            else:
                try:
                    validate_portal_password(new_password, user)
                    user.set_password(new_password)
                    user.save(update_fields=['password'])
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Password changed successfully.')
                except Exception as exc:
                    for error in (getattr(exc, 'messages', None) or [str(exc)]):
                        messages.error(request, error)
        else:
            user.first_name = request.POST.get('first_name', user.first_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            user.phone_number = request.POST.get('phone_number', user.phone_number)
            if request.FILES.get('profile_image'):
                user.profile_image = request.FILES['profile_image']
            user.save()
            messages.success(request, 'Profile updated.')
        return redirect('spoc_profile')

    context = {
        'spoc': spoc,
        'institution_map': institution_map,
        'password_help_text': PORTAL_PASSWORD_HELP_TEXT,
    }
    return render(request, 'spoc/profile.html', context)


# ────────────────────────────────────────────────────────────
#  NOTIFICATIONS (AJAX)
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
def spoc_mark_notifications_read(request):
    if not _spoc_required(request):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    from .models import SpocNotification
    SpocNotification.objects.filter(spoc=_get_spoc(request), is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})


# ────────────────────────────────────────────────────────────
#  MENTOR INVITATION MANAGEMENT (SPOC verifies mentor)
# ────────────────────────────────────────────────────────────

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_mentor_invitations(request):
    if not _spoc_required(request):
        return redirect('spoc_login')
    spoc = _get_spoc(request)
    from mentor.mentor.models import MentorInvitation
    from accounts.models import SpocInstitutionMap
    inst_map = SpocInstitutionMap.objects.filter(spoc=spoc).first()

    pending = []
    resolved = []
    if inst_map:
        all_invites = MentorInvitation.objects.filter(
            registration__institution=inst_map.institution
        ).select_related('team_leader', 'registration', 'hackathon').order_by('-invited_at')
        pending  = [i for i in all_invites if i.status in ('accepted', 'spoc_pending')]
        resolved = [i for i in all_invites if i.status not in ('invited', 'accepted', 'spoc_pending')]

    context = {'spoc': spoc, 'pending': pending, 'resolved': resolved}
    return render(request, 'spoc/mentor_invitations.html', context)


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_approve_mentor(request, invite_id):
    if not _spoc_required(request):
        return redirect('spoc_login')
    from mentor.mentor.models import MentorInvitation
    institution = _get_spoc_institution(_get_spoc(request))
    invite = get_object_or_404(MentorInvitation, id=invite_id, registration__institution=institution)
    invite.status = 'spoc_approved'
    invite.spoc_decided_at = timezone.now()
    invite.spoc_note = request.POST.get('note', '')
    invite.save()
    # Notify admin via email
    _notify_admin_mentor_spoc_approved(invite, request)
    messages.success(request, f'Mentor {invite.mentor_name} approved by SPOC. Admin notified.')
    return redirect('spoc_mentor_invitations')


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_reject_mentor(request, invite_id):
    if not _spoc_required(request):
        return redirect('spoc_login')
    from mentor.mentor.models import MentorInvitation
    institution = _get_spoc_institution(_get_spoc(request))
    invite = get_object_or_404(MentorInvitation, id=invite_id, registration__institution=institution)
    invite.status = 'spoc_rejected'
    invite.spoc_decided_at = timezone.now()
    invite.spoc_note = request.POST.get('rejection_reason', '')
    invite.save()
    # Notify team lead
    _notify_team_mentor_rejected(invite)
    messages.success(request, f'Mentor {invite.mentor_name} rejected.')
    return redirect('spoc_mentor_invitations')


def _notify_admin_mentor_spoc_approved(invite, request):
    try:
        from accounts.models import User
        admins = User.objects.filter(is_superuser=True)
        for admin in admins:
            subject = f'Mentor Verification — SPOC Approved: {invite.mentor_name}'
            html = f"""
            <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px;
                        background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
                <h2 style="color:#7c3aed;">Mentor Awaiting Admin Approval</h2>
                <p>Hello <strong>{admin.get_full_name() or admin.username}</strong>,</p>
                <p>SPOC has verified <strong>{invite.mentor_name}</strong> for team
                   <strong>{invite.registration.team_name if invite.registration else '—'}</strong>.</p>
                <p>Please log in to the Admin panel to approve or reject this mentor.</p>
                <a href="http://127.0.0.1:8000/accounts/dashboard/"
                   style="background:#7c3aed;color:white;padding:12px 24px;border-radius:8px;
                          text-decoration:none;font-weight:700;display:inline-block;margin-top:12px;">
                    Open Admin Panel →
                </a>
            </div>"""
            msg = EmailMultiAlternatives(
                subject=subject, body=f'Mentor {invite.mentor_name} needs admin approval.',
                from_email=settings.DEFAULT_FROM_EMAIL, to=[admin.email])
            msg.attach_alternative(html, "text/html")
            msg.send(fail_silently=True)
    except Exception as exc:
        logger.error(f"Notify admin mentor approved: {exc}")


def _notify_team_mentor_rejected(invite):
    try:
        subject = f'Mentor Verification Update — {invite.mentor_name}'
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px;
                    background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
            <h2 style="color:#dc2626;">Mentor Not Verified</h2>
            <p>Hello <strong>{invite.team_leader.get_full_name() or invite.team_leader.username}</strong>,</p>
            <p>The SPOC could not verify <strong>{invite.mentor_name}</strong> as your team mentor.</p>
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:14px;margin:16px 0;">
                <strong>Reason:</strong> {invite.spoc_note or 'Please contact your SPOC for details.'}
            </div>
            <p>Please invite a different mentor from your Team Dashboard.</p>
        </div>"""
        msg = EmailMultiAlternatives(
            subject=subject, body='Mentor rejected by SPOC.',
            from_email=settings.DEFAULT_FROM_EMAIL, to=[invite.team_leader.email])
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    except Exception as exc:
        logger.error(f"Notify team mentor rejected: {exc}")
