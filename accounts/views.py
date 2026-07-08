"""
accounts/views.py

Imports updated to pull Hackathon, ProblemStatement, CreativeMaterial
from the events app, and Team, Venue from the features app.
All view logic and URL names are UNCHANGED.
"""

import json
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail, EmailMultiAlternatives
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings
import random

# accounts-app models
from .models import (
    User, Role, SuperadminProfile, AdminProfile,
    SpocProfile, MentorProfile, JuryProfile, ExpertProfile, ExecutiveProfile,
    TeamleadProfile, OTPVerification, AdminPermission, AuditLog, Institution,
    SpocInstitutionMap,
    InAppMessage,
)

# cross-app imports
from events.models import Hackathon, HackathonDomain, ProblemStatement, CreativeMaterial
from features.models import Team, Venue, TeamRegistration, TeamEvaluationAssignment
from jury.models import EvaluatorProfile, TeamEvaluation
from .rendering import render_route

LANDING_SECTION_CHOICES = [
    ('latest-news', 'Latest News'),
    ('podcasts', 'Podcasts'),
    ('gallery', 'Gallery'),
    ('testimonials', 'Testimonials'),
    ('voice-of-inspiration', 'Voice of Inspiration'),
]

def _sync_portal_username_to_email(user):
    email_value = (getattr(user, 'email', '') or '').strip().lower()
    current_username = (getattr(user, 'username', '') or '').strip()

    if not email_value or current_username.lower() == email_value:
        return user

    is_portal_user = hasattr(user, 'spoc_profile') or hasattr(user, 'mentor_profile')
    if not is_portal_user:
        return user

    username_taken = User.objects.filter(username__iexact=email_value).exclude(pk=user.pk).exists()
    if username_taken:
        return user

    user.username = email_value
    user.save(update_fields=['username'])
    return user


def _find_login_user(identifier, password=None):
    identifier = (identifier or '').strip()
    if not identifier:
        return None

    candidates = []
    if '@' in identifier:
        candidates = list(
            User.objects.filter(email__iexact=identifier)
            .order_by('-is_active', '-date_joined', '-id')
        )
        username_match = User.objects.filter(username__iexact=identifier).first()
        if username_match and username_match not in candidates:
            candidates.insert(0, username_match)
    else:
        username_match = User.objects.filter(username__iexact=identifier).first()
        if username_match:
            candidates.append(username_match)
        candidates.extend(
            User.objects.filter(email__iexact=identifier)
            .exclude(pk=getattr(username_match, 'pk', None))
            .order_by('-is_active', '-date_joined', '-id')
        )

    if not candidates:
        return None

    if password:
        for candidate in candidates:
            if candidate.check_password(password):
                return _sync_portal_username_to_email(candidate)

    user_obj = candidates[0]
    return _sync_portal_username_to_email(user_obj)


def _unique_admin_permissions():
    seen_labels = set()
    unique_permissions = []

    for permission in AdminPermission.objects.order_by('name', 'id'):
        label_key = " ".join((permission.name or "").split()).casefold()
        label_key = (
            label_key.replace(" management", " mgt")
            .replace(" & ", " and ")
        )
        dedupe_key = label_key or permission.codename
        if dedupe_key in seen_labels:
            continue
        seen_labels.add(dedupe_key)
        unique_permissions.append(permission)

    return unique_permissions


# ─────────────────────────── AUTH ───────────────────────────

def login_view(request):
    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip()
        password = request.POST.get('password', '').strip()

        if not identifier or not password:
            messages.error(request, 'Please enter both username/email and password.')
            return render(request, 'accounts/login.html')

        user_obj = _find_login_user(identifier, password)

        if not user_obj:
            messages.error(request, 'No account found with that username or email.')
            return render(request, 'accounts/login.html', {'identifier': identifier})

        user = authenticate(request, username=user_obj.username, password=password)

        if user is None:
            messages.error(request, 'Incorrect password. Please try again.')
            return render(request, 'accounts/login.html', {'identifier': identifier})

        if not user.is_active:
            messages.error(request, 'Your account has been deactivated. Please contact the administrator.')
            return render(request, 'accounts/login.html', {'identifier': identifier})

        if user.is_superuser or (user.role and user.role.name == 'Super Admin'):
            OTPVerification.objects.filter(user=user).delete()
            otp_code = str(random.randint(1000, 9999))
            OTPVerification.objects.create(user=user, code=otp_code)
            request.session['pending_2fa_user_id'] = user.id

            try:
                email_subject = 'Your HackNexus Super Admin OTP'
                email_body_plain = (
                    f'Hello {user.get_full_name() or user.username},\n\n'
                    f'Your 4-digit verification code is: {otp_code}\n\n'
                    f'This code is valid for 10 minutes. Do not share it with anyone.\n\n'
                    f'— HackNexus Team'
                )
                email_body_html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #fff; border-radius: 12px; border: 1px solid #e5e7eb;">
                    <h2 style="color: #ea580c; margin-bottom: 8px;">HackNexus 2FA Verification</h2>
                    <p style="color: #374151;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
                    <p style="color: #374151;">Use the code below to complete your Super Admin login:</p>
                    <div style="background: #fff7ed; border: 2px dashed #ea580c; border-radius: 8px; padding: 24px; text-align: center; margin: 24px 0;">
                        <span style="font-size: 36px; font-weight: 900; letter-spacing: 12px; color: #ea580c;">{otp_code}</span>
                    </div>
                    <p style="color: #6b7280; font-size: 13px;">This code expires in <strong>10 minutes</strong>.</p>
                    <p style="color: #6b7280; font-size: 13px;">Do not share this code with anyone.</p>
                    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
                    <p style="color: #9ca3af; font-size: 12px;">If you did not request this, please ignore this email.</p>
                </div>
                """

                # send_mail(
                #     subject=email_subject,
                #     message=email_message,
                #     from_email=settings.EMAIL_HOST_USER,
                #     recipient_list=[user.email],
                #     fail_silently=False,
                # )

                msg = EmailMultiAlternatives(
                    subject=email_subject,
                    body=email_body_plain,
                    from_email=settings.EMAIL_HOST_USER,
                    to=[user.email],
                )
                msg.attach_alternative(email_body_html, "text/html")
                msg.send(fail_silently=False)
                messages.info(request, f'A 4-digit verification code has been sent to {user.email}.')
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'OTP email failed for {user.email}: {e}')
                messages.error(request, f'Could not send OTP email. Error: {e}.')

            return redirect('verify_otp')

        login(request, user)
        return _redirect_by_role(user)

    return render(request, 'accounts/login.html')


def _redirect_by_role(user):
    if user.is_superuser or (user.role and user.role.name == 'Super Admin'):
        return redirect('superadmin_dashboard')
    elif hasattr(user, 'admin_profile'):
        return redirect('admin_dashboard')
    elif hasattr(user, 'executive_profile'):
        return redirect('executive_dashboard')
    elif hasattr(user, 'spoc_profile'):
        return redirect('spoc_dashboard')
    elif hasattr(user, 'mentor_profile'):
        return redirect('mentor_dashboard')
    elif hasattr(user, 'teamlead_profile'):
        return redirect('team_dashboard')
    elif hasattr(user, 'jury_profile'):
        return redirect('jury_dashboard')
    elif hasattr(user, 'expert_profile'):
        return redirect('jury_dashboard')
    else:
        return redirect('login')


def _exec_guard(request):
    if not hasattr(request.user, 'executive_profile'):
        messages.error(request, 'Executive access required.')
        return None, redirect('login')
    return request.user.executive_profile, None


def _completion_checklist(user):
    missing = []

    if not (user.first_name or '').strip():
        missing.append('first name')
    if not (user.last_name or '').strip():
        missing.append('last name')
    if not (user.email or '').strip():
        missing.append('email')
    if not (user.phone_number or '').strip():
        missing.append('phone number')
    if not user.date_of_birth:
        missing.append('date of birth')
    if not (user.gender or '').strip():
        missing.append('gender')

    if hasattr(user, 'admin_profile'):
        if not user.admin_profile.permissions.exists():
            missing.append('assigned permissions')
    elif hasattr(user, 'executive_profile'):
        if not user.executive_profile.assigned_admin_id:
            missing.append('assigned admin')
    elif hasattr(user, 'spoc_profile'):
        if not (user.spoc_profile.institution_name or '').strip():
            missing.append('institution name')
        if not user.profile_image:
            missing.append('profile photo')
        if not user.id_proof:
            missing.append('ID proof')

        institution_map = (
            SpocInstitutionMap.objects
            .filter(spoc=user.spoc_profile)
            .select_related('institution__extended')
            .first()
        )
        institution = institution_map.institution if institution_map else None
        extended = getattr(institution, 'extended', None) if institution else None

        if not institution:
            missing.append('institution mapping')
        else:
            if not (institution.location or '').strip():
                missing.append('institution location')
            if not extended:
                missing.extend([
                    'institution email',
                    'institution address',
                    'institution head name',
                    'institution head email',
                    'institution contact',
                    'institution logo',
                ])
            else:
                if not (extended.email or '').strip():
                    missing.append('institution email')
                if not (extended.address or '').strip():
                    missing.append('institution address')
                if not (extended.institution_head_name or '').strip():
                    missing.append('institution head name')
                if not (extended.institution_head_email or '').strip():
                    missing.append('institution head email')
                if not (extended.contact_no or '').strip():
                    missing.append('institution contact')
                if not extended.logo:
                    missing.append('institution logo')
    elif hasattr(user, 'mentor_profile'):
        if not (user.mentor_profile.expertise or '').strip():
            missing.append('expertise')
    elif hasattr(user, 'jury_profile'):
        if not (user.jury_profile.domain or '').strip():
            missing.append('domain')
    elif hasattr(user, 'expert_profile'):
        if not (user.expert_profile.domain or '').strip():
            missing.append('domain')

    return missing


def _user_completion_status(user):
    return 'completed' if not _completion_checklist(user) else 'pending'


def _build_view_user_sections(user):
    missing_set = set(_completion_checklist(user))
    sections = []
    tracked_total = 0
    tracked_completed = 0

    def _display(value, fallback='Not provided'):
        if value is None:
            return fallback
        if hasattr(value, 'strftime'):
            try:
                return value.strftime('%d %b %Y')
            except Exception:
                return str(value)
        if isinstance(value, bool):
            return 'Yes' if value else 'No'
        text = str(value).strip()
        return text or fallback

    def _file_name(file_value):
        return str(file_value).replace('\\', '/').split('/')[-1]

    def _push(section_title, label, value=None, status_key=None, file_value=None, fallback='Not provided'):
        nonlocal tracked_total, tracked_completed

        is_complete = True
        if status_key:
            is_complete = status_key not in missing_set
            tracked_total += 1
            if is_complete:
                tracked_completed += 1
        else:
            is_complete = bool(file_value or (str(value).strip() if value is not None else ''))

        entry = {
            'label': label,
            'value': _file_name(file_value) if file_value else _display(value, fallback=fallback),
            'is_complete': is_complete,
            'status_text': 'Complete' if is_complete else 'Pending',
            'file_url': getattr(file_value, 'url', '') if file_value else '',
        }

        section = next((item for item in sections if item['title'] == section_title), None)
        if section is None:
            section = {'title': section_title, 'fields': []}
            sections.append(section)
        section['fields'].append(entry)

    _push('Personal Details', 'First Name', user.first_name, 'first name')
    _push('Personal Details', 'Last Name', user.last_name, 'last name')
    _push('Personal Details', 'Username', user.username)
    _push('Personal Details', 'Email', user.email, 'email')
    _push('Personal Details', 'Phone Number', user.phone_number, 'phone number')
    _push('Personal Details', 'Date of Birth', user.date_of_birth, 'date of birth')
    _push('Personal Details', 'Gender', user.gender, 'gender')
    _push('Personal Details', 'Profile Photo', status_key='profile photo', file_value=user.profile_image)
    _push('Personal Details', 'ID Proof', status_key='ID proof', file_value=user.id_proof)
    _push('Personal Details', 'Email Verified', 'Verified' if user.is_verified else 'Not verified')

    if hasattr(user, 'admin_profile'):
        permissions = list(user.admin_profile.permissions.values_list('name', flat=True))
        _push('Role Details', 'Role', 'Admin')
        _push('Role Details', 'Assigned Permissions', ', '.join(permissions), 'assigned permissions')
    elif hasattr(user, 'executive_profile'):
        assigned_admin = user.executive_profile.assigned_admin
        assigned_admin_name = (
            assigned_admin.user.get_full_name() or assigned_admin.user.username
        ) if assigned_admin else ''
        _push('Role Details', 'Role', 'Executive')
        _push('Role Details', 'Assigned Admin', assigned_admin_name, 'assigned admin')
    elif hasattr(user, 'spoc_profile'):
        institution_map = (
            SpocInstitutionMap.objects
            .filter(spoc=user.spoc_profile)
            .select_related('institution__extended', 'spoc__approved_by__user')
            .first()
        )
        institution = institution_map.institution if institution_map else None
        extended = getattr(institution, 'extended', None) if institution else None
        approved_by = getattr(user.spoc_profile, 'approved_by', None)

        _push('Role Details', 'Role', 'SPOC')
        _push('Role Details', 'Institution Name', user.spoc_profile.institution_name, 'institution name')
        _push('Role Details', 'Approved By', (approved_by.user.get_full_name() or approved_by.user.username) if approved_by else '')
        _push('Institution Details', 'Institution Mapping', institution.name if institution else '', 'institution mapping')
        _push('Institution Details', 'Institution Location', institution.location if institution else '', 'institution location')
        _push('Institution Details', 'Institution Email', extended.email if extended else '', 'institution email')
        _push('Institution Details', 'Institution Address', extended.address if extended else '', 'institution address')
        _push('Institution Details', 'Institution Head Name', extended.institution_head_name if extended else '', 'institution head name')
        _push('Institution Details', 'Institution Head Email', extended.institution_head_email if extended else '', 'institution head email')
        _push('Institution Details', 'Institution Contact', extended.contact_no if extended else '', 'institution contact')
        _push('Institution Details', 'Institution Logo', status_key='institution logo', file_value=getattr(extended, 'logo', None))
    elif hasattr(user, 'mentor_profile'):
        _push('Role Details', 'Role', 'Mentor')
        _push('Role Details', 'Expertise', user.mentor_profile.expertise, 'expertise')
    elif hasattr(user, 'jury_profile'):
        evaluator_profile = getattr(user, 'evaluator_profile', None)
        _push('Role Details', 'Role', 'Jury')
        _push('Role Details', 'Domain', user.jury_profile.domain, 'domain')
        if evaluator_profile:
            _push('Evaluator Profile', 'Organization', evaluator_profile.organization)
            _push('Evaluator Profile', 'Designation', evaluator_profile.designation)
            _push('Evaluator Profile', 'Bio', evaluator_profile.bio)
            _push('Evaluator Profile', 'Testimonial Video', file_value=evaluator_profile.testimonial_video)
            _push('Payout Details', 'Bank Account Holder', evaluator_profile.bank_account_holder)
            _push('Payout Details', 'Bank Name', evaluator_profile.bank_name)
            _push('Payout Details', 'Branch Name', evaluator_profile.branch_name)
            _push('Payout Details', 'Account Number', evaluator_profile.account_number)
            _push('Payout Details', 'IFSC Code', evaluator_profile.ifsc_code)
            _push('Payout Details', 'UPI ID', evaluator_profile.upi_id)
            _push('Payout Details', 'Cancelled Cheque', file_value=evaluator_profile.cancelled_cheque)
    elif hasattr(user, 'expert_profile'):
        evaluator_profile = getattr(user, 'evaluator_profile', None)
        _push('Role Details', 'Role', 'Expert')
        _push('Role Details', 'Domain', user.expert_profile.domain, 'domain')
        if evaluator_profile:
            _push('Evaluator Profile', 'Organization', evaluator_profile.organization)
            _push('Evaluator Profile', 'Designation', evaluator_profile.designation)
            _push('Evaluator Profile', 'Bio', evaluator_profile.bio)
            _push('Evaluator Profile', 'Testimonial Video', file_value=evaluator_profile.testimonial_video)
            _push('Payout Details', 'Bank Account Holder', evaluator_profile.bank_account_holder)
            _push('Payout Details', 'Bank Name', evaluator_profile.bank_name)
            _push('Payout Details', 'Branch Name', evaluator_profile.branch_name)
            _push('Payout Details', 'Account Number', evaluator_profile.account_number)
            _push('Payout Details', 'IFSC Code', evaluator_profile.ifsc_code)
            _push('Payout Details', 'UPI ID', evaluator_profile.upi_id)
            _push('Payout Details', 'Cancelled Cheque', file_value=evaluator_profile.cancelled_cheque)

    return {
        'sections': sections,
        'tracked_total': tracked_total,
        'tracked_completed': tracked_completed,
        'tracked_pending': max(tracked_total - tracked_completed, 0),
        'missing_fields': sorted(missing_set),
    }


def _build_executive_feature_cards(exec_profile):
    from features.views import ADMIN_PERMISSION_META

    assigned_codenames = set()
    if exec_profile.assigned_admin_id:
        assigned_codenames = set(
            exec_profile.assigned_admin.permissions.values_list('codename', flat=True)
        )

    colours = [
        'fc-blue', 'fc-indigo', 'fc-violet', 'fc-emerald', 'fc-teal',
        'fc-orange', 'fc-rose', 'fc-amber', 'fc-cyan', 'fc-sky',
    ]

    feature_cards = []
    seen_urls = set()
    colour_idx = 0
    for codename, meta in ADMIN_PERMISSION_META.items():
        url_key = meta.get('url_name', '')
        if url_key in seen_urls:
            for card in feature_cards:
                if card['url_name'] == url_key:
                    card['is_enabled'] = card['is_enabled'] or (codename in assigned_codenames)
                    if codename in assigned_codenames:
                        card['codenames'].append(codename)
            continue
        seen_urls.add(url_key)
        feature_cards.append({
            'codename': codename,
            'codenames': [codename],
            'label': meta.get('label', codename),
            'description': meta.get('description', ''),
            'icon': meta.get('icon', 'grid-outline'),
            'url_name': url_key,
            'is_enabled': codename in assigned_codenames,
            'colour': colours[colour_idx % len(colours)],
        })
        colour_idx += 1

    return feature_cards, assigned_codenames


def logout_view(request):
    logout(request)
    return redirect('landing_page')


@never_cache
def verify_otp(request):
    user_id = request.session.get('pending_2fa_user_id')
    if not user_id:
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    if request.method == 'POST':
        otp_code = request.POST.get('otp', '').strip()
        otp_record = OTPVerification.objects.filter(
            user=user, code=otp_code, is_verified=False
        ).order_by('-created_at').first()

        if otp_record and not otp_record.is_expired():
            otp_record.is_verified = True
            otp_record.save()
            login(request, user)
            request.session.pop('pending_2fa_user_id', None)
            return _redirect_by_role(user)
        else:
            messages.error(request, 'Invalid or expired verification code.')

    return render(request, 'accounts/verify_otp.html', {'email': user.email})


# ─────────────────────────── DASHBOARD ───────────────────────────

@login_required(login_url="/accounts/")
@never_cache
def superadmin_dashboard(request):
    is_super = request.user.is_superuser or (request.user.role and request.user.role.name == 'Super Admin')

    if not is_super:
        messages.error(request, "Restricted area. Superadmin access required.")
        return redirect('login')

    SuperadminProfile.objects.get_or_create(user=request.user)

    if not hasattr(request.user, 'superadmin_profile'):
        messages.warning(request, "SuperadminProfile missing.")
        return redirect('login')

    tab = request.GET.get('tab', 'overview')
    roles = Role.objects.all()
    live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()

    context = {
        'tab': tab,
        'roles': roles,
        'admin_role': Role.objects.filter(name='Admin').first(),
        'live_hackathon': live_hackathon,
        'all_permissions': _unique_admin_permissions(),
        'administrators': AdminProfile.objects.all().select_related('user'),
        'other_roles_list': Role.objects.filter(name__in=['Jury', 'Expert', 'Mentor', 'SPOC', 'Teamlead', 'Team Lead']),
        'active_nav': 'dashboard',
        'landing_section_choices': LANDING_SECTION_CHOICES,
    }

    if tab in ['overview', 'analytics']:
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        last_30_days = now - timedelta(days=30)

        def get_stats(model, date_field='created_at'):
            total = model.objects.count()
            new_month = model.objects.filter(**{f"{date_field}__gte": start_of_month}).count()
            new_week = model.objects.filter(**{f"{date_field}__gte": start_of_week}).count()
            new_today = model.objects.filter(**{f"{date_field}__gte": start_of_today}).count()
            return total, new_month, new_week, new_today

        def month_key_offset(year, month, offset):
            total_months = (year * 12 + (month - 1)) + offset
            return total_months // 12, (total_months % 12) + 1

        context['events_total'], context['events_new_month'], _, _ = get_stats(Hackathon)
        context['admins_total'] = AdminProfile.objects.count()
        context['admins_active'] = AdminProfile.objects.filter(
            user__last_login__gte=now - timedelta(days=1)
        ).count()
        context['jury_count'] = JuryProfile.objects.count()
        context['expert_count'] = ExpertProfile.objects.count()
        context['expert_jury_total'] = context['jury_count'] + context['expert_count']
        context['colleges_total'] = Institution.objects.count()
        context['colleges_new_week'] = SpocProfile.objects.exclude(institution_name__isnull=True).exclude(institution_name__exact='').count()
        context['teams_total'] = Team.objects.count()
        context['teams_new_today'] = Team.objects.filter(created_at__gte=start_of_today).count()
        context['execs_total'] = ExecutiveProfile.objects.count()
        context['ps_total'], _, _, _ = get_stats(ProblemStatement)
        context['venues_total'] = Venue.objects.count()
        context['published_ps_total'] = ProblemStatement.objects.filter(is_published=True, is_suspended=False).count()
        context['published_creatives_total'] = CreativeMaterial.objects.filter(is_published=True, is_suspended=False).count()
        context['pending_registrations'] = TeamRegistration.objects.filter(status='pending').count()
        context['approved_registrations'] = TeamRegistration.objects.filter(status='approved').count()
        context['rejected_registrations'] = TeamRegistration.objects.filter(status='rejected').count()
        total_registrations = TeamRegistration.objects.count()
        context['total_registrations'] = total_registrations
        context['approval_rate'] = round((context['approved_registrations'] / total_registrations) * 100, 1) if total_registrations else 0
        total_assignments = TeamEvaluationAssignment.objects.count()
        assigned_assignments = TeamEvaluationAssignment.objects.filter(status='Assigned').count()
        context['evaluation_assignment_rate'] = round((assigned_assignments / total_assignments) * 100, 1) if total_assignments else 0
        avg_score = TeamEvaluation.objects.aggregate(avg=Avg('score'))['avg']
        context['avg_evaluation_score'] = round(float(avg_score), 1) if avg_score is not None else 0
        context['active_users_30d'] = User.objects.filter(last_login__gte=last_30_days).count()

        activities = []
        for log in AuditLog.objects.select_related('actor').order_by('-created_at')[:6]:
            actor_label = (
                log.actor.get_full_name().strip()
                if log.actor and log.actor.get_full_name().strip()
                else log.actor_username or 'System'
            )
            activities.append({
                "text": f"{actor_label} {log.get_action_display().lower()}d {log.object_repr or log.model_name}",
                "time": timezone.localtime(log.created_at).strftime("%d %b %Y, %I:%M %p"),
                "icon": "pulse" if log.action == 'update' else ("add-circle" if log.action == 'create' else "trash"),
            })
        if not activities:
            for h in Hackathon.objects.all().order_by('-created_at')[:3]:
                activities.append({
                    "text": f"Event '{h.name}' configured",
                    "time": timezone.localtime(h.created_at).strftime("%d %b %Y, %I:%M %p"),
                    "icon": "calendar",
                })
        context['recent_activity'] = activities

        status_counts = Hackathon.objects.values('status').annotate(count=Count('id'))
        context['status_chart_data'] = json.dumps({
            'labels': [s['status'] for s in status_counts],
            'data': [s['count'] for s in status_counts]
        })
        domain_counts = ProblemStatement.objects.values('domain').annotate(count=Count('id'))
        context['domain_chart_data'] = json.dumps({
            'labels': [d['domain'] or 'Other' for d in domain_counts],
            'data': [d['count'] for d in domain_counts]
        })
        registration_counts = TeamRegistration.objects.values('status').annotate(count=Count('id')).order_by('status')
        context['registration_chart_data'] = json.dumps({
            'labels': [r['status'].replace('_', ' ').title() for r in registration_counts],
            'data': [r['count'] for r in registration_counts],
        })
        role_counts = User.objects.exclude(role__isnull=True).values('role__name').annotate(count=Count('id')).order_by('-count')
        context['role_chart_data'] = json.dumps({
            'labels': [r['role__name'] for r in role_counts],
            'data': [r['count'] for r in role_counts],
        })

        growth_labels = []
        growth_data = []
        for offset in range(-5, 1):
            year, month = month_key_offset(now.year, now.month, offset)
            growth_labels.append(f"{timezone.datetime(year, month, 1).strftime('%b %Y')}")
            growth_data.append(User.objects.filter(date_joined__year=year, date_joined__month=month).count())
        context['growth_chart_data'] = json.dumps({
            'labels': growth_labels,
            'data': growth_data,
        })

        top_domains = list(
            ProblemStatement.objects.exclude(domain__isnull=True)
            .exclude(domain__exact='')
            .values('domain')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )
        context['top_domains'] = top_domains

        live_event_snapshots = []
        for hackathon in Hackathon.objects.order_by('-updated_at')[:3]:
            live_event_snapshots.append({
                'name': hackathon.name,
                'status': hackathon.status,
                'teams': Team.objects.filter(hackathon=hackathon).count(),
                'problems': ProblemStatement.objects.filter(hackathon=hackathon, is_suspended=False).count(),
                'venues': Venue.objects.filter(hackathon=hackathon).count(),
            })
        context['live_event_snapshots'] = live_event_snapshots

    elif tab == 'events':
        query = request.GET.get('search_events', '')
        h_list = Hackathon.objects.all().order_by('-created_at')
        if query:
            h_list = h_list.filter(Q(name__icontains=query) | Q(organization_name__icontains=query))

        paginator = Paginator(h_list, 10)
        page = request.GET.get('page')
        try:
            context['hackathons_list'] = paginator.page(page)
        except PageNotAnInteger:
            context['hackathons_list'] = paginator.page(1)
        except EmptyPage:
            context['hackathons_list'] = paginator.page(paginator.num_pages)
        context['search_events'] = query

    elif tab == 'admin_mgt':
        query = request.GET.get('search_admins', '')
        admins = (
            AdminProfile.objects.all()
            .select_related('user')
            .prefetch_related('permissions')
            .order_by('-user__date_joined')
        )
        if query:
            admins = admins.filter(
                Q(user__username__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query)
            )
        paginator = Paginator(admins, 10)
        page = request.GET.get('page')
        try:
            context['admins_list'] = paginator.page(page)
        except PageNotAnInteger:
            context['admins_list'] = paginator.page(1)
        except EmptyPage:
            context['admins_list'] = paginator.page(paginator.num_pages)
        for admin in context['admins_list']:
            admin.permission_ids = list(admin.permissions.values_list('id', flat=True))
            admin.editable_permissions = [
                {
                    'id': perm.id,
                    'name': perm.name,
                    'description': perm.description,
                    'checked_attr': 'checked' if perm.id in admin.permission_ids else '',
                }
                for perm in context['all_permissions']
            ]
        context['search_admins'] = query

    elif tab == 'exec_mgt':
        query = request.GET.get('search_execs', '')
        execs = ExecutiveProfile.objects.all().select_related('user', 'assigned_admin__user').order_by('-user__date_joined')
        if query:
            execs = execs.filter(
                Q(user__username__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query)
            )
        paginator = Paginator(execs, 10)
        page = request.GET.get('page')
        try:
            context['executives_list'] = paginator.page(page)
        except PageNotAnInteger:
            context['executives_list'] = paginator.page(1)
        except EmptyPage:
            context['executives_list'] = paginator.page(paginator.num_pages)
        context['search_execs'] = query

    elif tab == 'user_mgt':
        query = request.GET.get('search_users', '')
        role_filter = request.GET.get('role_filter', '')
        other_roles = ['Jury', 'Mentor', 'SPOC', 'Expert', 'Teamlead', 'Team Lead']
        users = User.objects.filter(role__name__in=other_roles).order_by('-date_joined')
        
        if role_filter:
            users = users.filter(role__name=role_filter)
        if query:
            users = users.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query)
            )
            
        paginator = Paginator(users, 20)
        page = request.GET.get('page')
        try:
            context['users_list'] = paginator.page(page)
        except PageNotAnInteger:
            context['users_list'] = paginator.page(1)
        except EmptyPage:
            context['users_list'] = paginator.page(paginator.num_pages)
        context['search_users'] = query
        context['role_filter'] = role_filter

    elif tab == 'evaluator_payouts':
        query = request.GET.get('search_evaluators', '')
        bank_profiles = EvaluatorProfile.objects.select_related('user', 'user__role').order_by('-updated_at')
        if query:
            bank_profiles = bank_profiles.filter(
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(user__email__icontains=query) |
                Q(bank_name__icontains=query) |
                Q(ifsc_code__icontains=query)
            )
        context['bank_profiles'] = bank_profiles
        context['search_evaluators'] = query

    elif tab == 'problem_statements':
        query = request.GET.get('search_ps', '')
        ps_list = ProblemStatement.objects.filter(is_suspended=False).order_by('-created_at')
        if query:
            ps_list = ps_list.filter(Q(title__icontains=query) | Q(domain__icontains=query))
        paginator = Paginator(ps_list, 10)
        page = request.GET.get('page')
        try:
            context['problem_statements'] = paginator.page(page)
        except PageNotAnInteger:
            context['problem_statements'] = paginator.page(1)
        except EmptyPage:
            context['problem_statements'] = paginator.page(paginator.num_pages)
        context['search_ps'] = query
        context['hackathons'] = Hackathon.objects.filter(status='Live').order_by('-created_at')
        context['DOMAIN_CHOICES'] = [
            "Agriculture", "Healthcare", "Animal Resource", "Education"
        ]
        # Override with dynamic domains if configured on any live hackathon
        live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
        if live_hackathon:
            dynamic_domains = list(
                HackathonDomain.objects.filter(hackathon=live_hackathon)
                .order_by('display_order', 'name')
                .values_list('name', flat=True)
            )
            if dynamic_domains:
                context['DOMAIN_CHOICES'] = dynamic_domains

    elif tab == 'creatives':
        query = request.GET.get('search_creatives', '')
        creatives = CreativeMaterial.objects.all().select_related('hackathon').order_by('-uploaded_at')
        if query:
            creatives = creatives.filter(
                Q(title__icontains=query) | Q(hackathon__name__icontains=query)
            )
        context['creatives_list'] = creatives
        context['hackathons'] = Hackathon.objects.filter(status='Live').order_by('-created_at')
        context['search_creatives'] = query

    return render(request, 'accounts/superadmin_dashboard.html', context)


@login_required(login_url="/accounts/")
@never_cache
def admin_dashboard(request):
    if not hasattr(request.user, 'admin_profile'):
        messages.error(request, "Permission denied.")
        return render_route(request, '/accounts/dashboard/')

    from features.views import ADMIN_PERMISSION_META

    admin_prof = request.user.admin_profile
    assigned_codenames = set(
        admin_prof.permissions.all().values_list('codename', flat=True)
    )

    # Colour palette cycling across deduplicated feature cards
    CARD_COLOURS = [
        'fc-blue', 'fc-indigo', 'fc-violet', 'fc-emerald', 'fc-teal',
        'fc-orange', 'fc-rose', 'fc-amber', 'fc-cyan', 'fc-sky',
    ]

    # Build feature card list — deduplicated by url_name, each card knows
    # whether it is enabled and which colour to use.
    feature_cards = []
    seen_urls = set()
    colour_idx = 0
    for codename, meta in ADMIN_PERMISSION_META.items():
        url_key = meta.get('url_name', '')
        if url_key in seen_urls:
            # Two codenames share a URL → merge into the existing card
            for card in feature_cards:
                if card['url_name'] == url_key:
                    card['is_enabled'] = card['is_enabled'] or (codename in assigned_codenames)
                    if codename in assigned_codenames:
                        card['codenames'].append(codename)
            continue
        seen_urls.add(url_key)
        feature_cards.append({
            'codename': codename,
            'codenames': [codename],
            'label': meta.get('label', codename),
            'description': meta.get('description', ''),
            'icon': meta.get('icon', 'grid-outline'),
            'url_name': url_key,
            'is_enabled': codename in assigned_codenames,
            'colour': CARD_COLOURS[colour_idx % len(CARD_COLOURS)],
        })
        colour_idx += 1

    context = {
        'permissions': assigned_codenames,
        'feature_cards': feature_cards,
        'enabled_count': len([c for c in feature_cards if c['is_enabled']]),
        'admin_profile': admin_prof,
        'live_hackathon': Hackathon.objects.filter(status='Live').order_by('-updated_at').first(),
        'active_nav': 'admin_dashboard',
    }
    return render(request, 'accounts/admin_dashboard.html', context)


# ─────────────────────────── USER CREATION ───────────────────────────

def _send_welcome_email(user, plain_password, role_name):
    """Send a welcome email to a newly created user with their login credentials."""
    try:
        subject = f"Welcome to HackNexus — Your {role_name} Account Details"

        plain_body = (
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Your HackNexus account has been created by the Super Administrator.\n\n"
            f"Your login credentials:\n"
            f"  Username : {user.username}\n"
            f"  Password : {plain_password}\n"
            f"  Role     : {role_name}\n\n"
            f"Please log in at: https://hackathon.okcl.org/accounts/\n\n"
            f"We strongly recommend changing your password after your first login.\n\n"
            f"— HackNexus Team"
        )

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto;
                    padding: 32px; background: #ffffff; border-radius: 12px;
                    border: 1px solid #e5e7eb;">
            <h2 style="color: #ea580c; margin-bottom: 4px;">Welcome to HackNexus 🎉</h2>
            <p style="color: #6b7280; font-size: 13px; margin-top: 0;">
                Your <strong>{role_name}</strong> account has been created.
            </p>
            <hr style="border: none; border-top: 1px solid #f3f4f6; margin: 20px 0;">
            <p style="color: #374151;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
            <p style="color: #374151;">Here are your login credentials:</p>
            <div style="background: #fff7ed; border: 1px solid #fed7aa; border-radius: 10px;
                        padding: 20px; margin: 20px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #6b7280; font-size: 13px; width: 110px;">Username</td>
                        <td style="padding: 8px 0; font-weight: 800; color: #111827;
                                   font-family: monospace; font-size: 15px;">{user.username}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6b7280; font-size: 13px;">Password</td>
                        <td style="padding: 8px 0; font-weight: 800; color: #ea580c;
                                   font-family: monospace; font-size: 15px;">{plain_password}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6b7280; font-size: 13px;">Role</td>
                        <td style="padding: 8px 0; font-weight: 700; color: #374151;">{role_name}</td>
                    </tr>
                </table>
            </div>
            <p style="color: #374151; margin: 0;">
                <a href="https://hackathon.okcl.org/accounts/"
                   style="background: #ea580c; color: white; padding: 12px 24px;
                          border-radius: 8px; text-decoration: none; font-weight: 700;
                          display: inline-block; margin-top: 8px;">
                    Login to HackNexus →
                </a>
            </p>
            <hr style="border: none; border-top: 1px solid #f3f4f6; margin: 24px 0;">
            <p style="color: #9ca3af; font-size: 12px;">
                Please change your password after your first login for security.<br>
                If you did not expect this email, contact the system administrator.
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
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Welcome email failed for {user.email}: {e}')
        return False


@login_required(login_url="/accounts/")
@never_cache
def create_user(request):
    """Unified user creation. After creating, sends a welcome email with credentials."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        role_id = request.POST.get('role')
        assigned_admin_id = request.POST.get('assigned_admin_id')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        permission_ids = request.POST.getlist('permissions[]')
        redirect_tab = 'overview'

        try:
            role = Role.objects.get(id=role_id) if role_id and str(role_id).isdigit() else None
            is_active = request.POST.get('status') != 'draft'

            role_name = role.name if role else 'User'
            rn = role.name.lower() if role else ''

            # For Admin role: username MUST equal the email address so the
            # welcome email credential matches exactly what they type at login.
            if rn == 'admin' and email:
                username = email.strip().lower()

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_active=is_active
            )

            if role:
                if rn == 'admin':
                    admin_prof, _ = AdminProfile.objects.get_or_create(user=user)
                    if permission_ids:
                        admin_prof.permissions.set(permission_ids)
                    redirect_tab = 'admin_mgt'

                elif rn == 'executive':
                    exec_profile, _ = ExecutiveProfile.objects.get_or_create(user=user)
                    if assigned_admin_id:
                        admin_prof = AdminProfile.objects.filter(id=assigned_admin_id).first()
                        if admin_prof:
                            exec_profile.assigned_admin = admin_prof
                            exec_profile.save()
                    redirect_tab = 'exec_mgt'

                elif rn == 'super admin':
                    user.is_superuser = True
                    user.is_staff = True
                    user.save()
                    SuperadminProfile.objects.get_or_create(user=user)

                elif rn in ['spoc', 'mentor', 'jury', 'expert', 'teamlead']:
                    profile_map = {
                        'spoc': SpocProfile,
                        'mentor': MentorProfile,
                        'jury': JuryProfile,
                        'expert': ExpertProfile,
                        'teamlead': TeamleadProfile,
                    }
                    profile_map[rn].objects.get_or_create(user=user)
                    redirect_tab = 'user_mgt'

            email_sent = _send_welcome_email(user, password, role_name)
            status_msg = "Draft" if not is_active else "Onboarded"
            email_note = " Welcome email sent." if email_sent else " (Email delivery failed — check EMAIL settings.)"
            display_name = user.get_full_name() or user.username
            messages.success(request, f'{role_name} "{display_name}" {status_msg} successfully.{email_note}')

        except Exception as e:
            messages.error(request, f'Error creating user: {e}')

        return render_route(request, f'/accounts/dashboard/?tab={redirect_tab}')

    return render_route(request, '/accounts/dashboard/')


# ─────────────────────────── INLINE USER EDIT ───────────────────────────

@login_required(login_url="/accounts/")
@never_cache
def inline_edit_user(request, user_id):
    """Handles the inline edit form submissions from the dashboard tabs."""
    if not hasattr(request.user, 'superadmin_profile'):
        messages.error(request, "Permission denied.")
        return render_route(request, '/accounts/dashboard/')

    redirect_tab = request.POST.get('redirect_tab', 'user_mgt')

    try:
        target = User.objects.get(id=user_id)

        target.first_name = request.POST.get('first_name', target.first_name).strip()
        target.last_name = request.POST.get('last_name', target.last_name).strip()
        target.email = request.POST.get('email', target.email).strip()

        role_id = request.POST.get('role')
        if role_id and str(role_id).isdigit():
            try:
                target.role = Role.objects.get(id=role_id)
            except Role.DoesNotExist:
                pass

        new_password = request.POST.get('new_password', '').strip()
        if new_password:
            target.set_password(new_password)

        target.save()

        if hasattr(target, 'admin_profile'):
            perm_ids = request.POST.getlist('permissions[]')
            target.admin_profile.permissions.set(perm_ids)

        if hasattr(target, 'executive_profile'):
            admin_id = request.POST.get('assigned_admin_id')
            if admin_id and str(admin_id).isdigit():
                admin_prof = AdminProfile.objects.filter(id=admin_id).first()
                if admin_prof:
                    target.executive_profile.assigned_admin = admin_prof
                    target.executive_profile.save()

        messages.success(request, f'User "{target.username}" updated successfully.')

    except User.DoesNotExist:
        messages.error(request, "User not found.")

    return render_route(request, f'/accounts/dashboard/?tab={redirect_tab}')


# ─────────────────────────── USER MANAGEMENT ───────────────────────────

@login_required(login_url="/accounts/")
@never_cache
def view_user(request, user_id):
    if not (
        hasattr(request.user, 'superadmin_profile') or
        hasattr(request.user, 'admin_profile') or
        hasattr(request.user, 'executive_profile')
    ):
        messages.error(request, "Permission denied.")
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
        profile_info = None
        if hasattr(user, 'admin_profile'):
            profile_info = ("Admin", user.admin_profile)
        elif hasattr(user, 'executive_profile'):
            profile_info = ("Executive", user.executive_profile)
        elif hasattr(user, 'spoc_profile'):
            profile_info = ("SPOC", user.spoc_profile)
        elif hasattr(user, 'mentor_profile'):
            profile_info = ("Mentor", user.mentor_profile)
        elif hasattr(user, 'jury_profile'):
            profile_info = ("Jury", user.jury_profile)
        elif hasattr(user, 'expert_profile'):
            profile_info = ("Expert", user.expert_profile)

        detail_context = _build_view_user_sections(user)
        return render(request, 'accounts/view_user.html', {
            'target_user': user, 'profile_info': profile_info,
            'active_nav': 'users',
            'can_manage_user': hasattr(request.user, 'superadmin_profile'),
            **detail_context,
        })
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return render_route(request, '/accounts/dashboard/')


@login_required(login_url="/accounts/")
@never_cache
def edit_user(request, user_id):
    if not hasattr(request.user, 'superadmin_profile'):
        messages.error(request, "Permission denied.")
        return render_route(request, '/accounts/dashboard/')

    try:
        user = User.objects.get(id=user_id)
        roles = Role.objects.all()
        all_perms = _unique_admin_permissions()
        admins = AdminProfile.objects.all()

        if request.method == 'POST':
            user.first_name = request.POST.get('first_name')
            user.last_name = request.POST.get('last_name')
            user.email = request.POST.get('email')

            role_id = request.POST.get('role')
            if role_id:
                try:
                    user.role = Role.objects.get(id=role_id)
                except Role.DoesNotExist:
                    pass

            user.save()

            if hasattr(user, 'admin_profile'):
                perm_ids = request.POST.getlist('permissions[]')
                user.admin_profile.permissions.set(perm_ids)

            elif hasattr(user, 'executive_profile'):
                admin_id = request.POST.get('assigned_admin_id')
                if admin_id:
                    user.executive_profile.assigned_admin = AdminProfile.objects.filter(id=admin_id).first()
                    user.executive_profile.save()

            messages.success(request, f"User {user.username} updated successfully.")
            return render_route(request, 'view_user', user_id=user.id)

        return render(request, 'accounts/edit_user.html', {
            'target_user': user,
            'roles': roles,
            'all_permissions': all_perms,
            'administrators': admins,
            'active_nav': 'users',
        })
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return render_route(request, '/accounts/dashboard/')


@login_required(login_url="/accounts/")
@never_cache
def delete_user(request, user_id):
    if not hasattr(request.user, 'superadmin_profile'):
        messages.error(request, "Permission denied.")
        return render_route(request, '/accounts/dashboard/')

    try:
        user = User.objects.get(id=user_id)
        if user == request.user:
            messages.error(request, "You cannot delete yourself.")
        else:
            uname = user.username
            user.is_active = False
            user.save()
            messages.success(request, f"User {uname} has been suspended (deactivated).")
    except User.DoesNotExist:
        messages.error(request, "User not found.")

    return render_route(request, request.META.get('HTTP_REFERER', '/accounts/dashboard/'))


@login_required(login_url="/accounts/")
@never_cache
def toggle_user_status(request, user_id):
    if not hasattr(request.user, 'superadmin_profile'):
        messages.error(request, "Permission denied.")
        return render_route(request, '/accounts/dashboard/')

    try:
        user = User.objects.get(id=user_id)
        if user == request.user:
            messages.error(request, "You cannot deactivate yourself.")
        else:
            user.is_active = not user.is_active
            user.save()
            status_text = "activated" if user.is_active else "deactivated"
            messages.success(request, f"User {user.username} has been {status_text}.")
    except User.DoesNotExist:
        messages.error(request, "User not found.")

    if 'user' in locals() and hasattr(user, 'role') and user.role:
        if user.role.name == 'Admin':
            return render_route(request, '/accounts/dashboard/?tab=admin_mgt')
        elif user.role.name == 'Executive':
            return render_route(request, '/accounts/dashboard/?tab=exec_mgt')

    return render_route(request, '/accounts/dashboard/?tab=user_mgt')


# ─────────────────────────── HACKATHONS ───────────────────────────









# ─────────────────────────── PROBLEM STATEMENTS ───────────────────────────

# ─────────────────────────── CREATIVE MATERIALS ───────────────────────────

# ─────────────────────────── ADMIN PROFILE ───────────────────────────

@login_required(login_url='/accounts/')
@never_cache
def admin_profile(request):
    """Self-service profile page for Admin users."""
    if not hasattr(request.user, 'admin_profile'):
        messages.error(request, 'Access denied.')
        return redirect('login')
    return render(request, 'accounts/admin_profile.html', {
        'profile_user': request.user,
        'active_nav': 'admin_profile',
    })


@login_required(login_url='/accounts/')
def update_admin_profile(request):
    """Handle POST: update the admin's own profile (name, phone, password)."""
    if not hasattr(request.user, 'admin_profile'):
        messages.error(request, 'Access denied.')
        return redirect('login')
    if request.method != 'POST':
        return redirect('admin_profile')

    user = request.user
    try:
        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name  = request.POST.get('last_name',  user.last_name).strip()

        phone = request.POST.get('phone_number', '').strip()
        if phone:
            user.phone_number = phone

        if 'profile_image' in request.FILES:
            user.profile_image = request.FILES['profile_image']

        new_password     = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        if new_password:
            if new_password != confirm_password:
                messages.error(request, 'Passwords do not match.')
                return redirect('admin_profile')
            if len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters.')
                return redirect('admin_profile')
            user.set_password(new_password)
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)

        user.save()
        messages.success(request, 'Profile updated successfully. ✓')

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f'Admin profile update error: {exc}', exc_info=True)
        messages.error(request, f'Update failed: {exc}')

    return redirect('admin_profile')


# ─────────────────────────── SUPER ADMIN PROFILE ───────────────────────────

@login_required(login_url='/accounts/')
@never_cache
def superadmin_profile(request):
    """View the logged-in super admin's own profile."""
    is_super = (
        request.user.is_superuser or
        (request.user.role and request.user.role.name == 'Super Admin')
    )
    if not is_super:
        messages.error(request, 'Access denied.')
        return redirect('login')

    return render(request, 'accounts/superadmin_profile.html', {
        'tab': 'profile',
        'profile_user': request.user,
    })


@login_required(login_url='/accounts/')
def update_superadmin_profile(request):
    """Handle POST: update the super admin's own profile."""
    is_super = (
        request.user.is_superuser or
        (request.user.role and request.user.role.name == 'Super Admin')
    )
    if not is_super:
        messages.error(request, 'Access denied.')
        return redirect('login')
    if request.method != 'POST':
        return redirect('superadmin_profile')

    user = request.user
    try:
        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name  = request.POST.get('last_name',  user.last_name).strip()
        user.email      = request.POST.get('email',      user.email).strip()

        phone = request.POST.get('phone_number', '').strip()
        if phone:
            user.phone_number = phone

        gender = request.POST.get('gender', '').strip()
        if gender:
            user.gender = gender

        # ── Safe DOB parsing — handles "April 7, 2026", "2026-04-07", etc. ──
        dob_raw = request.POST.get('date_of_birth', '').strip()
        if dob_raw:
            from datetime import datetime as _dt
            parsed_dob = None
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%B %d, %Y', '%b %d, %Y'):
                try:
                    parsed_dob = _dt.strptime(dob_raw, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_dob:
                user.date_of_birth = parsed_dob
            # If format unrecognised, leave existing value untouched

        if 'profile_image' in request.FILES:
            user.profile_image = request.FILES['profile_image']

        # ── Optional password change ──
        new_password     = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        if new_password:
            if new_password != confirm_password:
                messages.error(request, 'New passwords do not match.')
                return redirect('superadmin_profile')
            if len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters.')
                return redirect('superadmin_profile')
            user.set_password(new_password)
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)

        user.save()
        messages.success(request, 'Profile updated successfully. ✓')

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f'Profile update error: {exc}', exc_info=True)
        messages.error(request, f'Update failed: {exc}')

    return redirect('superadmin_profile')


@login_required(login_url='/accounts/')
@never_cache
def executive_profile(request):
    """Self-service profile page for Executive users."""
    exec_profile, err = _exec_guard(request)
    if err:
        return err

    permission_count = 0
    if exec_profile.assigned_admin_id:
        permission_count = exec_profile.assigned_admin.permissions.count()

    return render(request, 'accounts/executive_profile.html', {
        'profile_user': request.user,
        'exec_profile': exec_profile,
        'assigned_admin': exec_profile.assigned_admin,
        'permission_count': permission_count,
        'active_nav': 'executive_profile',
    })


@login_required(login_url='/accounts/')
def update_executive_profile(request):
    """Handle POST updates for the executive profile."""
    exec_profile, err = _exec_guard(request)
    if err:
        return err
    if request.method != 'POST':
        return redirect('executive_profile')

    user = request.user
    try:
        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name = request.POST.get('last_name', user.last_name).strip()

        phone = request.POST.get('phone_number', '').strip()
        user.phone_number = phone or user.phone_number

        gender = request.POST.get('gender', '').strip()
        if gender:
            user.gender = gender

        dob_raw = request.POST.get('date_of_birth', '').strip()
        if dob_raw:
            from datetime import datetime as _dt
            parsed_dob = None
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%B %d, %Y', '%b %d, %Y'):
                try:
                    parsed_dob = _dt.strptime(dob_raw, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_dob:
                user.date_of_birth = parsed_dob

        if 'profile_image' in request.FILES:
            user.profile_image = request.FILES['profile_image']

        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        if new_password:
            if new_password != confirm_password:
                messages.error(request, 'Passwords do not match.')
                return redirect('executive_profile')
            if len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters.')
                return redirect('executive_profile')
            user.set_password(new_password)
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)

        user.save()
        messages.success(request, 'Executive profile updated successfully.')
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f'Executive profile update error: {exc}', exc_info=True)
        messages.error(request, f'Update failed: {exc}')

    return redirect('executive_profile')


@login_required(login_url='/accounts/')
@never_cache
def executive_dashboard(request):
    exec_profile, err = _exec_guard(request)
    if err:
        return err

    feature_cards, assigned_codenames = _build_executive_feature_cards(exec_profile)
    pending_rows = []
    users_qs = User.objects.filter(
        is_superuser=False,
        role__isnull=False,
    ).select_related('role').order_by('-date_joined')

    for user in users_qs:
        missing_fields = _completion_checklist(user)
        if missing_fields:
            pending_rows.append({
                'user': user,
                'role_name': user.role.name if user.role else '—',
                'missing_fields': missing_fields,
            })

    unread_count = InAppMessage.objects.filter(recipient=request.user, is_read=False).count()
    context = {
        'tab': 'overview',
        'exec_profile': exec_profile,
        'assigned_admin': exec_profile.assigned_admin,
        'feature_cards': feature_cards,
        'enabled_count': len([c for c in feature_cards if c['is_enabled']]),
        'permissions': assigned_codenames,
        'pending_rows': pending_rows[:8],
        'pending_total': len(pending_rows),
        'unread_count': unread_count,
        'active_nav': 'executive_dashboard',
    }
    return render(request, 'accounts/executive_dashboard.html', context)


@login_required(login_url='/accounts/')
@never_cache
def executive_user_status(request):
    """Read-only table of SPOC users with Pending/Completed completion status."""
    exec_profile, err = _exec_guard(request)
    if err:
        return err

    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    # Executive users only manage SPOC accounts in this workspace.
    users_qs = User.objects.filter(
        is_superuser=False,
        role__isnull=False,
        role__name__iexact='SPOC',
    ).select_related('role').order_by('-date_joined')

    if query:
        users_qs = users_qs.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    # Annotate completion status
    user_rows = []
    for u in users_qs:
        missing_fields = _completion_checklist(u)
        cs = _user_completion_status(u)
        if status_filter and cs != status_filter:
            continue
        user_rows.append({
            'user': u,
            'completion_status': cs,
            'missing_fields': missing_fields,
            'role_name': u.role.name if u.role else '—',
        })

    paginator = Paginator(user_rows, 20)
    page = request.GET.get('page')
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    unread_count = InAppMessage.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    feature_cards, assigned_codenames = _build_executive_feature_cards(exec_profile)

    context = {
        'page_obj': page_obj,
        'q': query,
        'status_filter': status_filter,
        'role_filter': 'SPOC',
        'roles_list': ['SPOC'],
        'total': paginator.count,
        'pending_count': sum(1 for r in user_rows if r['completion_status'] == 'pending'),
        'completed_count': sum(1 for r in user_rows if r['completion_status'] == 'completed'),
        'exec_profile': exec_profile,
        'assigned_admin': exec_profile.assigned_admin,
        'feature_cards': feature_cards,
        'enabled_count': len([c for c in feature_cards if c['is_enabled']]),
        'permissions': assigned_codenames,
        'unread_count': unread_count,
        'active_nav': 'executive_dashboard',
    }
    return render(request, 'accounts/executive_dashboard.html', {**context, 'tab': 'user_status'})


@login_required(login_url='/accounts/')
def executive_send_reminder(request, user_id):
    """Send an in-app and/or email reminder to a user with incomplete profile."""
    exec_profile, err = _exec_guard(request)
    if err:
        return err

    if request.method != 'POST':
        return redirect('executive_user_status')

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('executive_user_status')

    custom_msg = request.POST.get('custom_message', '').strip()
    send_email = request.POST.get('send_email') == 'on'

    default_body = (
        f'Dear {target_user.get_full_name() or target_user.username},\n\n'
        f'This is a reminder from the HackNexus team. '
        f'Some required fields in your profile are still incomplete. '
        f'Please log in and fill in all the required information at your earliest convenience.\n\n'
        f'Thank you,\nHackNexus Executive Team'
    )
    body = custom_msg if custom_msg else default_body
    subject = request.POST.get('subject', '').strip() or 'Action Required: Complete Your Profile'

    # In-app message
    InAppMessage.objects.create(
        sender=request.user,
        recipient=target_user,
        subject=subject,
        body=body,
    )

    # Email reminder (optional)
    if send_email and target_user.email:
        try:
            html_body = f"""
            <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                        padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
                <h2 style="color:#ea580c;margin-bottom:8px;">Profile Completion Reminder</h2>
                <p style="color:#374151;">Dear <strong>{target_user.get_full_name() or target_user.username}</strong>,</p>
                <div style="background:#fff7ed;border-left:4px solid #ea580c;padding:16px;border-radius:8px;margin:20px 0;">
                    <p style="margin:0;color:#374151;white-space:pre-line;">{body}</p>
                </div>
                <a href="https://hackathon.okcl.org/accounts/"
                   style="background:#ea580c;color:white;padding:12px 24px;border-radius:8px;
                          text-decoration:none;font-weight:700;display:inline-block;margin-top:8px;">
                    Complete My Profile →
                </a>
                <hr style="border:none;border-top:1px solid #f3f4f6;margin:24px 0;">
                <p style="color:#9ca3af;font-size:12px;">This message was sent by the HackNexus Executive team.</p>
            </div>
            """
            msg = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[target_user.email],
            )
            msg.attach_alternative(html_body, 'text/html')
            msg.send(fail_silently=True)
            messages.success(request, f'In-app + email reminder sent to {target_user.get_full_name() or target_user.email}.')
        except Exception as e:
            messages.warning(request, f'In-app message sent but email failed: {e}')
    else:
        messages.success(request, f'In-app reminder sent to {target_user.get_full_name() or target_user.username}.')

    return redirect('executive_user_status')


@login_required(login_url='/accounts/')
@never_cache
def executive_inbox(request):
    """Executive inbox — view all in-app messages."""
    exec_profile, err = _exec_guard(request)
    if err:
        return err

    inbox = InAppMessage.objects.filter(
        recipient=request.user
    ).select_related('sender').order_by('-created_at')

    sent = InAppMessage.objects.filter(
        sender=request.user
    ).select_related('recipient').order_by('-created_at')

    unread_count = inbox.filter(is_read=False).count()

    feature_cards, assigned_codenames = _build_executive_feature_cards(exec_profile)
    context = {
        'tab': 'inbox',
        'inbox': inbox,
        'sent': sent,
        'unread_count': unread_count,
        'exec_profile': exec_profile,
        'assigned_admin': exec_profile.assigned_admin,
        'feature_cards': feature_cards,
        'enabled_count': len([c for c in feature_cards if c['is_enabled']]),
        'permissions': assigned_codenames,
        'active_nav': 'executive_dashboard',
    }
    return render(request, 'accounts/executive_dashboard.html', context)


@login_required(login_url='/accounts/')
def executive_compose(request):
    """Send an in-app message (executive to admin or any user)."""
    exec_profile, err = _exec_guard(request)
    if err:
        return err

    if request.method != 'POST':
        return redirect('executive_inbox')

    recipient_id = request.POST.get('recipient_id')
    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()
    parent_id = request.POST.get('parent_id')

    if not recipient_id or not body:
        messages.error(request, 'Recipient and message body are required.')
        return redirect('executive_inbox')

    try:
        recipient = User.objects.get(id=recipient_id)
    except User.DoesNotExist:
        messages.error(request, 'Recipient not found.')
        return redirect('executive_inbox')

    parent = None
    if parent_id:
        parent = InAppMessage.objects.filter(id=parent_id).first()

    InAppMessage.objects.create(
        sender=request.user,
        recipient=recipient,
        subject=subject or f'Message from {request.user.get_full_name() or request.user.username}',
        body=body,
        parent=parent,
    )
    messages.success(request, f'Message sent to {recipient.get_full_name() or recipient.username}.')
    return redirect('executive_inbox')


@login_required(login_url='/accounts/')
@never_cache
def executive_message_detail(request, msg_id):
    """View a single message thread and mark it as read."""
    exec_profile, err = _exec_guard(request)
    if err:
        return err

    try:
        msg = InAppMessage.objects.select_related('sender', 'recipient').get(
            id=msg_id,
            recipient=request.user
        )
    except InAppMessage.DoesNotExist:
        messages.error(request, 'Message not found.')
        return redirect('executive_inbox')

    # Mark as read
    if not msg.is_read:
        msg.is_read = True
        msg.save(update_fields=['is_read'])

    replies = msg.replies.select_related('sender', 'recipient').order_by('created_at')
    unread_count = InAppMessage.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    feature_cards, assigned_codenames = _build_executive_feature_cards(exec_profile)

    context = {
        'tab': 'inbox',
        'message': msg,
        'replies': replies,
        'unread_count': unread_count,
        'exec_profile': exec_profile,
        'assigned_admin': exec_profile.assigned_admin,
        'feature_cards': feature_cards,
        'enabled_count': len([c for c in feature_cards if c['is_enabled']]),
        'permissions': assigned_codenames,
        'active_nav': 'executive_dashboard',
    }
    return render(request, 'accounts/executive_dashboard.html', context)


@login_required(login_url='/accounts/')
@never_cache
def admin_inbox(request):
    """Admin inbox — see messages from executives and users."""
    if not hasattr(request.user, 'admin_profile'):
        messages.error(request, 'Access denied.')
        return redirect('login')

    inbox = InAppMessage.objects.filter(
        recipient=request.user
    ).select_related('sender').order_by('-created_at')

    sent = InAppMessage.objects.filter(
        sender=request.user
    ).select_related('recipient').order_by('-created_at')

    unread_count = inbox.filter(is_read=False).count()

    # Mark all as read on view
    inbox.filter(is_read=False).update(is_read=True)

    context = {
        'inbox': inbox,
        'sent': sent,
        'unread_count': unread_count,
        'executive_contacts': ExecutiveProfile.objects.filter(
            assigned_admin=request.user.admin_profile
        ).select_related('user').order_by('user__first_name', 'user__username'),
        'active_nav': 'admin_inbox',
    }
    return render(request, 'accounts/admin_inbox.html', context)


@login_required(login_url='/accounts/')
def admin_compose(request):
    """Admin composes and sends an in-app message."""
    if not hasattr(request.user, 'admin_profile'):
        messages.error(request, 'Access denied.')
        return redirect('login')

    if request.method != 'POST':
        return redirect('admin_inbox')

    recipient_id = request.POST.get('recipient_id')
    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()
    parent_id = request.POST.get('parent_id')

    if not recipient_id or not body:
        messages.error(request, 'Recipient and message body are required.')
        return redirect('admin_inbox')

    try:
        recipient = User.objects.get(id=recipient_id)
    except User.DoesNotExist:
        messages.error(request, 'Recipient not found.')
        return redirect('admin_inbox')

    parent = None
    if parent_id:
        parent = InAppMessage.objects.filter(id=parent_id).first()

    InAppMessage.objects.create(
        sender=request.user,
        recipient=recipient,
        subject=subject or f'Message from {request.user.get_full_name() or request.user.username}',
        body=body,
        parent=parent,
    )
    messages.success(request, f'Message sent to {recipient.get_full_name() or recipient.username}.')
    return redirect('admin_inbox')


@login_required(login_url='/accounts/')
def resend_executive_credentials(request, exec_user_id):
    """Superadmin can resend credentials email to an executive."""
    is_super = (
        request.user.is_superuser or
        (request.user.role and request.user.role.name == 'Super Admin')
    )
    if not is_super:
        messages.error(request, 'Access denied.')
        return redirect('login')

    try:
        exec_user = User.objects.get(id=exec_user_id, executive_profile__isnull=False)
        # Generate a temporary password and set it
        from .passwords import generate_password
        new_pass = generate_password()
        exec_user.set_password(new_pass)
        exec_user.save()
        sent = _send_welcome_email(exec_user, new_pass, 'Executive')
        if sent:
            messages.success(request, f'Credentials resent to {exec_user.email}.')
        else:
            messages.warning(request, 'Password reset but email delivery failed — check EMAIL settings.')
    except User.DoesNotExist:
        messages.error(request, 'Executive not found.')

    return render_route(request, '/accounts/dashboard/?tab=exec_mgt')


@login_required(login_url='/accounts/')
@never_cache
def admin_profile(request):
    """View the logged-in admin's own profile."""
    if not hasattr(request.user, 'admin_profile'):
        messages.error(request, 'Access denied.')
        return redirect('login')

    return render(request, 'accounts/admin_profile.html', {
        'active_nav': 'admin_profile',
        'profile_user': request.user,
    })


@login_required(login_url='/accounts/')
def update_admin_profile(request):
    """Handle POST: update the admin's own profile."""
    if not hasattr(request.user, 'admin_profile'):
        messages.error(request, 'Access denied.')
        return redirect('login')
    if request.method != 'POST':
        return redirect('admin_profile')

    user = request.user
    try:
        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name  = request.POST.get('last_name',  user.last_name).strip()

        phone = request.POST.get('phone_number', '').strip()
        if phone:
            user.phone_number = phone

        if 'profile_image' in request.FILES:
            user.profile_image = request.FILES['profile_image']

        # Optional password change
        new_password     = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        if new_password:
            if new_password != confirm_password:
                messages.error(request, 'New passwords do not match.')
                return redirect('admin_profile')
            if len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters.')
                return redirect('admin_profile')
            user.set_password(new_password)
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)

        user.save()
        messages.success(request, 'Profile updated successfully. ✓')

    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f'Admin profile update error: {exc}', exc_info=True)
        messages.error(request, f'Update failed: {exc}')

    return redirect('admin_profile')
