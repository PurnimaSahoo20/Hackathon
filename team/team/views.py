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
    if timezone.localdate() > reg.hackathon.registration_close:
        return False
    if reg.status == 'approved':
        from spoc.spoc.models import SpocModificationDecision
        # Locked by default unless they have an active pending or approved modification request
        return SpocModificationDecision.objects.filter(team_name=reg.team_name, status__in=['pending', 'approved']).exists()
    return True


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


def _check_duplicate_aadhaar_bank(hackathon, aadhaar_number, bank_account, exclude_email=None):
    """Check for duplicate Aadhaar or bank account numbers across all registrations in the hackathon."""
    from features.models import TeamRegistration
    errors = []
    if not aadhaar_number and not bank_account:
        return errors

    registrations = TeamRegistration.objects.filter(hackathon=hackathon)
    for reg in registrations:
        # Check leader_details
        ld = reg.leader_details or {}
        leader_email = reg.team_leader.email.lower() if reg.team_leader else ''
        if exclude_email and leader_email == exclude_email.lower():
            pass  # skip self
        else:
            if aadhaar_number and ld.get('aadhaar_number') == aadhaar_number:
                errors.append(f'Aadhaar number {aadhaar_number} is already registered by another participant.')
            if bank_account and ld.get('bank_account') == bank_account:
                errors.append(f'Bank account number {bank_account} is already registered by another participant.')

        # Check members_data
        for m in (reg.members_data or []):
            m_email = (m.get('email') or '').lower()
            if exclude_email and m_email == exclude_email.lower():
                continue  # skip self
            if aadhaar_number and m.get('aadhaar_number') == aadhaar_number:
                errors.append(f'Aadhaar number {aadhaar_number} is already registered by another participant.')
            if bank_account and m.get('bank_account') == bank_account:
                errors.append(f'Bank account number {bank_account} is already registered by another participant.')

    # Deduplicate
    return list(dict.fromkeys(errors))

def _get_open_hackathons():
    from events.models import Hackathon
    from django.db.models import Q
    today = timezone.localdate()
    return Hackathon.objects.filter(
        status='Live'
    ).filter(
        Q(registration_open__isnull=True) | Q(registration_open__lte=today)
    ).filter(
        Q(registration_close__isnull=True) | Q(registration_close__gte=today)
    ).order_by('-created_at')

def _get_registration_check(today=None):
    if today is None:
        today = timezone.localdate()
    from events.models import Hackathon
    latest = Hackathon.objects.order_by('-created_at').first()
    if not latest:
        return {
            'allowed': False,
            'status': 'no_event',
            'message': 'No hackathon event has been configured yet.',
            'hackathon': None
        }
    
    if latest.status != 'Live':
        return {
            'allowed': False,
            'status': 'not_live',
            'message': f"Registration for '{latest.name}' is closed because the event is not live.",
            'hackathon': latest
        }
        
    if latest.registration_open and today < latest.registration_open:
        start_date = latest.registration_open.strftime('%d %b %Y')
        return {
            'allowed': False,
            'status': 'before_start',
            'message': f"Registration for '{latest.name}' has not started yet. It will open on {start_date}.",
            'hackathon': latest
        }
        
    if latest.registration_close and today > latest.registration_close:
        close_date = latest.registration_close.strftime('%d %b %Y')
        return {
            'allowed': False,
            'status': 'after_deadline',
            'message': f"Registration for '{latest.name}' has closed. The deadline was on {close_date}.",
            'hackathon': latest
        }
        
    return {
        'allowed': True,
        'status': 'open',
        'message': '',
        'hackathon': latest
    }

# ─────────────────────────────────────────────────────────────
#  LANDING / REGISTER
# ─────────────────────────────────────────────────────────────

@never_cache
def team_landing(request):
    """Public landing page — register or login."""
    if request.user.is_authenticated and _team_required(request):
        return redirect('team_dashboard')
    hackathons = _get_open_hackathons()
    reg_check = _get_registration_check()
    return render(request, 'team/landing.html', {
        'hackathons': hackathons,
        'reg_check': reg_check,
    })


def team_register(request):
    """Team lead signs up and creates a new TeamRegistration."""
    if request.user.is_authenticated and _team_required(request):
        return redirect('team_dashboard')

    reg_check = _get_registration_check()
    if not reg_check['allowed']:
        messages.error(request, reg_check['message'])
        return redirect('team_landing')

    hackathons = _get_open_hackathons()
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
            hackathon = hackathons.filter(id=hackathon_id).first()
            if not hackathon:
                messages.error(request, 'Please select a valid hackathon with open registration.')
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

        # Send welcome email
        _send_team_lead_welcome_email(user, reg)

        # Log in immediately
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
        messages.success(request, f'Registration successful! Check your email for next steps. Complete your team details below.')
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

    from features.models import Team
    team_obj = Team.objects.filter(team_leader=request.user).first()
    if team_obj and team_obj.status == 'disqualified':
        return render(request, 'team/suspended.html', {'team': team_obj})

    from .models import TeamNotification
    from features.models import Documentation

    reg = _get_team_registration(request)

    notifs = TeamNotification.objects.filter(team_leader=request.user, is_read=False)[:5]
    notif_count = TeamNotification.objects.filter(team_leader=request.user, is_read=False).count()
    steps = _get_pipeline_steps(reg)
    data = _get_dashboard_data(reg)

    news_items = []
    news_prefixes = (
        ('[News]', 'news'),
        ('[Announcement]', 'announcement'),
    )
    if reg and reg.hackathon:
        documentation_links = Documentation.objects.filter(
            hackathon=reg.hackathon,
            is_published=True,
        ).order_by('-created_at')
        for item in documentation_links:
            # check landing section
            landing_sections = []
            if item.landing_sections:
                if isinstance(item.landing_sections, str):
                    landing_sections = [item.landing_sections]
                else:
                    landing_sections = list(item.landing_sections)
            
            # Match latest-news, or legacy prefixes
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
            if len(news_items) >= 5:
                break

    context = {
        'reg': reg,
        'steps': steps,
        'notifs': notifs,
        'notif_count': notif_count,
        'is_fully_active': reg and reg.status == 'approved',
        'active_nav': 'dashboard',
        'is_approved': reg and reg.status == 'approved',
        'news_items': news_items,
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

        # Helper to re-render form with errors (keeps form open)
        def _rerender_with_errors():
            # Update user in-memory
            user = request.user
            user.first_name = request.POST.get('leader_first_name', user.first_name)
            user.last_name = request.POST.get('leader_last_name', user.last_name)
            user.phone_number = request.POST.get('leader_phone_number', user.phone_number)
            user.gender = request.POST.get('leader_gender', user.gender)
            dob_str = request.POST.get('leader_date_of_birth', '')
            if dob_str:
                try:
                    from django.utils.dateparse import parse_date
                    user.date_of_birth = parse_date(dob_str) or user.date_of_birth
                except Exception:
                    pass
            
            # Update team name in-memory
            reg.team_name = request.POST.get('team_name', reg.team_name)

            # Update leader details context
            leader_details_ctx = dict(reg.leader_details or {})
            leader_details_ctx.update({
                'role_in_team': request.POST.get('leader_role_in_team', leader_details_ctx.get('role_in_team', 'Team Lead')),
                'middle_name': request.POST.get('leader_middle_name', leader_details_ctx.get('middle_name', '')),
                'aadhaar_number': request.POST.get('leader_aadhaar_number', leader_details_ctx.get('aadhaar_number', '')),
                'bank_account': request.POST.get('leader_bank_account', leader_details_ctx.get('bank_account', '')),
                'ifsc': request.POST.get('leader_ifsc', leader_details_ctx.get('ifsc', '')),
                'bank_name': request.POST.get('leader_bank_name', leader_details_ctx.get('bank_name', '')),
                'cast': request.POST.get('leader_cast', leader_details_ctx.get('cast', '')),
                'tshirt_size': request.POST.get('leader_tshirt_size', leader_details_ctx.get('tshirt_size', '')),
            })

            from spoc.spoc.models import SpocModificationDecision
            mod_requests = SpocModificationDecision.objects.filter(team_name=reg.team_name).order_by('-requested_at')
            has_approved_mod = mod_requests.filter(status='approved').exists()

            ctx = {
                'reg': reg,
                'problem_statements': problem_statements,
                'institutions': institutions,
                'members': reg.members_data or [],
                'leader_details': leader_details_ctx,
                'can_edit_registration': _can_edit_registration(reg),
                'registration_deadline': reg.hackathon.registration_close,
                'show_leader_form': True,
                'mod_requests': mod_requests,
                'has_approved_mod': has_approved_mod,
                **_team_nav_context(request, 'details', reg),
            }
            return render(request, 'team/details.html', ctx)

        # Required field checks for Team Lead
        validation_errors = []
        leader_first = request.POST.get('leader_first_name', '').strip()
        leader_last = request.POST.get('leader_last_name', '').strip()
        leader_phone_raw = request.POST.get('leader_phone_number', '').strip()
        leader_dob_raw = request.POST.get('leader_date_of_birth', '').strip()
        leader_gender_raw = request.POST.get('leader_gender', '').strip()
        leader_cast_raw = request.POST.get('leader_cast', '').strip()
        leader_tshirt_raw = request.POST.get('leader_tshirt_size', '').strip()
        leader_aadhaar_raw = request.POST.get('leader_aadhaar_number', '').strip().replace(' ', '').replace('-', '')
        leader_bank_raw = request.POST.get('leader_bank_account', '').strip()
        leader_ifsc_raw = request.POST.get('leader_ifsc', '').strip().upper()
        leader_bank_name_raw = request.POST.get('leader_bank_name', '').strip()

        if not leader_first:
            validation_errors.append('First Name is required.')
        if not leader_last:
            validation_errors.append('Last Name is required.')
        if not leader_phone_raw:
            validation_errors.append('Phone Number is required.')
        if not leader_dob_raw:
            validation_errors.append('Date of Birth is required.')
        if not leader_gender_raw:
            validation_errors.append('Gender is required.')
        if not leader_cast_raw:
            validation_errors.append('Cast Category is required.')
        if not leader_tshirt_raw:
            validation_errors.append('T-Shirt Size is required.')
        if not leader_aadhaar_raw:
            validation_errors.append('Aadhaar Card Number is required.')
        if not leader_bank_raw:
            validation_errors.append('Bank Account Number is required.')
        if not leader_ifsc_raw:
            validation_errors.append('IFSC Code is required.')
        if not leader_bank_name_raw:
            validation_errors.append('Bank Name is required.')

        # File uploads: required only if not already uploaded
        existing_leader = dict(reg.leader_details or {})
        if not request.FILES.get('leader_photo') and not existing_leader.get('photo'):
            validation_errors.append('Passport Size Photo is required.')
        if not request.FILES.get('leader_college_id_proof') and not existing_leader.get('college_id_proof'):
            validation_errors.append('College ID Proof is required.')
        if not request.FILES.get('leader_aadhaar_proof') and not existing_leader.get('aadhaar_proof'):
            validation_errors.append('Aadhaar Proof Document is required.')
        if not request.FILES.get('leader_passbook_proof') and not existing_leader.get('passbook_proof'):
            validation_errors.append('Bank Passbook Front Page is required.')

        if validation_errors:
            for err in validation_errors:
                messages.error(request, err)
            return _rerender_with_errors()

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

        # Backend validations for Team Lead details
        leader_phone = request.POST.get('leader_phone_number', '').strip()
        if leader_phone:
            cleaned_phone = leader_phone.replace(' ', '').replace('-', '')
            if cleaned_phone.startswith('+91'):
                cleaned_phone = cleaned_phone[3:]
            import re
            if not re.match(r'^[6-9]\d{9}$', cleaned_phone):
                messages.error(request, 'Team Lead phone number must be a valid 10-digit mobile number.')
                return _rerender_with_errors()
            leader.phone_number = cleaned_phone
        else:
            leader.phone_number = None

        leader_dob = request.POST.get('leader_date_of_birth', '').strip()
        if leader_dob:
            import datetime
            try:
                dob_val = datetime.datetime.strptime(leader_dob, '%Y-%m-%d').date()
                if dob_val >= timezone.localdate():
                    messages.error(request, 'Team Lead Date of Birth cannot be in the future.')
                    return _rerender_with_errors()
            except ValueError:
                messages.error(request, 'Invalid Team Lead Date of Birth format.')
                return _rerender_with_errors()
            leader.date_of_birth = leader_dob
        else:
            leader.date_of_birth = None

        leader_aadhaar_num = request.POST.get('leader_aadhaar_number', '').strip().replace(' ', '').replace('-', '')
        if leader_aadhaar_num:
            import re
            if not re.match(r'^\d{12}$', leader_aadhaar_num):
                messages.error(request, 'Team Lead Aadhaar number must be exactly 12 digits.')
                return _rerender_with_errors()

        leader_bank_acc = request.POST.get('leader_bank_account', '').strip()
        if leader_bank_acc:
            import re
            if not re.match(r'^\d{9,18}$', leader_bank_acc):
                messages.error(request, 'Team Lead Bank Account number must be between 9 and 18 digits.')
                return _rerender_with_errors()

        leader_ifsc = request.POST.get('leader_ifsc', '').strip().upper()
        if leader_ifsc:
            import re
            if not re.match(r'^[A-Z]{4}[A-Z0-9]{7}$', leader_ifsc):
                messages.error(request, 'Team Lead IFSC code must be a valid 11-character alphanumeric code (e.g. SBIN0001234).')
                return _rerender_with_errors()

        # Duplicate Aadhaar / Bank Account check
        dup_errors = _check_duplicate_aadhaar_bank(
            reg.hackathon, leader_aadhaar_num, leader_bank_acc,
            exclude_email=request.user.email
        )
        if dup_errors:
            for err in dup_errors:
                messages.error(request, err)
            return _rerender_with_errors()

        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        max_file_size = 2 * 1024 * 1024  # 2MB

        leader_aadhaar = request.FILES.get('leader_aadhaar_proof')
        if leader_aadhaar:
            import os
            ext = os.path.splitext(leader_aadhaar.name)[1].lower()
            if ext not in allowed_extensions:
                messages.error(request, 'Team Lead Aadhaar proof must be a PDF, JPG, JPEG, or PNG file.')
                return _rerender_with_errors()
            if leader_aadhaar.size > max_file_size:
                messages.error(request, 'Team Lead Aadhaar proof file size must not exceed 2MB.')
                return _rerender_with_errors()

        leader_college_id = request.FILES.get('leader_college_id_proof')
        if leader_college_id:
            import os
            ext = os.path.splitext(leader_college_id.name)[1].lower()
            if ext not in allowed_extensions:
                messages.error(request, 'Team Lead College ID proof must be a PDF, JPG, JPEG, or PNG file.')
                return _rerender_with_errors()
            if leader_college_id.size > max_file_size:
                messages.error(request, 'Team Lead College ID proof file size must not exceed 2MB.')
                return _rerender_with_errors()

        leader_photo = request.FILES.get('leader_photo')
        if leader_photo:
            import os
            ext = os.path.splitext(leader_photo.name)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png']:
                messages.error(request, 'Team Lead Passport photo must be a JPG, JPEG, or PNG file.')
                return _rerender_with_errors()
            if leader_photo.size > max_file_size:
                messages.error(request, 'Team Lead Passport photo file size must not exceed 2MB.')
                return _rerender_with_errors()

        leader_passbook = request.FILES.get('leader_passbook_proof')
        if leader_passbook:
            import os
            ext = os.path.splitext(leader_passbook.name)[1].lower()
            if ext not in allowed_extensions:
                messages.error(request, 'Team Lead Bank Passbook proof must be a PDF, JPG, JPEG, or PNG file.')
                return _rerender_with_errors()
            if leader_passbook.size > max_file_size:
                messages.error(request, 'Team Lead Bank Passbook proof file size must not exceed 2MB.')
                return _rerender_with_errors()

        leader.first_name = request.POST.get('leader_first_name', leader.first_name).strip()
        leader.last_name = request.POST.get('leader_last_name', leader.last_name).strip()
        leader.gender = request.POST.get('leader_gender', leader.gender or '').strip() or None
        leader.save()

        leader_details.update({
            'role_in_team': request.POST.get('leader_role_in_team', leader_details.get('role_in_team', 'Team Lead')).strip() or 'Team Lead',
            'middle_name': request.POST.get('leader_middle_name', '').strip(),
            'cast': request.POST.get('leader_cast', leader_details.get('cast', '')).strip(),
            'tshirt_size': request.POST.get('leader_tshirt_size', leader_details.get('tshirt_size', '')).strip(),
            'aadhaar_number': leader_aadhaar_num,
            'bank_account': leader_bank_acc,
            'ifsc': leader_ifsc,
            'bank_name': request.POST.get('leader_bank_name', leader_details.get('bank_name', '')).strip(),
        })

        if leader_photo:
            leader_details['photo'] = _store_registration_upload(leader_photo, 'team_registration/leader/photo')

        if leader_passbook:
            leader_details['passbook_proof'] = _store_registration_upload(leader_passbook, 'team_registration/leader/passbook')

        if leader_aadhaar:
            leader_details['aadhaar_proof'] = _store_registration_upload(leader_aadhaar, 'team_registration/leader/aadhaar')

        if leader_college_id:
            leader_details['college_id_proof'] = _store_registration_upload(leader_college_id, 'team_registration/leader/college_ids')

        reg.leader_details = leader_details
        reg.save()

        # Handle Resubmission
        action_resubmit = request.POST.get('action_resubmit')
        action_submit_mod = request.POST.get('action_submit_modification')

        if action_resubmit:
            reg.status = 'pending'
            reg.rejection_note = ''
            reg.save()

            # Create TeamNotification
            from .models import TeamNotification
            TeamNotification.objects.create(
                team_leader=request.user,
                registration=reg,
                notif_type='system',
                title='Registration Resubmitted',
                body='Your team registration has been resubmitted to the SPOC for review.',
            )

            # Notify SPOC
            from accounts.models import SpocInstitutionMap
            from spoc.spoc.models import SpocNotification
            mapping = SpocInstitutionMap.objects.filter(institution=reg.institution).select_related('spoc').first()
            if mapping and mapping.spoc:
                SpocNotification.objects.create(
                    spoc=mapping.spoc,
                    notif_type='team_reg',
                    title='Team Registration Resubmitted',
                    body=f"Team '{reg.team_name}' has updated their details and resubmitted their registration.",
                    link=f"/spoc/teams/{reg.id}/",
                )

            messages.success(request, 'Team details updated and registration resubmitted successfully.')
            return redirect('team_dashboard')

        elif action_submit_mod:
            from spoc.spoc.models import SpocModificationDecision
            mods = SpocModificationDecision.objects.filter(team_name=reg.team_name, status__in=['pending', 'approved'])
            if mods.exists():
                mods.update(status='resolved')

                # Notify SPOC
                from accounts.models import SpocInstitutionMap
                from spoc.spoc.models import SpocNotification
                mapping = SpocInstitutionMap.objects.filter(institution=reg.institution).select_related('spoc').first()
                if mapping and mapping.spoc:
                    SpocNotification.objects.create(
                        spoc=mapping.spoc,
                        notif_type='mod_req',
                        title='Team Modifications Completed',
                        body=f"Team '{reg.team_name}' has completed their composition updates. Ready for final approval and letter upload.",
                        link=f"/spoc/teams/{reg.id}/",
                    )

            messages.success(request, 'Team details updated and modifications submitted successfully.')
            return redirect('team_details')

        messages.success(request, 'Team details updated.')
        return redirect('team_details')

    leader_details = dict(reg.leader_details or {})
    from spoc.spoc.models import SpocModificationDecision
    mod_requests = SpocModificationDecision.objects.filter(team_name=reg.team_name).order_by('-requested_at')
    has_approved_mod = mod_requests.filter(status='approved').exists()
    has_submitted_mod = mod_requests.filter(status='submitted').exists()
    max_size_reached = (len(reg.members_data or []) + 1) >= (reg.hackathon.max_team_size or 4)

    context = {
        'reg': reg,
        'problem_statements': problem_statements,
        'institutions': institutions,
        'members': reg.members_data or [],
        'leader_details': leader_details,
        'can_edit_registration': _can_edit_registration(reg),
        'registration_deadline': reg.hackathon.registration_close,
        'mod_requests': mod_requests,
        'has_approved_mod': has_approved_mod,
        'has_submitted_mod': has_submitted_mod,
        'max_size_reached': max_size_reached,
        **_team_nav_context(request, 'details', reg),
    }
    context['add_member_form_data'] = request.session.pop('add_member_form_data', None)
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
        return redirect(reverse('team_details') + '?show_add_member=1')

    if not _can_edit_registration(reg):
        messages.error(request, 'Members can no longer be added because the registration deadline has passed.')
        return redirect(reverse('team_details') + '?show_add_member=1')

    # Enforce maximum team size validation
    max_size = reg.hackathon.max_team_size or 4
    if reg.get_member_count() >= max_size:
        messages.error(request, f'You cannot add more members. The maximum team size for this hackathon is {max_size}.')
        return redirect('team_details')

    if request.method == 'POST':
        form_data = {}
        for key in request.POST:
            if key != 'csrfmiddlewaretoken':
                form_data[key] = request.POST.get(key, '')
        request.session['add_member_form_data'] = form_data

    middle_name = request.POST.get('middle_name', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    
    parts = [p for p in [first_name, middle_name, last_name] if p]
    name = " ".join(parts)
    
    email = request.POST.get('email', '').strip().lower()
    role  = request.POST.get('role', 'Member').strip()

    # Required field checks
    add_errors = []
    if not first_name:
        add_errors.append('First Name is required.')
    if not last_name:
        add_errors.append('Last Name is required.')
    if not email:
        add_errors.append('Email is required.')

    phone = request.POST.get('phone_number', '').strip()
    if not phone:
        add_errors.append('Phone Number is required.')
    dob_str = request.POST.get('date_of_birth', '').strip()
    if not dob_str:
        add_errors.append('Date of Birth is required.')
    if not request.POST.get('gender', '').strip():
        add_errors.append('Gender is required.')
    if not request.POST.get('cast', '').strip():
        add_errors.append('Cast Category is required.')
    if not request.POST.get('tshirt_size', '').strip():
        add_errors.append('T-Shirt Size is required.')

    aadhaar_raw = request.POST.get('aadhaar_number', '').strip().replace(' ', '').replace('-', '')
    if not aadhaar_raw:
        add_errors.append('Aadhaar Card Number is required.')
    bank_acc_raw = request.POST.get('bank_account', '').strip()
    if not bank_acc_raw:
        add_errors.append('Bank Account Number is required.')
    if not request.POST.get('ifsc', '').strip():
        add_errors.append('IFSC Code is required.')
    if not request.POST.get('bank_name', '').strip():
        add_errors.append('Bank Name is required.')

    # File upload checks
    if not request.FILES.get('photo'):
        add_errors.append('Passport Size Photo is required.')
    if not request.FILES.get('college_id_proof'):
        add_errors.append('College ID Proof is required.')
    if not request.FILES.get('aadhaar_proof'):
        add_errors.append('Aadhaar Proof Document is required.')
    if not request.FILES.get('passbook_proof'):
        add_errors.append('Bank Passbook Front Page is required.')

    if add_errors:
        for err in add_errors:
            messages.error(request, err)
        return redirect(reverse('team_details') + '?show_add_member=1')

    if not email:
        messages.error(request, 'Email is required.')
        return redirect(reverse('team_details') + '?show_add_member=1')

    if email == reg.team_leader.email.lower().strip():
        messages.error(request, 'The team leader cannot be added as a member.')
        return redirect(reverse('team_details') + '?show_add_member=1')

    # Add to members_data JSON
    members = list(reg.members_data or [])
    if any(m.get('email', '').lower() == email for m in members):
        messages.warning(request, 'This member is already in the team.')
        return redirect(reverse('team_details') + '?show_add_member=1')

    # Backend validations for Team Member
    phone = request.POST.get('phone_number', '').strip()
    if phone:
        cleaned_phone = phone.replace(' ', '').replace('-', '')
        if cleaned_phone.startswith('+91'):
            cleaned_phone = cleaned_phone[3:]
        import re
        if not re.match(r'^[6-9]\d{9}$', cleaned_phone):
            messages.error(request, 'Member phone number must be a valid 10-digit mobile number.')
            return redirect(reverse('team_details') + '?show_add_member=1')
        phone_val = cleaned_phone
    else:
        phone_val = ''

    dob_str = request.POST.get('date_of_birth', '').strip()
    if dob_str:
        import datetime
        try:
            dob_val = datetime.datetime.strptime(dob_str, '%Y-%m-%d').date()
            if dob_val >= timezone.localdate():
                messages.error(request, 'Member Date of Birth cannot be in the future.')
                return redirect('team_details')
        except ValueError:
            messages.error(request, 'Invalid Member Date of Birth format.')
            return redirect(reverse('team_details') + '?show_add_member=1')
        dob_val = dob_str
    else:
        dob_val = ''

    aadhaar = request.POST.get('aadhaar_number', '').strip().replace(' ', '').replace('-', '')
    if aadhaar:
        import re
        if not re.match(r'^\d{12}$', aadhaar):
            messages.error(request, 'Member Aadhaar Card number must be exactly 12 digits.')
            return redirect(reverse('team_details') + '?show_add_member=1')
        aadhaar_val = aadhaar
    else:
        aadhaar_val = ''

    bank_acc = request.POST.get('bank_account', '').strip()
    if bank_acc:
        import re
        if not re.match(r'^\d{9,18}$', bank_acc):
            messages.error(request, 'Member Bank Account number must be between 9 and 18 digits.')
            return redirect(reverse('team_details') + '?show_add_member=1')
        bank_acc_val = bank_acc
    else:
        bank_acc_val = ''

    ifsc = request.POST.get('ifsc', '').strip().upper()
    if ifsc:
        import re
        if not re.match(r'^[A-Z]{4}[A-Z0-9]{7}$', ifsc):
            messages.error(request, 'Member IFSC code must be a valid 11-character alphanumeric code (e.g. SBIN0001234).')
            return redirect(reverse('team_details') + '?show_add_member=1')
        ifsc_val = ifsc
    else:
        ifsc_val = ''

    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    max_file_size = 2 * 1024 * 1024  # 2MB

    photo = request.FILES.get('photo')
    if photo:
        import os
        ext = os.path.splitext(photo.name)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png']:
            messages.error(request, 'Member Passport photo must be a JPG, JPEG, or PNG file.')
            return redirect(reverse('team_details') + '?show_add_member=1')
        if photo.size > max_file_size:
            messages.error(request, 'Member Passport photo file size must not exceed 2MB.')
            return redirect(reverse('team_details') + '?show_add_member=1')

    passbook_proof = request.FILES.get('passbook_proof')
    if passbook_proof:
        import os
        ext = os.path.splitext(passbook_proof.name)[1].lower()
        if ext not in allowed_extensions:
            messages.error(request, 'Member Bank Passbook proof must be a PDF, JPG, JPEG, or PNG file.')
            return redirect(reverse('team_details') + '?show_add_member=1')
        if passbook_proof.size > max_file_size:
            messages.error(request, 'Member Bank Passbook proof file size must not exceed 2MB.')
            return redirect(reverse('team_details') + '?show_add_member=1')

    aadhaar_proof = request.FILES.get('aadhaar_proof')
    if aadhaar_proof:
        import os
        ext = os.path.splitext(aadhaar_proof.name)[1].lower()
        if ext not in allowed_extensions:
            messages.error(request, 'Member Aadhaar proof must be a PDF, JPG, JPEG, or PNG file.')
            return redirect(reverse('team_details') + '?show_add_member=1')
        if aadhaar_proof.size > max_file_size:
            messages.error(request, 'Member Aadhaar proof file size must not exceed 2MB.')
            return redirect(reverse('team_details') + '?show_add_member=1')

    college_id_proof = request.FILES.get('college_id_proof')
    if college_id_proof:
        import os
        ext = os.path.splitext(college_id_proof.name)[1].lower()
        if ext not in allowed_extensions:
            messages.error(request, 'Member College ID proof must be a PDF, JPG, JPEG, or PNG file.')
            return redirect(reverse('team_details') + '?show_add_member=1')
        if college_id_proof.size > max_file_size:
            messages.error(request, 'Member College ID proof file size must not exceed 2MB.')
            return redirect(reverse('team_details') + '?show_add_member=1')

    # Duplicate Aadhaar / Bank Account check for member
    dup_errors = _check_duplicate_aadhaar_bank(
        reg.hackathon, aadhaar_val, bank_acc_val,
        exclude_email=email
    )
    if dup_errors:
        for err in dup_errors:
            messages.error(request, err)
        return redirect(reverse('team_details') + '?show_add_member=1')

    member_data = {
        'name': name,
        'first_name': first_name,
        'middle_name': middle_name,
        'last_name': last_name,
        'email': email,
        'phone_number': phone_val,
        'role': role,
        'role_in_team': role,
        'date_of_birth': dob_val,
        'gender': request.POST.get('gender', '').strip(),
        'cast': request.POST.get('cast', '').strip(),
        'tshirt_size': request.POST.get('tshirt_size', '').strip(),
        'aadhaar_number': aadhaar_val,
        'bank_account': bank_acc_val,
        'ifsc': ifsc_val,
        'bank_name': request.POST.get('bank_name', '').strip(),
    }

    if photo:
        member_data['photo'] = _store_registration_upload(photo, 'team_registration/members/photo')

    if passbook_proof:
        member_data['passbook_proof'] = _store_registration_upload(passbook_proof, 'team_registration/members/passbook')

    if aadhaar_proof:
        member_data['aadhaar_proof'] = _store_registration_upload(aadhaar_proof, 'team_registration/members/aadhaar')

    if college_id_proof:
        member_data['college_id_proof'] = _store_registration_upload(college_id_proof, 'team_registration/members/college_ids')

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

    # Resubmit / Submit Modification actions
    action_resubmit = request.POST.get('action_resubmit')
    action_submit_mod = request.POST.get('action_submit_modification')

    if action_resubmit:
        reg.status = 'pending'
        reg.rejection_note = ''
        reg.save()

        # Notify SPOC
        from accounts.models import SpocInstitutionMap
        from spoc.spoc.models import SpocNotification
        mapping = SpocInstitutionMap.objects.filter(institution=reg.institution).select_related('spoc').first()
        if mapping and mapping.spoc:
            SpocNotification.objects.create(
                spoc=mapping.spoc,
                notif_type='team_reg',
                title='Team Registration Resubmitted',
                body=f"Team '{reg.team_name}' has updated their composition and resubmitted their registration.",
                link=f"/spoc/teams/{reg.id}/",
            )
        request.session.pop('add_member_form_data', None)
        messages.success(request, f"Member '{name or email}' added, invite sent and registration resubmitted.")
        return redirect('team_dashboard')

    elif action_submit_mod:
        from spoc.spoc.models import SpocModificationDecision
        mods = SpocModificationDecision.objects.filter(team_name=reg.team_name, status='approved')
        if mods.exists():
            mods.update(status='submitted')

            # Notify SPOC
            from accounts.models import SpocInstitutionMap
            from spoc.spoc.models import SpocNotification
            mapping = SpocInstitutionMap.objects.filter(institution=reg.institution).select_related('spoc').first()
            if mapping and mapping.spoc:
                SpocNotification.objects.create(
                    spoc=mapping.spoc,
                    notif_type='mod_req',
                    title='Modifications Submitted for Approval',
                    body=f"Team '{reg.team_name}' has updated their composition and submitted modifications for your final review and approval.",
                    link="/spoc/modifications/",
                )
        request.session.pop('add_member_form_data', None)
        messages.success(request, f"Member '{name or email}' added, invite sent and modifications submitted.")
        return redirect('team_details')

    request.session.pop('add_member_form_data', None)
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






@login_required(login_url='/team/login/')
@require_POST
def team_edit_member(request, member_index):
    """Edit an existing team member's details."""
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        messages.error(request, 'No registration found.')
        return redirect('team_details')

    if not _can_edit_registration(reg):
        messages.error(request, 'Members can no longer be edited because the registration deadline has passed.')
        return redirect('team_details')

    members = list(reg.members_data or [])
    if member_index < 0 or member_index >= len(members):
        messages.error(request, 'Invalid member.')
        return redirect('team_details')

    existing = members[member_index]
    redir_url = reverse('team_details') + f'?show_edit_member={member_index}'

    # Collect field values
    middle_name = request.POST.get('middle_name', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    parts = [p for p in [first_name, middle_name, last_name] if p]
    name = " ".join(parts)
    email = request.POST.get('email', '').strip().lower()
    role = request.POST.get('role', 'Member').strip()

    # Required field checks
    edit_errors = []
    if not first_name:
        edit_errors.append('First Name is required.')
    if not last_name:
        edit_errors.append('Last Name is required.')
    if not email:
        edit_errors.append('Email is required.')

    phone = request.POST.get('phone_number', '').strip()
    if not phone:
        edit_errors.append('Phone Number is required.')
    dob_str = request.POST.get('date_of_birth', '').strip()
    if not dob_str:
        edit_errors.append('Date of Birth is required.')
    if not request.POST.get('gender', '').strip():
        edit_errors.append('Gender is required.')
    if not request.POST.get('cast', '').strip():
        edit_errors.append('Cast Category is required.')
    if not request.POST.get('tshirt_size', '').strip():
        edit_errors.append('T-Shirt Size is required.')

    aadhaar_raw = request.POST.get('aadhaar_number', '').strip().replace(' ', '').replace('-', '')
    if not aadhaar_raw:
        edit_errors.append('Aadhaar Card Number is required.')
    bank_acc_raw = request.POST.get('bank_account', '').strip()
    if not bank_acc_raw:
        edit_errors.append('Bank Account Number is required.')
    if not request.POST.get('ifsc', '').strip():
        edit_errors.append('IFSC Code is required.')
    if not request.POST.get('bank_name', '').strip():
        edit_errors.append('Bank Name is required.')

    # File uploads: required if not already present
    if not request.FILES.get('photo') and not existing.get('photo'):
        edit_errors.append('Passport Size Photo is required.')
    if not request.FILES.get('college_id_proof') and not existing.get('college_id_proof'):
        edit_errors.append('College ID Proof is required.')
    if not request.FILES.get('aadhaar_proof') and not existing.get('aadhaar_proof'):
        edit_errors.append('Aadhaar Proof Document is required.')
    if not request.FILES.get('passbook_proof') and not existing.get('passbook_proof'):
        edit_errors.append('Bank Passbook Front Page is required.')

    if edit_errors:
        for err in edit_errors:
            messages.error(request, err)
        return redirect(redir_url)

    # Check duplicate email (not self)
    if email == reg.team_leader.email.lower().strip():
        messages.error(request, 'The team leader cannot be added as a member.')
        return redirect(redir_url)
    for i, m in enumerate(members):
        if i != member_index and m.get('email', '').lower() == email:
            messages.warning(request, 'This email is already used by another member.')
            return redirect(redir_url)

    # Validate phone
    if phone:
        cleaned_phone = phone.replace(' ', '').replace('-', '')
        if cleaned_phone.startswith('+91'):
            cleaned_phone = cleaned_phone[3:]
        import re
        if not re.match(r'^[6-9]\d{9}$', cleaned_phone):
            messages.error(request, 'Member phone number must be a valid 10-digit mobile number.')
            return redirect(redir_url)
        phone_val = cleaned_phone
    else:
        phone_val = ''

    # Validate DOB
    if dob_str:
        import datetime
        try:
            dob_val = datetime.datetime.strptime(dob_str, '%Y-%m-%d').date()
            if dob_val >= timezone.localdate():
                messages.error(request, 'Member Date of Birth cannot be in the future.')
                return redirect(redir_url)
        except ValueError:
            messages.error(request, 'Invalid Member Date of Birth format.')
            return redirect(redir_url)
        dob_val = dob_str
    else:
        dob_val = ''

    # Validate Aadhaar
    if aadhaar_raw:
        import re
        if not re.match(r'^\d{12}$', aadhaar_raw):
            messages.error(request, 'Member Aadhaar Card number must be exactly 12 digits.')
            return redirect(redir_url)
        aadhaar_val = aadhaar_raw
    else:
        aadhaar_val = ''

    # Validate bank account
    if bank_acc_raw:
        import re
        if not re.match(r'^\d{9,18}$', bank_acc_raw):
            messages.error(request, 'Member Bank Account number must be between 9 and 18 digits.')
            return redirect(redir_url)
        bank_acc_val = bank_acc_raw
    else:
        bank_acc_val = ''

    # Validate IFSC
    ifsc = request.POST.get('ifsc', '').strip().upper()
    if ifsc:
        import re
        if not re.match(r'^[A-Z]{4}[A-Z0-9]{7}$', ifsc):
            messages.error(request, 'Member IFSC code must be a valid 11-character code.')
            return redirect(redir_url)
        ifsc_val = ifsc
    else:
        ifsc_val = ''

    # Duplicate check
    dup_errors = _check_duplicate_aadhaar_bank(
        reg.hackathon, aadhaar_val, bank_acc_val, exclude_email=email
    )
    if dup_errors:
        for err in dup_errors:
            messages.error(request, err)
        return redirect(redir_url)

    # File validations and uploads
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    max_file_size = 2 * 1024 * 1024

    updated_data = {
        'name': name,
        'first_name': first_name,
        'middle_name': middle_name,
        'last_name': last_name,
        'email': email,
        'phone_number': phone_val,
        'role': role,
        'role_in_team': role,
        'date_of_birth': dob_val,
        'gender': request.POST.get('gender', '').strip(),
        'cast': request.POST.get('cast', '').strip(),
        'tshirt_size': request.POST.get('tshirt_size', '').strip(),
        'aadhaar_number': aadhaar_val,
        'bank_account': bank_acc_val,
        'ifsc': ifsc_val,
        'bank_name': request.POST.get('bank_name', '').strip(),
    }

    # Preserve existing uploads, override with new ones
    for file_key, upload_path in [
        ('photo', 'team_registration/members/photo'),
        ('passbook_proof', 'team_registration/members/passbook'),
        ('aadhaar_proof', 'team_registration/members/aadhaar'),
        ('college_id_proof', 'team_registration/members/college_ids'),
    ]:
        uploaded = request.FILES.get(file_key)
        if uploaded:
            import os
            ext = os.path.splitext(uploaded.name)[1].lower()
            valid_ext = ['.jpg', '.jpeg', '.png'] if file_key == 'photo' else allowed_extensions
            if ext not in valid_ext:
                messages.error(request, f'Invalid file type for {file_key}.')
                return redirect(redir_url)
            if uploaded.size > max_file_size:
                messages.error(request, f'{file_key} file size must not exceed 2MB.')
                return redirect(redir_url)
            updated_data[file_key] = _store_registration_upload(uploaded, upload_path)
        elif existing.get(file_key):
            updated_data[file_key] = existing[file_key]

    # Also preserve user_id if it exists
    if existing.get('user_id'):
        updated_data['user_id'] = existing['user_id']

    members[member_index] = updated_data
    reg.members_data = members
    reg.save(update_fields=['members_data'])

    # Resubmit / Submit Modification actions
    action_resubmit = request.POST.get('action_resubmit')
    action_submit_mod = request.POST.get('action_submit_modification')

    if action_resubmit:
        reg.status = 'pending'
        reg.rejection_note = ''
        reg.save()

        # Notify SPOC
        from accounts.models import SpocInstitutionMap
        from spoc.spoc.models import SpocNotification
        mapping = SpocInstitutionMap.objects.filter(institution=reg.institution).select_related('spoc').first()
        if mapping and mapping.spoc:
            SpocNotification.objects.create(
                spoc=mapping.spoc,
                notif_type='team_reg',
                title='Team Registration Resubmitted',
                body=f"Team '{reg.team_name}' has updated their composition and resubmitted their registration.",
                link=f"/spoc/teams/{reg.id}/",
            )
        messages.success(request, f"Member '{name or email}' updated and registration resubmitted.")
        return redirect('team_dashboard')

    elif action_submit_mod:
        from spoc.spoc.models import SpocModificationDecision
        mods = SpocModificationDecision.objects.filter(team_name=reg.team_name, status='approved')
        if mods.exists():
            mods.update(status='submitted')

            # Notify SPOC
            from accounts.models import SpocInstitutionMap
            from spoc.spoc.models import SpocNotification
            mapping = SpocInstitutionMap.objects.filter(institution=reg.institution).select_related('spoc').first()
            if mapping and mapping.spoc:
                SpocNotification.objects.create(
                    spoc=mapping.spoc,
                    notif_type='mod_req',
                    title='Modifications Submitted for Approval',
                    body=f"Team '{reg.team_name}' has updated their composition and submitted modifications for your final review and approval.",
                    link="/spoc/modifications/",
                )
        messages.success(request, f"Member '{name or email}' updated and modifications submitted.")
        return redirect('team_details')

    messages.success(request, f'Member {name or email} updated successfully.')
    return redirect('team_details')


def _send_team_lead_welcome_email(user, reg):
    """Send a branded welcome email to the team lead after registration."""
    try:
        event_name = reg.hackathon.name if reg.hackathon else "HackNexus"
        dashboard_url = "https://hackathon.okcl.org/team/dashboard/"
        details_url = "https://hackathon.okcl.org/team/details/"
        full_name = user.get_full_name() or user.username

        subject = f"Welcome to {event_name} — Complete Your Team Registration"

        plain_body = f"""Hello {full_name},

Congratulations! Your team "{reg.team_name}" has been successfully registered for {event_name}.

Your Dashboard: {dashboard_url}

Next Steps — Please complete the following:

1. Fill Your Personal Details
   - Go to Team Details in your dashboard
   - Fill all required fields: name, phone, DOB, gender, Aadhaar, bank details
   - Upload required documents: photo, college ID, Aadhaar proof, bank passbook

2. Add Team Members
   - Add each team member with their complete details
   - Each member needs: name, email, phone, DOB, gender, Aadhaar, bank details
   - Upload documents for each member

3. Invite Your Mentor
   - Send a mentor invitation from the Mentor section
   - Your mentor will guide your team through the hackathon

Important: All details must be completed before the registration deadline.

Best regards,
{event_name} Team
"""

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 20px; background: #f9f9f9;">
            <table cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 0 auto; background: #fff; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <tr>
                    <td style="background: linear-gradient(135deg, #2563eb, #1d4ed8); padding: 30px; text-align: center; color: #fff;">
                        <h1 style="margin: 0; font-size: 24px;">{event_name}</h1>
                        <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">Team Registration Successful</p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 30px;">
                        <p style="margin-top: 0;">Hello <strong>{full_name}</strong>,</p>
                        <p>Congratulations! Your team <strong>"{reg.team_name}"</strong> has been successfully registered for <strong>{event_name}</strong>.</p>

                        <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0 0 10px 0; font-weight: 700; color: #1e40af;">Your Team Dashboard</p>
                            <a href="{dashboard_url}" style="background: #2563eb; color: #fff; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 700; display: inline-block;">Open Dashboard &rarr;</a>
                        </div>

                        <h3 style="color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 5px; margin-top: 28px;">Next Steps</h3>
                        <p>Please complete the following to finalize your registration:</p>

                        <div style="background: #f0fdf4; border-left: 4px solid #22c55e; padding: 14px 18px; margin: 12px 0; border-radius: 0 8px 8px 0;">
                            <p style="margin: 0; font-weight: 700; color: #166534;">Step 1 — Fill Your Personal Details</p>
                            <ul style="margin: 8px 0 0 0; padding-left: 18px; color: #374151; font-size: 14px;">
                                <li>Go to <a href="{details_url}" style="color: #2563eb;">Team Details</a> in your dashboard</li>
                                <li>Fill all required fields: name, phone, DOB, gender, cast, t-shirt size</li>
                                <li>Fill Aadhaar number and bank account details</li>
                                <li>Upload: passport photo, college ID, Aadhaar proof, bank passbook</li>
                            </ul>
                        </div>

                        <div style="background: #fff7ed; border-left: 4px solid #f97316; padding: 14px 18px; margin: 12px 0; border-radius: 0 8px 8px 0;">
                            <p style="margin: 0; font-weight: 700; color: #9a3412;">Step 2 — Add Team Members</p>
                            <ul style="margin: 8px 0 0 0; padding-left: 18px; color: #374151; font-size: 14px;">
                                <li>Add each team member with their complete details</li>
                                <li>Each member needs: name, email, phone, DOB, gender, Aadhaar, bank info</li>
                                <li>Upload documents for each member</li>
                            </ul>
                        </div>

                        <div style="background: #faf5ff; border-left: 4px solid #a855f7; padding: 14px 18px; margin: 12px 0; border-radius: 0 8px 8px 0;">
                            <p style="margin: 0; font-weight: 700; color: #6b21a8;">Step 3 — Invite Your Mentor</p>
                            <ul style="margin: 8px 0 0 0; padding-left: 18px; color: #374151; font-size: 14px;">
                                <li>Send a mentor invitation from the Mentor section</li>
                                <li>Your mentor will guide your team through the hackathon</li>
                            </ul>
                        </div>

                        <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px; margin: 20px 0;">
                            <p style="margin: 0; font-size: 13px; color: #991b1b; font-weight: 600;">&#9888; All details must be completed before the registration deadline.</p>
                        </div>

                        <p style="margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px; color: #9ca3af; font-size: 12px;">
                            Best regards,<br>{event_name} Team
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
            to=[user.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)
    except Exception as exc:
        logger.error(f"Team lead welcome email failed for {user.email}: {exc}")


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
        if not _can_edit_registration(reg):
            messages.error(request, 'You cannot invite/replace a mentor because your registration is locked.')
            return redirect('team_invite_mentor')

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
        'can_edit_registration': _can_edit_registration(reg),
        **_team_nav_context(request, 'mentor', reg),
    }
    return render(request, 'team/invite_mentor.html', context)


def _send_mentor_invite_email(invite, reg, request):
    try:
        accept_url = f"https://hackathon.okcl.org/mentor/invite/{invite.token}/"
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
    from features.models import Documentation

    # Check unread count first
    unread_count = TeamNotification.objects.filter(team_leader=request.user, is_read=False).count()
    has_unread = unread_count > 0

    # Get general hackathon news/announcements
    news_items = []
    news_prefixes = (
        ('[News]', 'news'),
        ('[Announcement]', 'announcement'),
    )
    if reg.hackathon:
        documentation_links = Documentation.objects.filter(
            hackathon=reg.hackathon,
            is_published=True,
        ).order_by('-created_at')
        for item in documentation_links:
            # check landing section
            landing_sections = []
            if item.landing_sections:
                if isinstance(item.landing_sections, str):
                    landing_sections = [item.landing_sections]
                else:
                    landing_sections = list(item.landing_sections)
            
            # Match latest-news, or legacy prefixes
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
                'created_at': item.created_at,
            })

    # Fetch hackathon rounds
    rounds = reg.hackathon.get_rounds() if reg.hackathon else []
    active_round = reg.hackathon.active_round if reg.hackathon else None

    return render(request, 'team/announcements.html', {
        'reg': reg,
        'has_unread': has_unread,
        'news_items': news_items,
        'rounds': rounds,
        'active_round': active_round,
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

    from events.models import CreativeMaterial
    creative_queryset = CreativeMaterial.objects.filter(
        hackathon=reg.hackathon,
        is_published=True,
        is_suspended=False,
    )
    
    gallery_prefix = '[Gallery]'
    gallery_items = []
    for asset in creative_queryset.order_by('-uploaded_at'):
        landing_sections = []
        if asset.landing_sections:
            if isinstance(asset.landing_sections, str):
                landing_sections = [asset.landing_sections]
            else:
                landing_sections = list(asset.landing_sections)
        is_match = 'gallery' in landing_sections or (asset.title or '').startswith(gallery_prefix)
        if is_match:
            gallery_items.append(asset)

    return render(request, 'team/memories.html', {
        'reg': reg,
        'creatives': gallery_items[:12],
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

    from features.models import Podcast
    podcast_queryset = Podcast.objects.filter(
        hackathon=reg.hackathon,
        is_published=True,
    )
    
    podcasts = []
    for p in podcast_queryset.order_by('-created_at'):
        landing_sections = []
        if p.landing_sections:
            if isinstance(p.landing_sections, str):
                landing_sections = [p.landing_sections]
            else:
                landing_sections = list(p.landing_sections)
        is_match = 'podcasts' in landing_sections or (p.problem_statement_id is None)
        if is_match:
            podcasts.append(p)

    return render(request, 'team/media.html', {
        'reg': reg,
        'podcasts': podcasts[:12],
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


@login_required(login_url='/team/login/')
@require_POST
def team_resubmit_registration(request):
    """Resubmit a team registration that was rejected by the SPOC."""
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        return redirect('team_dashboard')

    if reg.status != 'rejected':
        messages.error(request, 'Only rejected registrations can be resubmitted.')
        return redirect('team_dashboard')

    if reg.hackathon.registration_close and timezone.localdate() > reg.hackathon.registration_close:
        messages.error(request, 'Registration deadline has passed. You cannot resubmit now.')
        return redirect('team_dashboard')

    reg.status = 'pending'
    reg.rejection_note = ''  # clear the old rejection reason
    reg.save()

    # Create TeamNotification
    from .models import TeamNotification
    TeamNotification.objects.create(
        team_leader=request.user,
        registration=reg,
        notif_type='system',
        title='Registration Resubmitted',
        body='Your team registration has been resubmitted to the SPOC for review.',
    )

    messages.success(request, 'Registration resubmitted successfully! The SPOC will review your application.')
    return redirect('team_dashboard')


@login_required(login_url='/team/login/')
@require_POST
def team_request_modification(request):
    """Submit a modification request to the SPOC (when registration is approved/locked)."""
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    from spoc.spoc.models import SpocModificationDecision
    from accounts.models import SpocInstitutionMap

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        return redirect('team_dashboard')

    requested_change = request.POST.get('requested_change', '').strip()
    reason = request.POST.get('reason', '').strip()

    if not requested_change or not reason:
        messages.error(request, 'Requested changes and reason are both required.')
        return redirect('team_details')

    # Find the SPOC mapping for their institution
    mapping = SpocInstitutionMap.objects.filter(institution=reg.institution).select_related('spoc').first()
    if not mapping or not mapping.spoc:
        messages.error(request, 'No SPOC profile mapped to your college. Please contact support.')
        return redirect('team_details')

    # Check for existing pending or submitted request
    existing = SpocModificationDecision.objects.filter(team_name=reg.team_name, status__in=['pending', 'submitted']).exists()
    if existing:
        messages.warning(request, 'You already have a pending or submitted modification request.')
        return redirect('team_details')

    # Create modification request
    SpocModificationDecision.objects.create(
        spoc=mapping.spoc,
        team_name=reg.team_name,
        requested_change=requested_change,
        reason=reason,
        status='pending',
    )

    # Notify SPOC
    from spoc.spoc.models import SpocNotification
    SpocNotification.objects.create(
        spoc=mapping.spoc,
        notif_type='mod_req',
        title='New Modification Request',
        body=f"Team '{reg.team_name}' has requested a registration modification: {requested_change[:100]}",
        link="/spoc/modifications/",
    )

    messages.success(request, 'Modification request submitted successfully. The SPOC has been notified.')
    return redirect('team_details')


@login_required(login_url='/team/login/')
@require_POST
def team_complete_modification(request):
    """Finish editing and lock details again, requesting final approval from SPOC."""
    if not _team_required(request):
        return redirect('team_login')

    from features.models import TeamRegistration
    from spoc.spoc.models import SpocModificationDecision

    reg = TeamRegistration.objects.filter(team_leader=request.user).order_by('-registered_at').first()
    if not reg:
        return redirect('team_dashboard')

    mods = SpocModificationDecision.objects.filter(team_name=reg.team_name, status='approved')
    if mods.exists():
        mods.update(status='submitted')
        
        # Notify SPOC
        from accounts.models import SpocInstitutionMap
        from spoc.spoc.models import SpocNotification
        mapping = SpocInstitutionMap.objects.filter(institution=reg.institution).select_related('spoc').first()
        if mapping and mapping.spoc:
            SpocNotification.objects.create(
                spoc=mapping.spoc,
                notif_type='mod_req',
                title='Modifications Submitted for Approval',
                body=f"Team '{reg.team_name}' has locked their edits and submitted modifications for your final review and approval.",
                link="/spoc/modifications/",
            )
        messages.success(request, 'Modifications submitted successfully. Your team details are locked pending SPOC final approval.')
    else:
        messages.error(request, 'No active approved modification request found.')

    return redirect('team_details')
