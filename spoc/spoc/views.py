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
    from features.models import TeamRegistration, Documentation
    from events.models import Hackathon

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
    account_steps = [
        'Invitation Received',
        'Registered & Login',
        'Admin Approved',
        'Managing Teams',
        'Letter Submitted',
        'Complete',
    ]

    # Live Hackathon & News & Rounds
    live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    news_items = []
    if live_hackathon:
        news_prefixes = (
            ('[News]', 'news'),
            ('[Announcement]', 'announcement'),
        )
        documentation_links = Documentation.objects.filter(
            hackathon=live_hackathon,
            is_published=True,
        ).order_by('-created_at')
        for item in documentation_links:
            landing_sections = []
            if item.landing_sections:
                if isinstance(item.landing_sections, str):
                    landing_sections = [item.landing_sections]
                else:
                    landing_sections = list(item.landing_sections)
            
            raw_title = (item.title or '').strip()
            is_match = 'latest-news' in landing_sections or any(raw_title.startswith(prefix) for prefix in ('[News]', '[Announcement]'))
            if not is_match:
                continue

            news_type = None
            title = raw_title
            for prefix, mapped_type in news_prefixes:
                if raw_title.startswith(prefix):
                    news_type = mapped_type
                    title = raw_title[len(prefix):].strip(" |:-")
                    break
            if not news_type:
                news_type = 'news'
            
            summary = (item.description or '').strip()
            news_items.append({
                'item': item,
                'title': title or raw_title or item.title,
                'summary': summary,
                'link': item.external_url or (item.file.url if item.file else '#'),
                'type': news_type,
                'type_label': news_type.title(),
                'search_text': ' '.join([
                    raw_title,
                    summary,
                    news_type,
                    item.created_at.strftime('%d %b %Y %I:%M %p') if item.created_at else '',
                ]).lower(),
            })

    rounds = live_hackathon.get_rounds() if live_hackathon else []

    context = {
        'spoc': spoc,
        'institution': institution,
        'total_teams': total_teams,
        'pending_teams': pending_teams,
        'approved_teams': approved_teams,
        'notif_count': notif_count,
        'notifications': notifs,
        'account_steps': account_steps,
        'live_hackathon': live_hackathon,
        'news_items': news_items,
        'rounds': rounds,
        'active_nav': 'dashboard',
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
def spoc_team_detail(request, token):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from features.models import TeamRegistration
    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    reg = get_object_or_404(TeamRegistration, registration_token=token, institution=institution)
    mentor_invite = reg.mentor_invitations.exclude(
        status__in=['invited']
    ).order_by('-accepted_at', '-invited_at').first()
    # Fetch existing approval record if any
    from .models import SpocTeamApproval
    approval = SpocTeamApproval.objects.filter(spoc=spoc, registration=reg).first()

    context = {
        'spoc': spoc,
        'reg': reg,
        'members': reg.members_data or [],
        'leader_details': reg.leader_details or {},
        'mentor_invite': mentor_invite,
        'registration_deadline_passed': _registration_deadline_passed(reg),
        'can_approve_team': True,  # SPOC can approve at any time
        'approval': approval,
    }
    return render(request, 'spoc/team_detail.html', context)


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_approve_team(request, token):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from features.models import TeamRegistration
    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    reg = get_object_or_404(TeamRegistration, registration_token=token, institution=institution)
    if reg.status != 'pending':
        messages.warning(request, f"Registration is already '{reg.status}'.")
        return redirect('spoc_teams')

    auth_letter = request.FILES.get('auth_letter')
    if not auth_letter:
        messages.error(request, 'Please upload the authorization letter to approve.')
        return redirect('spoc_team_detail', token=token)

    # Rename file to maintain slug
    import os
    from django.utils.text import slugify
    ext = os.path.splitext(auth_letter.name)[1].lower()
    auth_letter.name = f"approval_letter_{slugify(reg.team_name)}{ext}"

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

    # Email team leader is handled by the post_save signal in accounts/signals.py
    messages.success(request, f"Team '{reg.team_name}' approved and letter uploaded.")
    return redirect('spoc_teams')


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_reject_team(request, token):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from features.models import TeamRegistration
    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    reg = get_object_or_404(TeamRegistration, registration_token=token, institution=institution)
    reason = request.POST.get('rejection_reason', '').strip()
    if not reason:
        messages.error(request, 'Rejection reason is required.')
        return redirect('spoc_team_detail', token=token)

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
        # Collect all member emails to send the rejection notification
        to_emails = [leader.email]
        if status == 'rejected':
            for m in (reg.members_data or []):
                if m.get('email'):
                    to_emails.append(m['email'])

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
                <a href="https://hackathon.okcl.org/team/login/"
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
                <p>You may review and update details or resubmit via your dashboard.</p>
            </div>"""
        msg = EmailMultiAlternatives(
            subject=subject, body='See HTML version.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_emails,
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

@login_required(login_url='/spoc/login/')
@never_cache
def spoc_download_approval_template(request, token):
    """Generate and serve an HTML-based approval letter template as a downloadable file."""
    if not _spoc_required(request):
        return redirect('spoc_login')

    from features.models import TeamRegistration
    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    reg = get_object_or_404(TeamRegistration, registration_token=token, institution=institution)

    leader = reg.team_leader
    members = reg.members_data or []
    event_name = reg.hackathon.name if reg.hackathon else "HackNexus"
    institution_name = institution.name if institution else "Institution"
    spoc_name = request.user.get_full_name() or request.user.username

    members_rows = ""
    for i, m in enumerate(members, 2):
        members_rows += f"""
        <tr>
            <td style="border:1px solid #999;padding:8px;text-align:center;">{i}</td>
            <td style="border:1px solid #999;padding:8px;">{m.get('name', m.get('email', '-'))}</td>
            <td style="border:1px solid #999;padding:8px;">{m.get('email', '-')}</td>
            <td style="border:1px solid #999;padding:8px;">{m.get('phone_number', '-')}</td>
            <td style="border:1px solid #999;padding:8px;">{m.get('role_in_team', m.get('role', 'Member'))}</td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Approval Letter — {reg.team_name}</title>
    <style>
        @page {{ margin: 2cm; }}
        body {{ font-family: 'Times New Roman', serif; font-size: 14px; line-height: 1.7; color: #111; margin: 40px; }}
        .header {{ text-align: center; margin-bottom: 30px; border-bottom: 3px double #333; padding-bottom: 20px; }}
        .header h1 {{ font-size: 22px; margin: 0 0 5px 0; text-transform: uppercase; letter-spacing: 2px; }}
        .header h2 {{ font-size: 16px; margin: 0; font-weight: normal; color: #555; }}
        .ref-line {{ display: flex; justify-content: space-between; margin: 20px 0; font-size: 13px; color: #666; }}
        .subject {{ text-align: center; font-weight: bold; text-decoration: underline; margin: 25px 0; font-size: 15px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th {{ border: 1px solid #999; padding: 8px; background: #f0f0f0; text-align: left; font-size: 13px; }}
        td {{ font-size: 13px; }}
        .signature-block {{ margin-top: 60px; display: flex; justify-content: space-between; }}
        .sig-box {{ text-align: center; min-width: 200px; }}
        .sig-line {{ border-top: 1px solid #333; margin-top: 60px; padding-top: 5px; }}
        .stamp-area {{ border: 2px dashed #999; padding: 30px; text-align: center; color: #999; margin-top: 20px; min-height: 80px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{institution_name}</h1>
        <h2>Authorization Letter for Hackathon Participation</h2>
    </div>

    <div class="ref-line">
        <span>Ref No: _______________</span>
        <span>Date: _______________</span>
    </div>

    <p><strong>To,</strong><br>
    The Organizing Committee,<br>
    <strong>{event_name}</strong></p>

    <p class="subject">Subject: Authorization Letter for Team Participation in {event_name}</p>

    <p>Dear Sir/Madam,</p>

    <p>This is to certify that the following team from <strong>{institution_name}</strong> is hereby authorized to participate in <strong>{event_name}</strong>. The details of the team are as follows:</p>

    <table>
        <tr>
            <th style="width: 180px;">Team Name</th>
            <td style="border:1px solid #999;padding:8px;"><strong>{reg.team_name}</strong></td>
        </tr>
        <tr>
            <th>Team Leader</th>
            <td style="border:1px solid #999;padding:8px;">{leader.get_full_name() or leader.username}</td>
        </tr>
        <tr>
            <th>Team Leader Email</th>
            <td style="border:1px solid #999;padding:8px;">{leader.email}</td>
        </tr>
        <tr>
            <th>Team Leader Phone</th>
            <td style="border:1px solid #999;padding:8px;">{leader.phone_number or '-'}</td>
        </tr>
        <tr>
            <th>SPOC Name</th>
            <td style="border:1px solid #999;padding:8px;">{spoc_name}</td>
        </tr>
        <tr>
            <th>Problem Statement</th>
            <td style="border:1px solid #999;padding:8px;">{reg.problem_statement.title if reg.problem_statement else 'Not selected'}</td>
        </tr>
    </table>

    <h3 style="margin-top: 25px;">Team Members</h3>
    <table>
        <thead>
            <tr>
                <th style="width:50px;text-align:center;">S.No</th>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Role</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="border:1px solid #999;padding:8px;text-align:center;">1</td>
                <td style="border:1px solid #999;padding:8px;">{leader.get_full_name() or leader.username}</td>
                <td style="border:1px solid #999;padding:8px;">{leader.email}</td>
                <td style="border:1px solid #999;padding:8px;">{leader.phone_number or '-'}</td>
                <td style="border:1px solid #999;padding:8px;">Team Leader</td>
            </tr>
            {members_rows}
        </tbody>
    </table>

    <p style="margin-top: 25px;">I hereby confirm that the above-mentioned students are bonafide students of <strong>{institution_name}</strong> and are authorized to represent our institution in this event. All the details provided are true and correct to the best of our knowledge.</p>

    <p>We request you to kindly process their registration accordingly.</p>

    <div class="signature-block">
        <div class="sig-box">
            <div class="sig-line">SPOC Signature</div>
            <div style="margin-top:5px;font-size:12px;color:#666">{spoc_name}</div>
        </div>
        <div class="sig-box">
            <div class="sig-line">HOD / Principal Signature</div>
            <div style="margin-top:5px;font-size:12px;color:#666">Name & Designation</div>
        </div>
    </div>

    <div class="stamp-area">
        <p style="margin:0;font-size:13px;">Official Institutional Stamp / Seal</p>
    </div>
</body>
</html>"""

    from django.http import HttpResponse
    response = HttpResponse(html_content, content_type='text/html')
    from django.utils.text import slugify
    response['Content-Disposition'] = f'attachment; filename="approval_letter_{slugify(reg.team_name)}.html"'
    return response


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_submit_final_letter(request, token):
    """SPOC submits a final approval letter (after team data changes)."""
    if not _spoc_required(request):
        return redirect('spoc_login')

    from features.models import TeamRegistration
    from .models import SpocTeamApproval
    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    reg = get_object_or_404(TeamRegistration, registration_token=token, institution=institution)

    if reg.status != 'approved':
        messages.error(request, 'Final letter can only be submitted for approved teams.')
        return redirect('spoc_team_detail', token=token)

    final_letter = request.FILES.get('final_auth_letter')
    if not final_letter:
        messages.error(request, 'Please upload the final authorization letter.')
        return redirect('spoc_team_detail', token=token)

    # Rename file to maintain slug
    import os
    from django.utils.text import slugify
    ext = os.path.splitext(final_letter.name)[1].lower()
    final_letter.name = f"final_approval_letter_{slugify(reg.team_name)}{ext}"

    approval, _ = SpocTeamApproval.objects.get_or_create(spoc=spoc, registration=reg)
    approval.final_auth_letter = final_letter
    approval.final_submitted_at = timezone.now()
    approval.save()

    # Activity notification
    from .models import SpocDashboardActivity
    SpocDashboardActivity.objects.create(
        spoc=spoc,
        icon='📄', color='#2563eb',
        text=f"Final approval letter submitted for <strong>{reg.team_name}</strong>"
    )

    messages.success(request, f"Final approval letter uploaded for '{reg.team_name}'.")
    return redirect('spoc_team_detail', token=token)


def spoc_modifications(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    from .models import SpocModificationDecision
    from features.models import TeamRegistration

    pending = SpocModificationDecision.objects.filter(spoc=spoc, status='pending')
    submitted = SpocModificationDecision.objects.filter(spoc=spoc, status='submitted')
    resolved = SpocModificationDecision.objects.filter(spoc=spoc, status__in=['resolved', 'rejected'])[:10]

    for q in [pending, submitted, resolved]:
        for mod in q:
            mod.registration = TeamRegistration.objects.filter(team_name=mod.team_name, institution=institution).first()

    context = {
        'spoc': spoc,
        'pending': pending,
        'submitted': submitted,
        'resolved': resolved,
    }
    return render(request, 'spoc/modifications.html', context)


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_approve_modification(request, mod_id):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from .models import SpocModificationDecision, SpocDashboardActivity
    from features.models import TeamRegistration
    from team.team.models import TeamNotification

    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    mod = get_object_or_404(SpocModificationDecision, id=mod_id, spoc=spoc)
    reg = TeamRegistration.objects.filter(team_name=mod.team_name, institution=institution).first()

    old_status = mod.status
    auth_letter = request.FILES.get('auth_letter')

    if old_status == 'submitted':
        mod.status = 'resolved'
        mod.decided_at = timezone.now()
        mod.save()

        SpocDashboardActivity.objects.create(
            spoc=spoc,
            icon='✅', color='#059669',
            text=f"Approved final modifications for <strong>{mod.team_name}</strong>"
        )

        if reg:
            TeamNotification.objects.create(
                team_leader=reg.team_leader,
                registration=reg,
                notif_type='system',
                title='Modifications Approved by SPOC',
                body='Your final team modifications have been approved by the SPOC and details are now locked.',
            )

        messages.success(request, f"Final modifications for '{mod.team_name}' approved successfully.")
    else:
        mod.status = 'approved'
        mod.decided_at = timezone.now()
        if auth_letter:
            # Rename file to maintain slug
            import os
            from django.utils.text import slugify
            ext = os.path.splitext(auth_letter.name)[1].lower()
            auth_letter.name = f"modification_approval_letter_{slugify(mod.team_name)}{ext}"
            mod.auth_letter = auth_letter
        mod.save()

        SpocDashboardActivity.objects.create(
            spoc=spoc,
            icon='🔓', color='#7c3aed',
            text=f"Unlocked registration for <strong>{mod.team_name}</strong>"
        )

        if reg:
            TeamNotification.objects.create(
                team_leader=reg.team_leader,
                registration=reg,
                notif_type='system',
                title='Modification Request Approved',
                body='Your request to modify team details has been approved. Your team details are now unlocked for editing.',
            )

        messages.success(request, f"Modification request for '{mod.team_name}' approved. Team is now unlocked.")

    return redirect('spoc_modifications')


@login_required(login_url='/spoc/login/')
@require_POST
def spoc_reject_modification(request, mod_id):
    if not _spoc_required(request):
        return redirect('spoc_login')

    from .models import SpocModificationDecision, SpocDashboardActivity
    from features.models import TeamRegistration
    from team.team.models import TeamNotification

    spoc = _get_spoc(request)
    institution = _get_spoc_institution(spoc)
    mod = get_object_or_404(SpocModificationDecision, id=mod_id, spoc=spoc)
    reg = TeamRegistration.objects.filter(team_name=mod.team_name, institution=institution).first()

    reason = request.POST.get('rejection_reason', '').strip()
    mod.status = 'rejected'
    mod.rejection_reason = reason
    mod.decided_at = timezone.now()
    mod.save()

    SpocDashboardActivity.objects.create(
        spoc=spoc,
        icon='❌', color='#dc2626',
        text=f"Rejected modifications for <strong>{mod.team_name}</strong>"
    )

    if reg:
        TeamNotification.objects.create(
            team_leader=reg.team_leader,
            registration=reg,
            notif_type='system',
            title='Modifications Rejected by SPOC',
            body=f"Your team modifications/request was rejected by the SPOC. Reason: {reason}",
        )

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
#  MESSAGES / COMMUNICATION
# ────────────────────────────────────────────────────────────

def _get_contact_role_label(user):
    if hasattr(user, 'superadmin_profile'):
        return 'Super Admin'
    if hasattr(user, 'admin_profile'):
        return 'Admin'
    if hasattr(user, 'executive_profile'):
        return 'Executive'
    return user.role.name if user.role else 'Contact'


@login_required(login_url='/spoc/login/')
@never_cache
def spoc_messages(request):
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from .models import SpocMessage
    from accounts.models import User

    # Allowed contact types
    available_contact_types = [
        {'value': 'super_admin', 'label': 'Super Admin'},
        {'value': 'admin', 'label': 'Admin'},
        {'value': 'executive', 'label': 'Executive'},
    ]

    # Get all potential admins/superadmins/execs
    admin_users = User.objects.filter(
        Q(is_superuser=True) |
        Q(superadmin_profile__isnull=False) |
        Q(admin_profile__isnull=False) |
        Q(executive_profile__isnull=False)
    ).exclude(id=request.user.id).distinct()

    available_contacts = []
    for admin_user in admin_users:
        contact_type = 'super_admin' if hasattr(admin_user, 'superadmin_profile') else (
            'admin' if hasattr(admin_user, 'admin_profile') else 'executive'
        )
        available_contacts.append({
            'user': admin_user,
            'contact_type': contact_type,
            'role_label': _get_contact_role_label(admin_user),
        })

    # Get active conversations (those with messages)
    conversations = []
    for contact in available_contacts:
        admin_user = contact['user']
        last_message = SpocMessage.objects.filter(
            Q(sender=request.user, recipient=admin_user) | Q(sender=admin_user, recipient=request.user)
        ).order_by('-sent_at').first()
        unread_count = SpocMessage.objects.filter(
            sender=admin_user,
            recipient=request.user,
            is_read=False,
        ).count()
        
        if last_message:
            conversations.append({
                'user': admin_user,
                'contact_type': contact['contact_type'],
                'role_label': contact['role_label'],
                'last_message': last_message,
                'unread_count': unread_count,
            })

    conversations.sort(
        key=lambda item: item['last_message'].sent_at if item['last_message'] else request.user.date_joined,
        reverse=True
    )

    # Handle sending new message from the form
    selected_contact_user_id = request.GET.get('contact')
    selected_contact_type = request.GET.get('contact_type')
    
    selected_contact = None
    selected_thread = []
    
    if selected_contact_user_id:
        try:
            c_user = User.objects.get(id=selected_contact_user_id)
            selected_contact = {
                'user': c_user,
                'role_label': _get_contact_role_label(c_user),
            }
            selected_thread = SpocMessage.objects.filter(
                sender__in=[request.user, c_user],
                recipient__in=[request.user, c_user],
            ).order_by('sent_at')
            
            # Mark unread as read
            SpocMessage.objects.filter(sender=c_user, recipient=request.user, is_read=False).update(is_read=True)
        except User.DoesNotExist:
            pass

    if request.method == 'POST':
        contact_user_id = request.POST.get('contact_user_id')
        body = request.POST.get('body', '').strip()
        if contact_user_id and body:
            try:
                recipient = User.objects.get(id=contact_user_id)
                SpocMessage.objects.create(sender=request.user, recipient=recipient, body=body)
                messages.success(request, 'Message sent successfully.')
                
                # Redirect to the thread
                contact_type = 'super_admin' if hasattr(recipient, 'superadmin_profile') else (
                    'admin' if hasattr(recipient, 'admin_profile') else 'executive'
                )
                return redirect(f"{request.path}?contact={recipient.id}&contact_type={contact_type}")
            except User.DoesNotExist:
                messages.error(request, 'Recipient not found.')

    context = {
        'spoc': spoc,
        'dashboard_title': 'SPOC Communication',
        'available_contact_types': available_contact_types,
        'available_contacts': available_contacts,
        'conversations': conversations,
        'selected_contact_user_id': selected_contact_user_id,
        'selected_contact_type': selected_contact_type,
        'selected_contact': selected_contact,
        'selected_thread': selected_thread,
        'active_nav': 'messages',
    }
    return render(request, 'spoc/messages.html', context)


@login_required(login_url='/spoc/login/')
def spoc_conversation(request, user_id):
    if not _spoc_required(request):
        return redirect('spoc_login')
    from accounts.models import User
    recipient = get_object_or_404(User, id=user_id)
    contact_type = 'super_admin' if hasattr(recipient, 'superadmin_profile') else (
        'admin' if hasattr(recipient, 'admin_profile') else 'executive'
    )
    return redirect(f"/spoc/messages/?contact={user_id}&contact_type={contact_type}")


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
    from features.models import Documentation

    live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    news_items = []
    if live_hackathon:
        news_prefixes = (
            ('[News]', 'news'),
            ('[Announcement]', 'announcement'),
        )
        documentation_links = Documentation.objects.filter(
            hackathon=live_hackathon,
            is_published=True,
        ).order_by('-created_at')
        for item in documentation_links:
            landing_sections = []
            if item.landing_sections:
                if isinstance(item.landing_sections, str):
                    landing_sections = [item.landing_sections]
                else:
                    landing_sections = list(item.landing_sections)
            
            raw_title = (item.title or '').strip()
            is_match = 'latest-news' in landing_sections or any(raw_title.startswith(prefix) for prefix in ('[News]', '[Announcement]'))
            if not is_match:
                continue

            news_type = None
            title = raw_title
            for prefix, mapped_type in news_prefixes:
                if raw_title.startswith(prefix):
                    news_type = mapped_type
                    title = raw_title[len(prefix):].strip(" |:-")
                    break
            if not news_type:
                news_type = 'news'
            
            summary = (item.description or '').strip()
            news_items.append({
                'item': item,
                'title': title or raw_title or item.title,
                'summary': summary,
                'link': item.external_url or (item.file.url if item.file else '#'),
                'type': news_type,
                'type_label': news_type.title(),
                'search_text': ' '.join([
                    raw_title,
                    summary,
                    news_type,
                    item.created_at.strftime('%d %b %Y %I:%M %p') if item.created_at else '',
                ]).lower(),
            })

    rounds = live_hackathon.get_rounds() if live_hackathon else []

    context = {
        'spoc': spoc,
        'live_hackathon': live_hackathon,
        'news_items': news_items,
        'rounds': rounds,
        'active_nav': 'announcements',
    }
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
                <a href="https://hackathon.okcl.org/accounts/dashboard/"
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


@login_required(login_url='/spoc/login/')
@never_cache
def spoc_notifications(request):
    """List all notifications for the logged-in SPOC."""
    if not _spoc_required(request):
        return redirect('spoc_login')

    spoc = _get_spoc(request)
    from .models import SpocNotification

    # Get notifications
    notifications = SpocNotification.objects.filter(spoc=spoc).order_by('-created_at')

    # Mark them all as read when they view this page
    SpocNotification.objects.filter(spoc=spoc, is_read=False).update(is_read=True)

    context = {
        'spoc': spoc,
        'notifications': notifications,
        'active_nav': 'notifications',
    }
    return render(request, 'spoc/notifications.html', context)
