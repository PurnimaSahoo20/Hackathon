"""
team/views.py

Team portal views:
  - public landing + signup (team lead registers)
  - login + OTP 2FA
  - dashboard (partially active until approval)
  - fill team details, add members
  - invite mentor by email
  - submit solution
  - notifications
"""
import os, random, secrets, string, logging
from uuid import uuid4
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.core.files.storage import default_storage

from accounts.passwords import PORTAL_PASSWORD_HELP_TEXT, validate_portal_password

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _team_required(request):
    return request.user.is_authenticated and hasattr(request.user, 'teamlead_profile')

def _gen_token():
    return secrets.token_urlsafe(32)

def _gen_password(length=12):
    return ''.join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(length))


def _get_available_institutions():
    from accounts.models import Institution

    return Institution.objects.filter(
        spocinstitutionmap__isnull=False
    ).distinct().order_by('name')


def _store_registration_upload(upload, folder):
    if not upload:
        return ''
    safe_name = f"{uuid4().hex}_{os.path.basename(upload.name)}"
    return default_storage.save(f"{folder}/{safe_name}", upload)


def _can_edit_registration(reg):
    if not reg or not reg.hackathon or not reg.hackathon.registration_close:
        return True
    return timezone.localdate() <= reg.hackathon.registration_close


def _team_nav_context(request, active_nav, reg=None):
    from .models import TeamNotification

    return {
        'active_nav': active_nav,
        'is_approved': bool(reg and reg.status == 'approved'),
        'notif_count': TeamNotification.objects.filter(team_leader=request.user, is_read=False).count()
        if getattr(request, 'user', None) and request.user.is_authenticated else 0,
    }


def _get_team_registration(request):
    from features.models import TeamRegistration

    return TeamRegistration.objects.filter(
        team_leader=request.user
    ).select_related('hackathon', 'problem_statement', 'mentor', 'institution').order_by('-registered_at').first()


def _get_dashboard_data(reg):
    from features.models import Documentation, Podcast, Venue
    from events.models import CreativeMaterial
    from mentor.mentor.models import MentorInvitation
    from .models import TeamSolution, TeamSupportMessage, TeamTravelDetail

    data = {
        'solutions': TeamSolution.objects.none(),
        'travel_details': TeamTravelDetail.objects.none(),
        'support_messages': TeamSupportMessage.objects.none(),
        'mentor_invite': None,
        'resources': Documentation.objects.none(),
        'podcasts': Podcast.objects.none(),
        'creatives': CreativeMaterial.objects.none(),
        'venue': None,
        'members': [],
        'leader_details': {},
        'rounds': [],
        'active_round': None,
        'slots_open': 0,
    }
    if not reg:
        return data

    mentor_invite = MentorInvitation.objects.filter(
        registration=reg
    ).order_by('-invited_at').first()
    resources = Documentation.objects.filter(
        hackathon=reg.hackathon,
        is_published=True,
    )
    if reg.problem_statement:
        resources = resources.filter(problem_statement=reg.problem_statement)

    data.update({
        'solutions': TeamSolution.objects.filter(registration=reg),
        'travel_details': TeamTravelDetail.objects.filter(registration=reg),
        'support_messages': TeamSupportMessage.objects.filter(registration=reg),
        'mentor_invite': mentor_invite,
        'resources': resources,
        'podcasts': Podcast.objects.filter(
            hackathon=reg.hackathon,
            is_published=True,
            publication_scope='internal',
        ),
        'creatives': CreativeMaterial.objects.filter(
            hackathon=reg.hackathon, is_published=True, is_suspended=False,
        ),
        'venue': Venue.objects.filter(hackathon=reg.hackathon, status='Active').order_by('-updated_at').first(),
        'members': reg.get_members_display(),
        'leader_details': dict(reg.leader_details or {}),
        'rounds': reg.hackathon.get_rounds() if reg.hackathon else [],
        'active_round': reg.hackathon.active_round if reg.hackathon else None,
        'slots_open': max((reg.hackathon.max_team_size or 4) - reg.get_member_count(), 0),
    })
    return data

def _send_otp(user, otp_code):
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;
                background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
        <h2 style="color:#2563eb;">HackNexus Team Login — 2FA</h2>
        <p>Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
        <div style="background:#eff6ff;border:2px dashed #2563eb;border-radius:8px;
                    padding:24px;text-align:center;margin:24px 0;">
            <span style="font-size:36px;font-weight:900;letter-spacing:12px;color:#2563eb;">{otp_code}</span>
        </div>
        <p style="color:#6b7280;font-size:13px;">Valid for <strong>10 minutes</strong>.</p>
    </div>"""
    try:
        msg = EmailMultiAlternatives(
            subject='HackNexus Team Portal — Verification Code',
            body=f'Your OTP: {otp_code}',
            from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email])
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.error(f"Team OTP email error: {exc}")

# ─────────────────────────────────────────────────────────────
#  LANDING / REGISTER
# ─────────────────────────────────────────────────────────────

def team_landing(request):
    """Public landing page — register or login."""
    if request.user.is_authenticated and _team_required(request):
        return redirect('team_dashboard')
    from events.models import Hackathon
    hackathons = Hackathon.objects.filter(status='Live').order_by('-created_at')
    return render(request, 'team/landing.html', {'hackathons': hackathons})


def team_register(request):
    """Team lead signs up and creates a new TeamRegistration."""
    if request.user.is_authenticated and _team_required(request):
        return redirect('team_dashboard')

    from events.models import Hackathon
    hackathons = Hackathon.objects.filter(status='Live').order_by('-created_at')
    institutions = _get_available_institutions()

    if request.method == 'POST':
        first_name   = request.POST.get('first_name', '').strip()
        last_name    = request.POST.get('last_name', '').strip()
        email        = request.POST.get('email', '').strip().lower()
        phone        = request.POST.get('phone', '').strip()
        password     = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        hackathon_id = request.POST.get('hackathon')
        institution_id = request.POST.get('institution')
        team_name    = request.POST.get('team_name', '').strip()

        from accounts.models import User, Role, TeamleadProfile
        from features.models import TeamRegistration

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'An account with this email already exists. Please log in.')
            return render(request, 'team/register.html', {'hackathons': hackathons, 'institutions': institutions})

        if password != confirm_password:
            messages.error(request, 'Password and confirm password do not match.')
            return render(request, 'team/register.html', {'hackathons': hackathons, 'institutions': institutions})

        try:
            validate_portal_password(password)
        except Exception as exc:
            for error in (getattr(exc, 'messages', None) or [str(exc)]):
                messages.error(request, error)
            return render(request, 'team/register.html', {'hackathons': hackathons, 'institutions': institutions})

        if not hackathon_id and hackathons.exists():
            hackathon = hackathons.first()
        else:
            try:
                hackathon = Hackathon.objects.get(id=hackathon_id)
            except Hackathon.DoesNotExist:
                messages.error(request, 'Please select a valid hackathon.')
                return render(request, 'team/register.html', {'hackathons': hackathons, 'institutions': institutions})

        institution = institutions.filter(id=institution_id).first()
        if institution is None:
            messages.error(request, 'Please select a valid institution from the approved SPOC list.')
            return render(request, 'team/register.html', {'hackathons': hackathons, 'institutions': institutions})

        # Create user
        role, _ = Role.objects.get_or_create(name='Team Lead', defaults={'description': 'Hackathon team leader'})
        base_username = email.split('@')[0].replace('.', '').replace('-', '')[:15] or 'team'
        username = base_username
        i = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{i}"; i += 1

        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name,
            phone_number=phone or None, role=role, is_active=True,
        )
        TeamleadProfile.objects.create(user=user)

        # Create TeamRegistration (status=pending)
        reg = TeamRegistration.objects.create(
            hackathon=hackathon,
            team_name=team_name or f"Team {first_name}",
            team_leader=user,
            institution=institution,
            status='pending',
        )

        # Create TeamNotification
        from .models import TeamNotification
        TeamNotification.objects.create(
            team_leader=user, registration=reg,
            notif_type='system',
            title='Registration Submitted',
            body='Your team registration has been submitted. Complete your team details and invite a mentor to proceed.',
        )

        # Log in immediately
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
        messages.success(request, f'Registration successful! Complete your team details below.')
        return redirect('team_dashboard')

    return render(request, 'team/register.html', {'hackathons': hackathons, 'institutions': institutions})

# ─────────────────────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────────────────────

@never_cache
def team_login(request):
    next_url = request.GET.get('next', '')
    login_url = reverse('login')
    if next_url:
        return redirect(f'{login_url}?next={next_url}')
    return redirect('login')


@never_cache
def team_verify_otp(request):
    user_id = request.session.get('team_pending_2fa_user_id')
    if not user_id:
        return redirect('team_login')

    from accounts.models import User, OTPVerification
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('team_login')

    if request.method == 'POST':
        otp_code = request.POST.get('otp', '').strip()
        record = OTPVerification.objects.filter(user=user, code=otp_code, is_verified=False).order_by('-created_at').first()
        if record and not record.is_expired():
            record.is_verified = True; record.save()
            del request.session['team_pending_2fa_user_id']
            login(request, user)
            return redirect('team_dashboard')
        else:
            messages.error(request, 'Invalid or expired OTP.')

    return render(request, 'team/verify_otp.html', {'email': user.email})


@login_required(login_url='/team/login/')
def team_logout(request):
    logout(request)
    return redirect('landing_page')

# ─────────────────────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/team/login/')
@never_cache
def team_dashboard(request):
    if not _team_required(request):
        return redirect('team_login')

    from .models import TeamNotification

    reg = _get_team_registration(request)

    notifs = TeamNotification.objects.filter(team_leader=request.user, is_read=False)[:5]
    notif_count = TeamNotification.objects.filter(team_leader=request.user, is_read=False).count()
    steps = _get_pipeline_steps(reg)
    data = _get_dashboard_data(reg)

    context = {
        'reg': reg,
        'steps': steps,
        'notifs': notifs,
        'notif_count': notif_count,
        'is_fully_active': reg and reg.status == 'approved',
        'active_nav': 'dashboard',
        'is_approved': reg and reg.status == 'approved',
        **data,
    }
    return render(request, 'team/dashboard.html', context)


def _get_pipeline_steps(reg):
    """Returns list of (label, status) for the approval pipeline."""
    if not reg:
        return []
    from mentor.mentor.models import MentorInvitation

    mentor_invite = MentorInvitation.objects.filter(registration=reg).order_by('-invited_at').first()
    has_submission = reg.solutions.exists()
    team_details_done = bool(reg.members_data or reg.problem_statement or reg.leader_details)
    mentor_status = 'pending'
    mentor_review_status = 'pending'

    if mentor_invite:
        mentor_status = 'done'
        if mentor_invite.status in ['accepted', 'spoc_approved', 'admin_approved', 'active']:
            mentor_review_status = 'done'
        elif mentor_invite.status in ['invited']:
            mentor_review_status = 'active'
    elif reg.mentor:
        mentor_status = 'done'
        mentor_review_status = 'done'

    steps = [
        ('Registered', 'done'),
        ('Team Details Filled', 'done' if team_details_done else 'active'),
        ('Mentor Invited', mentor_status),
        ('Mentor Review', mentor_review_status),
        ('SPOC Approved', 'done' if reg.status == 'approved' else ('active' if reg.status == 'pending' else 'pending')),
        ('Dashboard Active', 'done' if reg.status == 'approved' else 'pending'),
        ('Upload Solution', 'done' if has_submission else ('active' if reg.status == 'approved' else 'pending')),
    ]
    return steps

# ─────────────────────────────────────────────────────────────
#  TEAM DETAILS
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/team/login/')
@never_cache
def team_details(request):
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    from events.models import ProblemStatement, Hackathon

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        return redirect('team_dashboard')

    problem_statements = ProblemStatement.objects.filter(hackathon=reg.hackathon)
    institutions = _get_available_institutions()

    if request.method == 'POST':
        if not _can_edit_registration(reg):
            messages.error(request, 'Team details can no longer be edited because the registration deadline has passed.')
            return redirect('team_details')

        reg.team_name = request.POST.get('team_name', reg.team_name).strip()
        ps_id = request.POST.get('problem_statement')
        inst_id = request.POST.get('institution')
        if ps_id:
            try:
                reg.problem_statement = ProblemStatement.objects.get(id=ps_id)
            except ProblemStatement.DoesNotExist:
                pass
        if inst_id:
            try:
                reg.institution = institutions.get(id=inst_id)
            except institutions.model.DoesNotExist:
                pass

        leader_details = dict(reg.leader_details or {})
        leader = request.user
        leader.first_name = request.POST.get('leader_first_name', leader.first_name).strip()
        leader.last_name = request.POST.get('leader_last_name', leader.last_name).strip()
        leader.phone_number = request.POST.get('leader_phone_number', leader.phone_number or '').strip() or None
        leader.gender = request.POST.get('leader_gender', leader.gender or '').strip() or None
        leader_dob = request.POST.get('leader_date_of_birth', '').strip()
        leader.date_of_birth = leader_dob or None

        leader_id_proof = request.FILES.get('leader_id_proof')
        if leader_id_proof:
            leader.id_proof = leader_id_proof

        leader.save()

        leader_details.update({
            'role_in_team': request.POST.get('leader_role_in_team', leader_details.get('role_in_team', 'Team Lead')).strip() or 'Team Lead',
            'cast': request.POST.get('leader_cast', leader_details.get('cast', '')).strip(),
            'tshirt_size': request.POST.get('leader_tshirt_size', leader_details.get('tshirt_size', '')).strip(),
            'aadhaar_number': request.POST.get('leader_aadhaar_number', leader_details.get('aadhaar_number', '')).strip(),
            'bank_account': request.POST.get('leader_bank_account', leader_details.get('bank_account', '')).strip(),
            'ifsc': request.POST.get('leader_ifsc', leader_details.get('ifsc', '')).strip(),
            'bank_name': request.POST.get('leader_bank_name', leader_details.get('bank_name', '')).strip(),
        })

        leader_aadhaar = request.FILES.get('leader_aadhaar_proof')
        if leader_aadhaar:
            leader_details['aadhaar_proof'] = _store_registration_upload(leader_aadhaar, 'team_registration/leader/aadhaar')

        leader_college_id = request.FILES.get('leader_college_id_proof')
        if leader_college_id:
            leader_details['college_id_proof'] = _store_registration_upload(leader_college_id, 'team_registration/leader/college_ids')

        if leader.id_proof:
            leader_details['id_proof'] = leader.id_proof.name

        reg.leader_details = leader_details
        reg.save()
        messages.success(request, 'Team details updated.')
        return redirect('team_details')

    leader_details = dict(reg.leader_details or {})
    context = {
        'reg': reg,
        'problem_statements': problem_statements,
        'institutions': institutions,
        'members': reg.members_data or [],
        'leader_details': leader_details,
        'can_edit_registration': _can_edit_registration(reg),
        'registration_deadline': reg.hackathon.registration_close,
        **_team_nav_context(request, 'details', reg),
    }
    return render(request, 'team/details.html', context)


@login_required(login_url='/team/login/')
@require_POST
def team_add_member(request):
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    from .models import TeamMemberInvite

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        messages.error(request, 'No registration found.')
        return redirect('team_details')

    if not _can_edit_registration(reg):
        messages.error(request, 'Members can no longer be added because the registration deadline has passed.')
        return redirect('team_details')

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    name = f"{first_name} {last_name}".strip()
    email = request.POST.get('email', '').strip().lower()
    role  = request.POST.get('role', 'Member').strip()

    if not email:
        messages.error(request, 'Email is required.')
        return redirect('team_details')

    # Add to members_data JSON
    members = list(reg.members_data or [])
    if any(m.get('email', '').lower() == email for m in members):
        messages.warning(request, 'This member is already in the team.')
        return redirect('team_details')

    member_data = {
        'name': name,
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone_number': request.POST.get('phone_number', '').strip(),
        'role': role,
        'role_in_team': role,
        'date_of_birth': request.POST.get('date_of_birth', '').strip(),
        'gender': request.POST.get('gender', '').strip(),
        'cast': request.POST.get('cast', '').strip(),
        'tshirt_size': request.POST.get('tshirt_size', '').strip(),
        'aadhaar_number': request.POST.get('aadhaar_number', '').strip(),
        'bank_account': request.POST.get('bank_account', '').strip(),
        'ifsc': request.POST.get('ifsc', '').strip(),
        'bank_name': request.POST.get('bank_name', '').strip(),
    }

    aadhaar_proof = request.FILES.get('aadhaar_proof')
    if aadhaar_proof:
        member_data['aadhaar_proof'] = _store_registration_upload(aadhaar_proof, 'team_registration/members/aadhaar')

    college_id_proof = request.FILES.get('college_id_proof')
    if college_id_proof:
        member_data['college_id_proof'] = _store_registration_upload(college_id_proof, 'team_registration/members/college_ids')

    id_proof = request.FILES.get('id_proof')
    if id_proof:
        member_data['id_proof'] = _store_registration_upload(id_proof, 'team_registration/members/id_proofs')

    members.append(member_data)
    reg.members_data = members
    reg.save(update_fields=['members_data'])

    # Send invite email
    token = _gen_token()
    invite = TeamMemberInvite.objects.create(
        registration=reg, inviter=request.user,
        email=email, name=name, role=role, token=token,
    )
    _send_member_invite_email(invite, reg)
    messages.success(request, f'Member {name or email} added and invite sent.')
    return redirect('team_details')


def _send_member_invite_email(invite, reg):
    try:
        subject = f"You've been added to team '{reg.team_name}' on HackNexus"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                    padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
            <h2 style="color:#2563eb;">Team Invitation 🎉</h2>
            <p>Hello <strong>{invite.name or invite.email}</strong>,</p>
            <p>You've been added as a member of team <strong>"{reg.team_name}"</strong> for
               <strong>{reg.hackathon.name}</strong>.</p>
            <p style="color:#6b7280;font-size:13px;">Role: {invite.role}</p>
            <p style="margin-top:16px;color:#6b7280;font-size:13px;">
                Your team lead will complete the registration process. You'll be notified once the team is approved.
            </p>
        </div>"""
        msg = EmailMultiAlternatives(
            subject=subject, body=f'You joined team {reg.team_name}.',
            from_email=settings.DEFAULT_FROM_EMAIL, to=[invite.email])
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    except Exception as exc:
        logger.error(f"Member invite email failed: {exc}")


# ─────────────────────────────────────────────────────────────
#  MENTOR INVITE
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/team/login/')
@never_cache
def team_invite_mentor(request):
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    from mentor.mentor.models import MentorInvitation

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        return redirect('team_dashboard')

    if not reg.institution_id:
        messages.error(request, 'Select your college from the approved SPOC list before inviting a mentor.')
        return redirect('team_details')

    existing_invite = MentorInvitation.objects.filter(
        team_leader=request.user, registration=reg
    ).order_by('-invited_at').first()

    if request.method == 'POST':
        mentor_name  = request.POST.get('mentor_name', '').strip()
        mentor_email = request.POST.get('mentor_email', '').strip().lower()

        if not mentor_name or not mentor_email:
            messages.error(request, 'Mentor name and email are required.')
            return redirect('team_invite_mentor')

        token = _gen_token()
        invite = MentorInvitation.objects.create(
            team_leader=request.user,
            registration=reg,
            hackathon=reg.hackathon,
            mentor_name=mentor_name,
            mentor_email=mentor_email,
            token=token,
            status='invited',
        )
        _send_mentor_invite_email(invite, reg, request)
        messages.success(request, f'Mentor invitation sent to {mentor_email}.')
        return redirect('team_invite_mentor')

    context = {
        'reg': reg,
        'existing_invite': existing_invite,
        **_team_nav_context(request, 'mentor', reg),
    }
    return render(request, 'team/invite_mentor.html', context)


def _send_mentor_invite_email(invite, reg, request):
    try:
        accept_url = request.build_absolute_uri(f'/mentor/invite/{invite.token}/')
        subject = f"Mentor Invitation — Team '{reg.team_name}' on HackNexus"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                    padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
            <h2 style="color:#059669;">You're Invited to be a Mentor! 🎓</h2>
            <p>Hello <strong>{invite.mentor_name}</strong>,</p>
            <p><strong>{request.user.get_full_name() or request.user.username}</strong> has invited you to be the mentor for their team <strong>"{reg.team_name}"</strong>.</p>
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;margin:20px 0;">
                <div style="font-size:13px;margin-bottom:8px;color:#374151;"><strong>Hackathon:</strong> {reg.hackathon.name}</div>
                <div style="font-size:13px;margin-bottom:8px;color:#374151;"><strong>Team:</strong> {reg.team_name}</div>
                <div style="font-size:13px;color:#374151;"><strong>Problem Statement:</strong> {reg.problem_statement.title if reg.problem_statement else "To be selected"}</div>
            </div>
            <a href="{accept_url}"
               style="background:#059669;color:white;padding:14px 28px;border-radius:10px;
                      text-decoration:none;font-weight:700;display:inline-block;font-size:15px;">
                View Details &amp; Accept Invitation →
            </a>
            <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
                This link is valid. If you have questions, contact the team lead at {request.user.email}.
            </p>
        </div>"""
        msg = EmailMultiAlternatives(
            subject=subject, body=f'Mentor invite: {accept_url}',
            from_email=settings.DEFAULT_FROM_EMAIL, to=[invite.mentor_email])
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.error(f"Mentor invite email failed: {exc}")


# ─────────────────────────────────────────────────────────────
#  SOLUTION SUBMISSION
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/team/login/')
@never_cache
def team_submission(request):
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    from .models import TeamSolution

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        return redirect('team_dashboard')

    solutions = TeamSolution.objects.filter(registration=reg)

    if request.method == 'POST':
        if reg.status != 'approved':
            messages.error(request, 'Your team must be approved before submitting solutions.')
            return redirect('team_submission')

        title = request.POST.get('title', '').strip()
        desc  = request.POST.get('description', '').strip()

        if not title:
            messages.error(request, 'Please provide a title for your submission.')
            return redirect('team_submission')

        ppt_file = request.FILES.get('ppt_file')
        report_file = request.FILES.get('report_file')
        code_file = request.FILES.get('code_file')
        video_url = request.POST.get('video_url', '').strip()
        other_file = request.FILES.get('other_file')

        if not ppt_file:
            messages.error(request, 'Presentation (PPT/PDF) is required.')
            return redirect('team_submission')

        # Create separate submission records for each uploaded asset
        TeamSolution.objects.create(
            registration=reg, uploaded_by=request.user,
            title=f"{title} (Presentation)", doc_type='ppt',
            file=ppt_file, description=desc
        )

        if report_file:
            TeamSolution.objects.create(
                registration=reg, uploaded_by=request.user,
                title=f"{title} (Report)", doc_type='report',
                file=report_file, description=desc
            )

        if code_file:
            TeamSolution.objects.create(
                registration=reg, uploaded_by=request.user,
                title=f"{title} (Code)", doc_type='code',
                file=code_file, description=desc
            )

        if video_url:
            TeamSolution.objects.create(
                registration=reg, uploaded_by=request.user,
                title=f"{title} (Video URL)", doc_type='video',
                video_url=video_url, description=desc
            )

        if other_file:
            TeamSolution.objects.create(
                registration=reg, uploaded_by=request.user,
                title=f"{title} (Other Asset)", doc_type='other',
                file=other_file, description=desc
            )

        messages.success(request, 'Solution assets submitted successfully!')
        return redirect('team_submission')

    context = {
        'reg': reg,
        'solutions': solutions,
        'is_approved': reg.status == 'approved',
        **_team_nav_context(request, 'submission', reg),
    }
    return render(request, 'team/submission.html', context)


@login_required(login_url='/team/login/')
@require_POST
def team_add_travel(request):
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    from .models import TeamTravelDetail

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        messages.error(request, 'No registration found.')
        return redirect('team_dashboard')

    origin = request.POST.get('origin', '').strip()
    destination = request.POST.get('destination', '').strip()
    journey_date = request.POST.get('journey_date', '').strip()
    travel_mode = request.POST.get('travel_mode', 'train').strip() or 'train'

    if not origin or not destination or not journey_date:
        messages.error(request, 'Please fill origin, destination, and journey date.')
        return redirect('team_travel')

    ticket_amount_str = request.POST.get('ticket_amount', '').strip()
    ticket_amount = float(ticket_amount_str) if ticket_amount_str else None

    TeamTravelDetail.objects.create(
        registration=reg,
        submitted_by=request.user,
        origin=origin,
        destination=destination,
        journey_date=journey_date,
        travel_mode=travel_mode,
        traveler_name=request.POST.get('traveler_name', '').strip(),
        ticket_number=request.POST.get('ticket_number', '').strip(),
        ticket_amount=ticket_amount,
        notes=request.POST.get('notes', '').strip(),
        ticket_file=request.FILES.get('ticket_file'),
    )
    messages.success(request, 'Travel details added successfully.')
    return redirect('team_travel')


@login_required(login_url='/team/login/')
@require_POST
def team_send_support_message(request):
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    from .models import TeamSupportMessage

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        messages.error(request, 'No registration found.')
        return redirect('team_dashboard')

    subject = request.POST.get('subject', '').strip()
    message_text = request.POST.get('message', '').strip()
    if not subject or not message_text:
        messages.error(request, 'Subject and message are required.')
        return redirect('team_dashboard')

    TeamSupportMessage.objects.create(
        registration=reg,
        sender=request.user,
        category=request.POST.get('category', 'general').strip() or 'general',
        subject=subject,
        message=message_text,
        attachment=request.FILES.get('attachment'),
    )
    messages.success(request, 'Your message has been logged for admin review.')
    return redirect('team_communication')


@login_required(login_url='/team/login/')
@never_cache
def team_communication(request):
    if not _team_required(request):
        return redirect('team_login')

    reg = _get_team_registration(request)
    if not reg:
        return redirect('team_dashboard')

    data = _get_dashboard_data(reg)
    return render(request, 'team/communication.html', {
        'reg': reg,
        'support_messages': data['support_messages'],
        **_team_nav_context(request, 'communication', reg),
    })


@login_required(login_url='/team/login/')
@never_cache
def team_travel(request):
    if not _team_required(request):
        return redirect('team_login')

    reg = _get_team_registration(request)
    if not reg:
        return redirect('team_dashboard')

    data = _get_dashboard_data(reg)
    return render(request, 'team/travel.html', {
        'reg': reg,
        'travel_details': data['travel_details'],
        **_team_nav_context(request, 'travel', reg),
    })


@login_required(login_url='/team/login/')
@never_cache
def team_content(request):
    if not _team_required(request):
        return redirect('team_login')

    reg = _get_team_registration(request)
    if not reg:
        return redirect('team_dashboard')

    data = _get_dashboard_data(reg)
    return render(request, 'team/content.html', {
        'reg': reg,
        'resources': data['resources'][:10],
        'podcasts': data['podcasts'][:4],
        'venue': data['venue'],
        **_team_nav_context(request, 'content', reg),
    })


@login_required(login_url='/team/login/')
@never_cache
def team_announcements(request):
    if not _team_required(request):
        return redirect('team_login')

    reg = _get_team_registration(request)
    if not reg:
        return redirect('team_dashboard')

    from .models import TeamNotification
    notifs = TeamNotification.objects.filter(team_leader=request.user)
    return render(request, 'team/announcements.html', {
        'reg': reg,
        'notifs': notifs,
        **_team_nav_context(request, 'announcements', reg),
    })


@login_required(login_url='/team/login/')
@never_cache
def team_results(request):
    if not _team_required(request):
        return redirect('team_login')

    reg = _get_team_registration(request)
    if not reg:
        return redirect('team_dashboard')

    data = _get_dashboard_data(reg)
    return render(request, 'team/results.html', {
        'reg': reg,
        'solutions': data['solutions'][:10],
        'rounds': data['rounds'],
        'active_round': data['active_round'],
        **_team_nav_context(request, 'results', reg),
    })


@login_required(login_url='/team/login/')
@never_cache
def team_memories(request):
    if not _team_required(request):
        return redirect('team_login')

    reg = _get_team_registration(request)
    if not reg:
        return redirect('team_dashboard')

    data = _get_dashboard_data(reg)
    return render(request, 'team/memories.html', {
        'reg': reg,
        'creatives': data['creatives'][:12],
        **_team_nav_context(request, 'memories', reg),
    })


@login_required(login_url='/team/login/')
@never_cache
def team_media(request):
    if not _team_required(request):
        return redirect('team_login')

    reg = _get_team_registration(request)
    if not reg:
        return redirect('team_dashboard')

    data = _get_dashboard_data(reg)
    return render(request, 'team/media.html', {
        'reg': reg,
        'podcasts': data['podcasts'][:10],
        'creatives': data['creatives'][:10],
        **_team_nav_context(request, 'media', reg),
    })


# ─────────────────────────────────────────────────────────────
#  NOTIFICATIONS
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/team/login/')
@never_cache
def team_notifications(request):
    if not _team_required(request):
        return redirect('team_login')

    from .models import TeamNotification
    notifs = TeamNotification.objects.filter(team_leader=request.user)
    TeamNotification.objects.filter(team_leader=request.user, is_read=False).update(is_read=True)
    reg = getattr(request.user, 'led_registrations', None)
    reg = reg.order_by('-registered_at').first() if reg is not None else None
    return render(request, 'team/notifications.html', {
        'notifs': notifs,
        **_team_nav_context(request, 'notifications', reg),
    })


# ─────────────────────────────────────────────────────────────
#  PROFILE
# ─────────────────────────────────────────────────────────────

@login_required(login_url='/team/login/')
@never_cache
def team_profile(request):
    if not _team_required(request):
        return redirect('team_login')

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile')
        if form_type == 'password':
            current_password = request.POST.get('current_password', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()

            if not current_password or not new_password or not confirm_password:
                messages.error(request, 'All password fields are required.')
            elif not request.user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New password and confirm password do not match.')
            else:
                try:
                    validate_portal_password(new_password, request.user)
                    request.user.set_password(new_password)
                    request.user.save(update_fields=['password'])
                    update_session_auth_hash(request, request.user)
                    messages.success(request, 'Password changed successfully.')
                except Exception as exc:
                    for error in (getattr(exc, 'messages', None) or [str(exc)]):
                        messages.error(request, error)
        else:
            request.user.first_name = request.POST.get('first_name', request.user.first_name)
            request.user.last_name  = request.POST.get('last_name',  request.user.last_name)
            request.user.phone_number = request.POST.get('phone_number', request.user.phone_number)
            if request.FILES.get('profile_image'):
                request.user.profile_image = request.FILES['profile_image']
            request.user.save()
            messages.success(request, 'Profile updated.')
        return redirect('team_profile')

    from features.models import TeamRegistration
    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    return render(request, 'team/profile.html', {
        'reg': reg,
        'password_help_text': PORTAL_PASSWORD_HELP_TEXT,
        **_team_nav_context(request, 'profile', reg),
    })
