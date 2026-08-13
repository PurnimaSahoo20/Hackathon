"""
features/views.py

View functionality dealing with features such as SPOC Management, Teams, Content, Venues and Logistics, and Finances.
"""

import csv
import io
import uuid
import logging
import secrets
import re
import os

def _clean_indian_phone_number(val):
    val = (val or '').strip()
    cleaned = re.sub(r'[\s\-()]', '', val)
    if cleaned.startswith('+91'):
        digits = cleaned[3:]
    elif cleaned.startswith('91') and len(cleaned) == 12:
        digits = cleaned[2:]
    else:
        digits = cleaned
    if not re.match(r'^[6-9]\d{9}$', digits):
        raise ValueError("Phone number must be a valid 10-digit Indian mobile number (e.g. +91 9876543210).")
    return f"+91 {digits}"

def _clean_indian_contact_number(val):
    val = (val or '').strip()
    cleaned = re.sub(r'[\s\-()]', '', val)
    if cleaned.startswith('+91'):
        digits = cleaned[3:]
    elif cleaned.startswith('91') and len(cleaned) == 12:
        digits = cleaned[2:]
    else:
        digits = cleaned
    if not re.match(r'^\d{10}$', digits):
        raise ValueError("Contact number must be a valid 10-digit contact number (e.g. +91 6742500000).")
    return f"+91 {digits}"

def _validate_image_file(uploaded_file, field_label, max_size_mb=2):
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif']:
        raise ValueError(f"{field_label} must be a valid image file (JPG, JPEG, PNG, or GIF).")
    if uploaded_file.size > max_size_mb * 1024 * 1024:
        raise ValueError(f"{field_label} file size cannot exceed {max_size_mb}MB.")

def _validate_document_file(uploaded_file, field_label, max_size_mb=5):
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ['.pdf', '.jpg', '.jpeg', '.png']:
        raise ValueError(f"{field_label} must be a PDF or an image (JPG, JPEG, PNG).")
    if uploaded_file.size > max_size_mb * 1024 * 1024:
        raise ValueError(f"{field_label} file size cannot exceed {max_size_mb}MB.")
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from django.db import transaction, connection
from django.db.models import Q, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_POST
from django.http import HttpResponse

# accounts-app models
from accounts.models import (
    User, Role, SpocProfile, Institution, AdminProfile, MentorProfile,
    TeamleadProfile, JuryProfile, JuryInvitation,
    ExpertProfile, ExpertInvitation
)
from accounts.rendering import render_route
from jury.models import EvaluatorProfile

# cross-app imports
from events.models import Hackathon, ProblemStatement, CreativeMaterial, RoundMarkingParameter
from .models import (
    Team, Venue,
    TeamMember, TeamStatusLog, TeamMentor,
    TeamRegistration, TeamDocument,
    Podcast, Documentation,
    LogisticsPlan, VenueAllocation, VenueFoodRefreshment, VolunteerAssignment,
    EventBudget, SponsorshipFund, FinancialTransaction,
    FAQItem,
)

logger = logging.getLogger(__name__)

JURY_TESTIMONIAL_PREFIX = '[Jury Testimonial]'
EXPERT_TESTIMONIAL_PREFIX = '[Expert Testimonial]'
TEAM_TESTIMONIAL_PREFIX = '[Team Testimonial]'
VIP_TESTIMONIAL_PREFIX = '[VIP Testimonial]'
NEWS_PREFIX = '[News]'
ANNOUNCEMENT_PREFIX = '[Announcement]'
GALLERY_PREFIX = '[Gallery]'
FEED_PREFIX = '[Feed]'

TESTIMONIAL_PREFIX_MAP = {
    'jury': JURY_TESTIMONIAL_PREFIX,
    'expert': EXPERT_TESTIMONIAL_PREFIX,
    'team': TEAM_TESTIMONIAL_PREFIX,
    'vip': VIP_TESTIMONIAL_PREFIX,
}

LANDING_SECTION_CHOICES = [
    ('latest-news', 'Latest News'),
    ('podcasts', 'Podcasts'),
    ('gallery', 'Gallery'),
    ('testimonials', 'Testimonials'),
]

LANDING_SECTION_LABELS = {value: label for value, label in LANDING_SECTION_CHOICES}
FEED_PLATFORM_CHOICES = [
    ('instagram', 'Instagram'),
    ('facebook', 'Facebook'),
    ('youtube', 'YouTube'),
    ('twitter', 'Twitter / X'),
    ('linkedin', 'LinkedIn'),
    ('website', 'Website'),
    ('other', 'Other'),
]
FEED_PLATFORM_LABELS = dict(FEED_PLATFORM_CHOICES)


def _clean_landing_sections(raw_sections):
    allowed = {value for value, _ in LANDING_SECTION_CHOICES}
    cleaned = []
    for section in raw_sections or []:
        section = (section or '').strip()
        if section in allowed and section not in cleaned:
            cleaned.append(section)
    return cleaned


def _landing_sections_label_text(sections):
    labels = [LANDING_SECTION_LABELS.get(section, section.replace('-', ' ').title()) for section in (sections or []) if section]
    return ', '.join(labels) if labels else 'Not selected'

LIVE_APPROVED_STATUSES = ('spoc_approved', 'admin_approved')

ADMIN_PERMISSION_META = {
    'spoc_college_mgt': {
        'label': 'SPOC & College Management',
        'description': 'Invite and manage institutions and SPOCs.',
        'icon': 'school-outline',
        'url_name': 'spoc_college_management',
    },
    'team_event_monitoring': {
        'label': 'Team & Event Monitoring',
        'description': 'Track registrations, live teams, and workflow updates.',
        'icon': 'people-circle-outline',
        'url_name': 'team_event_monitoring',
    },
    'problem_statement_content_mgt': {
        'label': 'Problem Statement & Content Management',
        'description': 'Manage problem statements, podcasts, and documents.',
        'icon': 'library-outline',
        'url_name': 'content_management',
    },
    'venue_logistics_mgt': {
        'label': 'Venue & Logistics Management',
        'description': 'Plan venues, logistics, food, and volunteer allocation.',
        'icon': 'business-outline',
        'url_name': 'venue_logistics_management',
    },
    'financial_mgt': {
        'label': 'Financial Management',
        'description': 'Manage budgets, sponsorships, and transactions.',
        'icon': 'cash-outline',
        'url_name': 'finance_management',
    },
    'jury_onboarding_mgt': {
        'label': 'Jury Onboarding & Management',
        'description': 'Create jury accounts and maintain the jury roster.',
        'icon': 'people-outline',
        'url_name': 'jury_management',
    },
    'evaluation_coordination': {
        'label': 'Evaluation Coordination',
        'description': 'Configure round-wise evaluation parameters and readiness.',
        'icon': 'clipboard-outline',
        'url_name': 'jury_management',
    },
    'feedback_support_mgt': {
        'label': 'Feedback & Support Management',
        'description': 'Review support tickets and coordinate responses.',
        'icon': 'help-buoy-outline',
        'url_name': 'support_operations_management',
    },
    'accommodation_health_mgt': {
        'label': 'Accommodation & Health Support Management',
        'description': 'Monitor travel, stay, and health-related requests.',
        'icon': 'medkit-outline',
        'url_name': 'support_operations_management',
    },
    'social_media_creative_mgt': {
        'label': 'Social Media & Creative Management',
        'description': 'Publish and control promotional creative assets.',
        'icon': 'color-palette-outline',
        'url_name': 'media_communications_management',
    },
    'media_sponsorship_mgt': {
        'label': 'Media & Sponsorship Management',
        'description': 'Track sponsors together with public-facing media assets.',
        'icon': 'megaphone-outline',
        'url_name': 'media_communications_management',
    },
    'announcement_communication_sys': {
        'label': 'Announcement & Communication System',
        'description': 'Review the current outward communication surface.',
        'icon': 'chatbubbles-outline',
        'url_name': 'media_communications_management',
    },
    'reporting_result_mgt': {
        'label': 'Reporting & Result Management',
        'description': 'Review outcome summaries and export result data.',
        'icon': 'bar-chart-outline',
        'url_name': 'results_reporting_management',
    },
    'awards_certification_mgt': {
        'label': 'Awards & Certification Management',
        'description': 'Identify award-ready teams and track prize-related spends.',
        'icon': 'trophy-outline',
        'url_name': 'results_reporting_management',
    },
}


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _get_models():
    """Legacy helper kept for backward compatibility within this module."""
    from accounts.models import SpocInvitation, InstitutionExtended, SpocInstitutionMap
    return {
        'SpocInvitation':      SpocInvitation,
        'InstitutionExtended': InstitutionExtended,
        'SpocInstitutionMap':  SpocInstitutionMap,
        'TeamMember':          TeamMember,
        'TeamStatusLog':       TeamStatusLog,
        'TeamMentor':          TeamMentor,
        'Podcast':             Podcast,
        'Documentation':       Documentation,
        'TeamRegistration':    TeamRegistration,
        'TeamDocument':        TeamDocument,
    }


def _superadmin_required(request):
    return (
        request.user.is_authenticated and
        (request.user.is_superuser or
         (request.user.role and request.user.role.name in ('Super Admin', 'Admin')))
    )


def _is_super_admin_user(user):
    return bool(
        user.is_authenticated and (
            user.is_superuser or
            (getattr(user, 'role', None) and user.role.name == 'Super Admin')
        )
    )


def _assigned_permission_codenames(user):
    if not getattr(user, 'is_authenticated', False):
        return set()
    if _is_super_admin_user(user):
        return set(ADMIN_PERMISSION_META.keys())
    if hasattr(user, 'admin_profile'):
        return set(user.admin_profile.permissions.values_list('codename', flat=True))
    if hasattr(user, 'executive_profile') and user.executive_profile.assigned_admin_id:
        return set(user.executive_profile.assigned_admin.permissions.values_list('codename', flat=True))
    return set()


def _has_admin_permission(request, *codenames):
    if _is_super_admin_user(request.user):
        return True
    if not (hasattr(request.user, 'admin_profile') or hasattr(request.user, 'executive_profile')):
        return False
    assigned = _assigned_permission_codenames(request.user)
    return any(code in assigned for code in codenames)


def _is_executive_readonly_user(user):
    return bool(getattr(user, 'is_authenticated', False) and hasattr(user, 'executive_profile'))


def _feature_home_for_user(user):
    if _is_executive_readonly_user(user):
        return '/accounts/executive-dashboard/'
    return '/accounts/admin-dashboard/'


def _permission_denied(request, *codenames):
    readable = [
        ADMIN_PERMISSION_META.get(code, {}).get('label', code.replace('_', ' ').title())
        for code in codenames
    ]
    messages.error(
        request,
        "Access denied. You need one of these permissions: " + ", ".join(readable) + ".",
    )
    return render_route(request, _feature_home_for_user(request.user))


def _feature_permission_required(request, *codenames):
    if _is_executive_readonly_user(request.user):
        url_name = getattr(getattr(request, 'resolver_match', None), 'url_name', '') or ''
        readonly_prefixes = (
            'edit_', 'save_', 'delete_', 'toggle_', 'approve_', 'reject_', 'suspend_', 'send_',
            'update_', 'create_', 'mentor_admin_',
        )
        if request.method != 'GET' or url_name.startswith(readonly_prefixes):
            messages.error(request, 'Executives have view-only access for assigned features.')
            return render_route(request, _feature_home_for_user(request.user))
    if _has_admin_permission(request, *codenames):
        return None
    return _permission_denied(request, *codenames)


def _feature_context(request, **extra):
    context = {
        'admin_permission_meta': ADMIN_PERMISSION_META,
        'assigned_permission_codes': sorted(_assigned_permission_codenames(request.user)),
        'readonly_mode': _is_executive_readonly_user(request.user),
    }
    context.update(extra)
    return context


def _has_team_permission(request):
    return _has_admin_permission(request, 'team_event_monitoring')


def _build_unique_username(email, fallback_prefix='user'):
    base = slugify((email or '').split('@')[0]).replace('-', '') or fallback_prefix
    candidate = base
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base}{secrets.token_hex(2)}"
    return candidate


def _build_portal_password(length=12):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _jury_testimonial_title(user):
    display_name = user.get_full_name().strip() or user.username
    return f'{JURY_TESTIMONIAL_PREFIX} {user.id} | {display_name}'


def _jury_testimonial_hackathon(user):
    invite = getattr(user, 'from_jury_invitation', None)
    return getattr(invite, 'hackathon', None)


def _jury_testimonial_asset(user):
    hackathon = _jury_testimonial_hackathon(user)
    if not hackathon:
        return None
    return CreativeMaterial.objects.filter(
        hackathon=hackathon,
        title__startswith=f'{JURY_TESTIMONIAL_PREFIX} {user.id} |',
    ).order_by('-uploaded_at').first()


def _expert_testimonial_title(user):
    display_name = user.get_full_name().strip() or user.username
    return f'{EXPERT_TESTIMONIAL_PREFIX} {user.id} | {display_name}'


def _expert_testimonial_hackathon(user):
    invite = getattr(user, 'from_expert_invitation', None)
    return getattr(invite, 'hackathon', None)


def _expert_testimonial_asset(user):
    hackathon = _expert_testimonial_hackathon(user)
    if not hackathon:
        return None
    return CreativeMaterial.objects.filter(
        hackathon=hackathon,
        title__startswith=f'{EXPERT_TESTIMONIAL_PREFIX} {user.id} |',
    ).order_by('-uploaded_at').first()


def _vip_testimonial_title(raw_title):
    return f'{VIP_TESTIMONIAL_PREFIX} {raw_title.strip()}'


def _strip_asset_prefix(title, prefix):
    title = title or ''
    if title.startswith(prefix):
        return title[len(prefix):].strip(' |')
    return title


def _attach_landing_section(title, landing_section):
    title = (title or '').strip()
    if landing_section in LANDING_SECTION_LABELS:
        return f'[Landing:{landing_section}] {title}'
    return title


def _extract_landing_section(title):
    title = title or ''
    marker_prefix = '[Landing:'
    if title.startswith(marker_prefix) and '] ' in title:
        section_value = title[len(marker_prefix):].split(']', 1)[0].strip()
        return section_value if section_value in LANDING_SECTION_LABELS else ''
    return ''


def _strip_landing_section(title):
    title = title or ''
    marker_prefix = '[Landing:'
    if title.startswith(marker_prefix) and '] ' in title:
        return title.split('] ', 1)[1].strip()
    return title.strip()


def _testimonial_title(kind, raw_title, landing_section=''):
    prefix = TESTIMONIAL_PREFIX_MAP.get(kind, VIP_TESTIMONIAL_PREFIX)
    return f'{prefix} {_attach_landing_section(raw_title, landing_section)}'


def _extract_testimonial_assets(queryset, kind):
    prefix = TESTIMONIAL_PREFIX_MAP[kind]
    return queryset.filter(title__startswith=prefix)


def _normalize_testimonial_title(title):
    normalized = title or ''
    for prefix in TESTIMONIAL_PREFIX_MAP.values():
        normalized = _strip_asset_prefix(normalized, prefix)
    normalized = _strip_landing_section(normalized)
    return normalized.strip() or 'Testimonial'


def _news_item_kind(title):
    title = title or ''
    if title.startswith(ANNOUNCEMENT_PREFIX):
        return 'announcement'
    return 'news'


def _display_asset_title(title):
    return _strip_landing_section(title or '').strip() or 'Untitled'


def _prefixed_title(prefix, raw_title, landing_section=''):
    return f'{prefix} {_attach_landing_section(raw_title, landing_section)}'


def _extract_prefixed_assets(queryset, prefix):
    return queryset.filter(title__startswith=prefix)


def _feed_description(platform, published_date):
    return f'platform::{platform}\npublished_date::{published_date}'


def _parse_feed_description(description):
    platform = 'other'
    published_date = ''
    for line in (description or '').splitlines():
        if line.startswith('platform::'):
            platform = line.split('::', 1)[1].strip() or 'other'
        elif line.startswith('published_date::'):
            published_date = line.split('::', 1)[1].strip()
    return {
        'platform': platform if platform in FEED_PLATFORM_LABELS else 'other',
        'published_date': published_date,
    }


def _resolve_hackathon_scope(request):
    hackathons = Hackathon.objects.exclude(status='Suspended').order_by('-created_at')
    hackathon_filter = request.GET.get('hackathon', '')

    active_hackathon = None
    if hackathon_filter and hackathon_filter.isdigit():
        active_hackathon = Hackathon.objects.filter(id=hackathon_filter).first()
    if active_hackathon is None:
        active_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
        if active_hackathon:
            hackathon_filter = str(active_hackathon.id)

    return hackathons, hackathon_filter, active_hackathon


def _podcast_publication_scope_supported():
    """Return whether the current database has the newer podcast scope column."""
    table_name = Podcast._meta.db_table
    try:
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table_name)
        return any(column.name == 'publication_scope' for column in description)
    except Exception:
        logger.warning("Could not inspect %s for publication_scope; assuming legacy schema.", table_name, exc_info=True)
        return False


def _get_or_create_team_user(email, first_name='', last_name='', phone_number='', role_name=''):
    email = (email or '').strip().lower()
    first_name = (first_name or '').strip()
    last_name = (last_name or '').strip()
    phone_number = (phone_number or '').strip()

    if not email:
        raise ValueError("Email is required for each team user.")

    user = User.objects.filter(email__iexact=email).first()
    if not user:
        base_username = slugify(email.split('@')[0]).replace('-', '') or 'user'
        username = base_username
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{get_random_string(5).lower()}"

        role = None
        if role_name:
            role = Role.objects.filter(name__iexact=role_name).first()

        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number or None,
            role=role,
            is_active=True,
        )
        user.set_unusable_password()
        user.save()
        return user

    changed = False
    for field_name, value in {
        'first_name': first_name,
        'last_name': last_name,
        'phone_number': phone_number,
    }.items():
        if value and not getattr(user, field_name):
            setattr(user, field_name, value)
            changed = True
    if changed:
        user.save(update_fields=['first_name', 'last_name', 'phone_number'])
    return user


def _send_team_admin_approval_email(team, mentor_invite=None):
    leader = team.team_leader
    mentor_name = mentor_invite.mentor_name if mentor_invite else 'your mentor'
    try:
        subject = f"Admin Approved Team '{team.team_name}' - HackNexus"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                    padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
            <h2 style="color:#059669;">Admin Approval Complete</h2>
            <p>Hello <strong>{leader.get_full_name() or leader.username}</strong>,</p>
            <p>Your team <strong>{team.team_name}</strong> for <strong>{team.hackathon.name}</strong> has now been approved by the admin.</p>
            <p>{mentor_name} has been finalized as your mentor, and login credentials have been sent to the mentor email.</p>
            <a href="https://hackathon.okcl.org/team/dashboard/"
               style="background:#2563eb;color:white;padding:12px 24px;border-radius:8px;
                      text-decoration:none;font-weight:700;display:inline-block;margin-top:12px;">
                Open Team Dashboard
            </a>
        </div>"""
        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"Your team '{team.team_name}' has been approved by the admin. Mentor credentials have been sent.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[leader.email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    except Exception as exc:
        logger.error(f"Admin team approval email failed for team {team.pk}: {exc}", exc_info=True)


def _notify_team_admin_approval(team, mentor_invite=None):
    try:
        from team.team.models import TeamNotification
        registration = getattr(team, 'from_registration', None)
        mentor_name = mentor_invite.mentor_name if mentor_invite else 'your mentor'
        TeamNotification.objects.create(
            team_leader=team.team_leader,
            registration=registration,
            notif_type='admin_approved',
            title='Admin approved your team',
            body=f"Your team '{team.team_name}' is now fully approved. Login credentials have been sent to {mentor_name}.",
        )
        _send_team_admin_approval_email(team, mentor_invite)
    except Exception as exc:
        logger.error(f"Admin team notification failed for team {team.pk}: {exc}", exc_info=True)


def _finalize_team_admin_approval(team, acting_user):
    from mentor.mentor.models import MentorInvitation
    from mentor.mentor.signals import provision_mentor_account

    if team.status == 'admin_approved':
        return False

    mentor_invite = None
    registration = getattr(team, 'from_registration', None)
    if registration:
        mentor_invite = MentorInvitation.objects.filter(
            registration=registration
        ).select_related('created_user').order_by('-invited_at').first()

    old_status = team.status
    team.status = 'admin_approved'
    team.save(update_fields=['status', 'updated_at'])
    TeamStatusLog.objects.create(
        team=team,
        old_status=old_status,
        new_status='admin_approved',
        changed_by=acting_user,
        note=f"Admin approved the team from the live team detail view.",
    )

    if mentor_invite and mentor_invite.created_user is None and mentor_invite.status in ('accepted', 'spoc_pending', 'spoc_approved'):
        mentor_invite.status = 'admin_approved'
        mentor_invite.admin_decided_at = timezone.now()
        if not mentor_invite.admin_note:
            mentor_invite.admin_note = f"Admin approved with team finalization by {acting_user.get_username()}."
        mentor_invite.save(update_fields=['status', 'admin_decided_at', 'admin_note'])
        provision_mentor_account(mentor_invite, resend_email=True)

    _notify_team_admin_approval(team, mentor_invite)
    return True


# ══════════════════════════════════════════════════════════════
#  FEATURE 1 : SPOC & COLLEGE MANAGEMENT
# ══════════════════════════════════════════════════════════════

@login_required(login_url='/accounts/')
@never_cache
def spoc_college_management(request):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied

    from accounts.models import SpocInvitation

    sub = request.GET.get('sub', 'invitations')
    hackathons = Hackathon.objects.filter(status='Live').order_by('-created_at')

    context = _feature_context(request, tab='spoc_college', sub=sub, hackathons=hackathons)

    if sub == 'invitations':
        query = request.GET.get('q', '')
        invites = SpocInvitation.objects.select_related(
            'invited_by', 'hackathon', 'approved_by', 'created_user'
        ).order_by('-invited_at')
        if query:
            invites = invites.filter(
                Q(email__icontains=query) | Q(institution_name__icontains=query)
            )
        context.update({'invitations': invites, 'q': query})

    elif sub == 'institutions':
        query = request.GET.get('q', '')
        institutions = Institution.objects.all().order_by('name')
        if query:
            institutions = institutions.filter(name__icontains=query)
        paginator = Paginator(institutions, 15)
        page = request.GET.get('page')
        try:
            context['institutions'] = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            context['institutions'] = paginator.page(1)
        context['q'] = query

    elif sub == 'spocs':
        query = request.GET.get('q', '')
        spocs = SpocProfile.objects.select_related('user').order_by('-user__date_joined')
        if query:
            spocs = spocs.filter(
                Q(user__username__icontains=query) |
                Q(user__email__icontains=query) |
                Q(institution_name__icontains=query)
            )
        context.update({'spocs': spocs, 'q': query})

    return render(request, 'features/spoc_college.html', context)


@login_required(login_url='/accounts/')
@never_cache
def view_spoc(request, spoc_id):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied
    try:
        spoc = SpocProfile.objects.select_related('user').get(id=spoc_id)
    except SpocProfile.DoesNotExist:
        messages.error(request, "SPOC not found.")
        return render_route(request, '/features/spoc/?sub=spocs')

    from accounts.models import SpocInstitutionMap
    maps = SpocInstitutionMap.objects.filter(spoc=spoc).select_related('institution')
    return render(request, 'features/spoc_detail.html', {
        'spoc': spoc, 'institution_maps': maps,
        'tab': 'spoc_college', 'sub': 'spocs',
    })


@login_required(login_url='/accounts/')
@never_cache
def edit_spoc(request, spoc_id):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied
    try:
        spoc = SpocProfile.objects.select_related('user').get(id=spoc_id)
    except SpocProfile.DoesNotExist:
        messages.error(request, "SPOC not found.")
        return render_route(request, '/features/spoc/?sub=spocs')

    if request.method == 'POST':
        try:
            user = spoc.user
            user.first_name = request.POST.get('first_name', user.first_name).strip()
            user.last_name = request.POST.get('last_name', user.last_name).strip()
            user.email = request.POST.get('email', user.email).strip()
            phone = request.POST.get('phone_number', '').strip()
            if phone:
                user.phone_number = phone
            gender = request.POST.get('gender', '').strip()
            if gender:
                user.gender = gender
            user.save()
            spoc.institution_name = request.POST.get('institution_name', spoc.institution_name).strip()
            spoc.save()
            messages.success(request, f"SPOC '{user.username}' updated successfully.")
        except Exception as exc:
            logger.error(f"Edit SPOC {spoc_id}: {exc}", exc_info=True)
            messages.error(request, f"Update failed: {exc}")
        return render_route(request, '/features/spoc/?sub=spocs')

    return render(request, 'features/spoc_edit.html', {
        'spoc': spoc, 'tab': 'spoc_college', 'sub': 'spocs',
    })


@login_required(login_url='/accounts/')
@require_POST
def suspend_spoc(request, spoc_id):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied
    try:
        spoc = SpocProfile.objects.select_related('user').get(id=spoc_id)
        spoc.user.is_active = not spoc.user.is_active
        spoc.user.save()
        word = "activated" if spoc.user.is_active else "suspended"
        messages.success(request, f"SPOC '{spoc.user.username}' {word}.")
    except SpocProfile.DoesNotExist:
        messages.error(request, "SPOC not found.")
    except Exception as exc:
        messages.error(request, f"Failed: {exc}")
    sub = request.GET.get('sub', 'spocs')
    if sub not in ['spocs', 'invitations']:
        sub = 'spocs'
    return render_route(request, f'/features/spoc/?sub={sub}')


@login_required(login_url='/accounts/')
@never_cache
def send_spoc_invite(request):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/spoc/?sub=invitations')

    email = request.POST.get('email', '').strip().lower()
    hackathon_id = request.POST.get('hackathon_id')
    institution_name = request.POST.get('institution_name', '').strip()
    city = request.POST.get('city', '').strip()
    state = request.POST.get('state', '').strip()

    if not email:
        messages.error(request, "Email is required.")
        return render_route(request, '/features/spoc/?sub=invitations')
    try:
        hackathon = _get_selected_hackathon(hackathon_id)
        _create_and_send_spoc_invitation(
            request=request,
            email=email,
            hackathon=hackathon,
            institution_name=institution_name,
            city=city,
            state=state,
        )
        messages.success(request, f"Invitation sent to {email}.")
    except Exception as exc:
        logger.error(f"SPOC invite error {email}: {exc}", exc_info=True)
        messages.error(request, f"Failed: {exc}")
    return render_route(request, '/features/spoc/?sub=invitations')


@login_required(login_url='/accounts/')
@never_cache
def send_bulk_spoc_invites(request):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/spoc/?sub=invitations')

    csv_file = request.FILES.get('csv_file')
    hackathon_id = request.POST.get('hackathon_id')

    if not csv_file:
        messages.error(request, "Please upload a CSV file.")
        return render_route(request, '/features/spoc/?sub=invitations')

    if not csv_file.name.lower().endswith('.csv'):
        messages.error(request, "Only CSV files are supported for bulk invite.")
        return render_route(request, '/features/spoc/?sub=invitations')

    try:
        decoded = csv_file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        messages.error(request, "CSV file must be UTF-8 encoded.")
        return render_route(request, '/features/spoc/?sub=invitations')

    records = _extract_spoc_data_from_csv(decoded)
    if not records:
        messages.error(request, "No valid entries were found in the uploaded CSV.")
        return render_route(request, '/features/spoc/?sub=invitations')

    hackathon = _get_selected_hackathon(hackathon_id)
    sent_count = 0
    failed = []

    for rec in records:
        email = rec['email']
        try:
            _create_and_send_spoc_invitation(
                request=request,
                email=email,
                hackathon=hackathon,
                institution_name=rec['institution_name'],
                city=rec['city'],
                state=rec['state'],
            )
            sent_count += 1
        except Exception as exc:
            failed.append(f"{email} ({exc})")

    if sent_count:
        messages.success(request, f"Bulk invitation completed. {sent_count} invitation(s) sent.")
    if failed:
        preview = "; ".join(failed[:5])
        extra = f" and {len(failed) - 5} more" if len(failed) > 5 else ""
        messages.warning(request, f"{len(failed)} email(s) could not be processed: {preview}{extra}")

    return render_route(request, '/features/spoc/?sub=invitations')


def _get_selected_hackathon(hackathon_id):
    if hackathon_id and str(hackathon_id).isdigit():
        return Hackathon.objects.filter(id=hackathon_id).first()
    return None


def _create_and_send_spoc_invitation(request, email, hackathon=None, institution_name='', city='', state=''):
    from accounts.models import SpocInvitation
    from django.urls import reverse

    email = (email or '').strip().lower()
    if not email:
        raise ValueError("Email is required.")

    try:
        validate_email(email)
    except ValidationError as exc:
        raise ValueError("Invalid email address.") from exc

    if institution_name:
        inst_name_clean = institution_name.strip()
        from accounts.models import Institution
        existing_inst_inv = SpocInvitation.objects.filter(institution_name__iexact=inst_name_clean).exclude(status='rejected').first()
        existing_inst = Institution.objects.filter(name__iexact=inst_name_clean).first()
        if existing_inst_inv or existing_inst:
            raise ValueError(f"University '{inst_name_clean}' has already been invited or registered.")

    existing = SpocInvitation.objects.filter(email=email).first()
    if existing:
        if existing.status == 'approved':
            raise ValueError("Already approved SPOC.")
        raise ValueError("Invitation already sent.")

    if User.objects.filter(email=email).exists():
        raise ValueError("User already exists.")

    with transaction.atomic():
        token = uuid.uuid4().hex
        invite = SpocInvitation.objects.create(
            invited_by=request.user,
            email=email,
            hackathon=hackathon,
            token=token,
            status='invited',
            institution_name=institution_name,
            city=city,
            state=state,
        )
        form_link = request.build_absolute_uri(reverse('spoc_register_form', args=[token]))
        _send_spoc_invite_email(invite, form_link)


def _extract_spoc_data_from_csv(decoded_csv):
    reader = csv.reader(io.StringIO(decoded_csv))
    rows = [row for row in reader if any((cell or '').strip() for cell in row)]
    if not rows:
        return []

    header = [cell.strip().lower() for cell in rows[0]]
    email_candidates = {'email', 'emails', 'spoc email', 'spoc_email', 'mail', 'email address'}
    inst_candidates = {'institution', 'institution name', 'institution_name', 'college', 'college name', 'university'}
    city_candidates = {'city', 'town', 'city/town'}
    state_candidates = {'state', 'province'}

    email_idx = next((idx for idx, name in enumerate(header) if name in email_candidates), None)
    inst_idx = next((idx for idx, name in enumerate(header) if name in inst_candidates), None)
    city_idx = next((idx for idx, name in enumerate(header) if name in city_candidates), None)
    state_idx = next((idx for idx, name in enumerate(header) if name in state_candidates), None)

    records = []
    seen_emails = set()

    if email_idx is not None:
        data_rows = rows[1:]
        for row in data_rows:
            if email_idx >= len(row):
                continue
            email = row[email_idx].strip().lower()
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)
            
            inst_name = row[inst_idx].strip() if (inst_idx is not None and inst_idx < len(row)) else ''
            city = row[city_idx].strip() if (city_idx is not None and city_idx < len(row)) else ''
            state = row[state_idx].strip() if (state_idx is not None and state_idx < len(row)) else ''
            
            records.append({
                'email': email,
                'institution_name': inst_name,
                'city': city,
                'state': state
            })
        return records

    first_value = (rows[0][0] if rows[0] else '').strip().lower()
    data_rows = rows
    if first_value in email_candidates:
        data_rows = rows[1:]

    for row in data_rows:
        email = next((cell.strip().lower() for cell in row if '@' in (cell or '')), '')
        if email and email not in seen_emails:
            seen_emails.add(email)
            records.append({
                'email': email,
                'institution_name': '',
                'city': '',
                'state': ''
            })

    return records


def _send_spoc_invite_email(invite, form_link):
    # Set defaults / get values
    from django.utils import timezone
    hackathon = invite.hackathon
    event_name = hackathon.name if hackathon else "HackNexus"
    org_name = hackathon.organization_name if hackathon else "HackNexus Secretariat"
    
    # Reference number: REF/HN/2026/0001 (or similar)
    ref_no = f"REF/HN/2026/{invite.id:04d}"
    
    # Date
    date_str = invite.invited_at.strftime('%d %B %Y') if invite.invited_at else timezone.now().strftime('%d %B %Y')
    
    institution_name = invite.institution_name or "Your Institution"
    city = invite.city or "City"
    state = invite.state or "State"
    
    # Event flagship state
    event_state = "Odisha"
    
    event_admin_name = invite.invited_by.get_full_name() if (invite.invited_by and invite.invited_by.get_full_name()) else "Event Administrator"
    
    support_email = "support@hacknexus.com"
    support_number = "+91 99999 99999"
    website = "https://hackathon.okcl.org/"

    subject = f"Invitation to Participate in {event_name} – Nomination of Institutional SPOC and Registration of Institution"
    
    plain_body = f"""Ref. No.: {ref_no}
Date: {date_str}

To
The Principal / Director / Vice Chancellor
{institution_name}
{city}, {state}

Subject: Invitation to participate in {event_name} and nomination of an Institutional Single Point of Contact (SPOC)

Respected Sir/Madam,

Greetings from {org_name}!

The {event_name} is a flagship event of {event_state} organised by {org_name} to facilitate a platform for the students of our nation to showcase their skill and talent.

We are pleased to invite {institution_name} to participate in {event_name}, an initiative aimed at fostering innovation, creativity, problem-solving, entrepreneurship, and collaborative learning among students.

The event provides an excellent platform for students to transform innovative ideas into impactful solutions while working on real-world challenges across various domains. It also offers an opportunity for institutions to showcase the innovation potential of their students and strengthen their engagement with industry and academia.

To facilitate smooth participation, we request your esteemed institution to nominate an Institutional Single Point of Contact (SPOC) who will coordinate all activities related to the event on behalf of your institution.

The nominated SPOC will be responsible for:
•	Registering the institution on the event portal. 
•	Coordinating student participation. 
•	Disseminating event-related information within the institution. 
•	Facilitating communication between the organizing committee and participating students. 
•	Monitoring registrations and submissions from the institution. 

Once the institution is successfully registered, the institution's name will automatically become available in the student registration portal, enabling students to select {institution_name} while registering for {event_name}.

Institution Registration
The nominated SPOC may kindly register the institution using the following link:
{form_link}

Upon successful registration, login credentials and further communication regarding the event schedule, problem statements, guidelines, and important announcements will be shared with the registered SPOC.

We sincerely request your kind support in encouraging maximum student participation and making this initiative a grand success.

Should you require any clarification or assistance, please feel free to contact the Event Coordination Team.

We look forward to the enthusiastic participation of {institution_name} in {event_name}.

With warm regards,

{event_admin_name}
Event Administrator
{event_name}
{org_name}
Email: {support_email}
Mobile: {support_number}
Website: {website}
"""

    html_body = f"""<div style="font-family: Arial, sans-serif; line-height: 1.6; max-width: 700px; margin: 0 auto; padding: 24px; color: #1f2937; border: 1px solid #e5e7eb; border-radius: 12px; background-color: #ffffff;">
    <div style="margin-bottom: 24px;">
        <strong>Ref. No.:</strong> {ref_no}<br>
        <strong>Date:</strong> {date_str}
    </div>

    <div style="margin-bottom: 20px;">
        To<br>
        <strong>The Principal / Director / Vice Chancellor</strong><br>
        {institution_name}<br>
        {city}, {state}
    </div>

    <div style="margin-bottom: 20px; font-weight: bold; text-decoration: underline;">
        Subject: Invitation to participate in {event_name} and nomination of an Institutional Single Point of Contact (SPOC)
    </div>

    <div style="margin-bottom: 16px;">
        Respected Sir/Madam,<br><br>
        Greetings from {org_name}!
    </div>

    <p>The <strong>{event_name}</strong> is a flagship event of <strong>{event_state}</strong> organised by <strong>{org_name}</strong> to facilitate a platform for the students of our nation to showcase their skill and talent.</p>

    <p>We are pleased to invite <strong>{institution_name}</strong> to participate in <strong>{event_name}</strong>, an initiative aimed at fostering innovation, creativity, problem-solving, entrepreneurship, and collaborative learning among students.</p>

    <p>The event provides an excellent platform for students to transform innovative ideas into impactful solutions while working on real-world challenges across various domains. It also offers an opportunity for institutions to showcase the innovation potential of their students and strengthen their engagement with industry and academia.</p>

    <p>To facilitate smooth participation, we request your esteemed institution to nominate an Institutional Single Point of Contact (SPOC) who will coordinate all activities related to the event on behalf of your institution.</p>

    <div style="margin-bottom: 16px; padding-left: 20px;">
        The nominated SPOC will be responsible for:
        <ul style="margin: 8px 0; padding-left: 20px;">
            <li>Registering the institution on the event portal.</li>
            <li>Coordinating student participation.</li>
            <li>Disseminating event-related information within the institution.</li>
            <li>Facilitating communication between the organizing committee and participating students.</li>
            <li>Monitoring registrations and submissions from the institution.</li>
        </ul>
    </div>

    <p>Once the institution is successfully registered, the institution's name will automatically become available in the student registration portal, enabling students to select <strong>{institution_name}</strong> while registering for <strong>{event_name}</strong>.</p>

    <div style="margin-top: 24px; margin-bottom: 24px; padding: 20px; background-color: #fff7ed; border-left: 4px solid #ea580c; border-radius: 6px;">
        <h4 style="margin: 0 0 10px 0; color: #c2410c; font-size: 16px; font-weight: 700;">Institution Registration</h4>
        <p style="margin: 0 0 16px 0; font-size: 14px;">The nominated SPOC may kindly register the institution using the following link:</p>
        <a href="{form_link}" style="background-color: #ea580c; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 700; display: inline-block; font-size: 14px;">Register Institution →</a>
    </div>

    <p>Upon successful registration, login credentials and further communication regarding the event schedule, problem statements, guidelines, and important announcements will be shared with the registered SPOC.</p>

    <p>We sincerely request your kind support in encouraging maximum student participation and making this initiative a grand success.</p>

    <p>Should you require any clarification or assistance, please feel free to contact the Event Coordination Team.</p>

    <p>We look forward to the enthusiastic participation of <strong>{institution_name}</strong> in <strong>{event_name}</strong>.</p>

    <div style="margin-top: 32px; border-top: 1px solid #e5e7eb; padding-top: 20px; font-size: 14px;">
        With warm regards,<br><br>
        <strong>{event_admin_name}</strong><br>
        Event Administrator<br>
        {event_name}<br>
        {org_name}<br><br>
        <strong>Email:</strong> <a href="mailto:{support_email}" style="color: #ea580c; text-decoration: none;">{support_email}</a><br>
        <strong>Mobile:</strong> {support_number}<br>
        <strong>Website:</strong> <a href="{website}" style="color: #ea580c; text-decoration: none;">{website}</a>
    </div>
</div>
"""

    msg = EmailMultiAlternatives(
        subject,
        plain_body,
        settings.DEFAULT_FROM_EMAIL, [invite.email]
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)


def _send_rejection_correction_email(email, form_link, role_label, reason, hackathon=None):
    hackathon_name = hackathon.name if hackathon else "HackNexus"
    safe_reason = reason or "Please review your previous submission and update the required details."
    html = f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
        <h2 style="color:#dc2626;">Application Update Required</h2>
        <p>Your <strong>{role_label}</strong> application for <strong>{hackathon_name}</strong> needs correction before it can be approved.</p>
        <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:14px 16px;margin:18px 0;">
            <div style="font-weight:700;color:#991b1b;margin-bottom:6px;">Rejection reason</div>
            <div style="color:#7f1d1d;">{safe_reason}</div>
        </div>
        <p>You can reopen the same application form, edit your earlier submission, and submit it again for review.</p>
        <a href="{form_link}" style="background:#2563eb;color:white;padding:14px 24px;border-radius:8px;text-decoration:none;font-weight:700;display:inline-block;margin:12px 0 8px;">Open Application Form</a>
        <p style="color:#6b7280;font-size:13px;">If the button does not work, use this link:<br><a href="{form_link}">{form_link}</a></p>
    </div>"""
    msg = EmailMultiAlternatives(
        f"{role_label} application needs correction - {hackathon_name}",
        f"Your application needs correction.\nReason: {safe_reason}\nUpdate here: {form_link}",
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )
    msg.attach_alternative(html, "text/html")
    try:
        msg.send(fail_silently=False)
    except Exception:
        logger.exception("Failed to send rejection correction email to %s", email)


def spoc_register_form(request, token):
    from accounts.models import SpocInvitation
    try:
        invitation = SpocInvitation.objects.get(token=token)
    except SpocInvitation.DoesNotExist:
        return render(request, 'features/spoc_register_invalid.html',
                      {'reason': 'Invalid or expired registration link.'})
    if invitation.status == 'suspended':
        return render(request, 'features/spoc_register_invalid.html',
                      {'reason': 'This SPOC registration is currently suspended. Please contact the administrator.'})
    if invitation.status in ('approved', 'pending'):
        msg = ('Already approved. You can log in.' if invitation.status == 'approved'
               else 'Already submitted and under review.')
        return render(request, 'features/spoc_register_invalid.html', {'reason': msg})

    if request.method == 'POST':
        try:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone_number = request.POST.get('phone_number', '').strip()
            gender = request.POST.get('gender', '').strip()
            institution_name = request.POST.get('institution_name', '').strip()
            institution_email = request.POST.get('institution_email', '').strip().lower()
            institution_address = request.POST.get('institution_address', '').strip()
            institution_head_name = request.POST.get('institution_head_name', '').strip()
            institution_head_email = request.POST.get('institution_head_email', '').strip().lower()
            institution_contact = request.POST.get('institution_contact', '').strip()
            institution_location = request.POST.get('institution_location', '').strip()

            if not first_name or len(first_name) < 2:
                raise ValueError("First name must be at least 2 characters long.")
            if not last_name or len(last_name) < 2:
                raise ValueError("Last name must be at least 2 characters long.")
            
            phone_number = _clean_indian_phone_number(phone_number)
            
            if not institution_name or len(institution_name) < 3:
                raise ValueError("Institution name must be at least 3 characters long.")
            
            from accounts.models import Institution
            existing_inst_inv = SpocInvitation.objects.filter(institution_name__iexact=institution_name).exclude(id=invitation.id).exclude(status='rejected').first()
            existing_inst = Institution.objects.filter(name__iexact=institution_name).first()
            if existing_inst_inv or existing_inst:
                raise ValueError(f"University/Institution '{institution_name}' has already been invited or registered.")
                
            if not institution_email:
                raise ValueError("Institution email is required.")
            try:
                validate_email(institution_email)
            except ValidationError:
                raise ValueError("Please enter a valid institution email address.")
                
            if not institution_address or len(institution_address) < 10:
                raise ValueError("Institution address must be at least 10 characters long.")
                
            if not institution_location or len(institution_location) < 3:
                raise ValueError("Institution location/city must be at least 3 characters long.")
                
            if institution_contact and institution_contact != '+91':
                institution_contact = _clean_indian_contact_number(institution_contact)
            else:
                institution_contact = ''
                
            if not institution_head_name or len(institution_head_name) < 2:
                raise ValueError("Institution head/principal name must be at least 2 characters long.")
                
            if not institution_head_email:
                raise ValueError("Institution head email is required.")
            try:
                validate_email(institution_head_email)
            except ValidationError:
                raise ValueError("Please enter a valid head/principal email address.")

            dob = request.POST.get('date_of_birth', '').strip()
            if dob:
                from datetime import datetime, date
                try:
                    dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                    today = date.today()
                    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                    if age < 18:
                        raise ValueError("SPOC must be at least 18 years old.")
                except ValueError as e:
                    if "18" in str(e):
                        raise e
                    raise ValueError("Please enter a valid date of birth in YYYY-MM-DD format.")
            else:
                dob_date = None

            if 'institution_logo' in request.FILES:
                _validate_image_file(request.FILES['institution_logo'], "Institution logo")
            
            if not invitation.id_proof and 'id_proof' not in request.FILES:
                raise ValueError("Government ID Proof is required.")
                
            if 'id_proof' in request.FILES:
                _validate_document_file(request.FILES['id_proof'], "Government ID proof")

            invitation.first_name = first_name
            invitation.last_name = last_name
            invitation.phone_number = phone_number
            invitation.gender = gender
            invitation.institution_name = institution_name
            invitation.institution_email = institution_email
            invitation.institution_address = institution_address
            invitation.institution_head_name = institution_head_name
            invitation.institution_head_email = institution_head_email
            invitation.institution_contact = institution_contact
            invitation.institution_location = institution_location
            
            if dob_date:
                invitation.date_of_birth = dob_date
            else:
                invitation.date_of_birth = None
            
            if 'institution_logo' in request.FILES:
                invitation.institution_logo = request.FILES['institution_logo']
            if 'id_proof' in request.FILES:
                invitation.id_proof = request.FILES['id_proof']
                
            invitation.status = 'pending'
            invitation.rejection_reason = ''
            invitation.submitted_at = timezone.now()
            invitation.save()
            return render(request, 'features/spoc_register_success.html',
                          {'email': invitation.email})
        except Exception as exc:
            logger.error(f"SPOC form token {token}: {exc}", exc_info=True)
            messages.error(request, f"Submission failed: {exc}.")
    return render(request, 'features/spoc_register_form.html', {
        'invitation': invitation,
        'is_rejected_resubmission': invitation.status == 'rejected',
    })


@login_required(login_url='/accounts/')
@never_cache
def view_spoc_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied

    from accounts.models import SpocInvitation
    invite = get_object_or_404(
        SpocInvitation.objects.select_related('invited_by', 'hackathon', 'approved_by', 'created_user'),
        id=invite_id
    )
    return render(request, 'features/spoc_invitation_detail.html', {
        'invite': invite,
        'tab': 'spoc_college',
        'sub': 'invitations',
    })


@login_required(login_url='/accounts/')
@never_cache
def edit_spoc_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied

    from accounts.models import SpocInvitation
    invite = get_object_or_404(SpocInvitation, id=invite_id)

    if invite.status == 'approved':
        messages.warning(request, "Approved applications should be edited from the SPOC profile.")
        if invite.created_user and hasattr(invite.created_user, 'spoc_profile'):
            return render_route(request, 'edit_spoc', invite.created_user.spoc_profile.id)
        return render_route(request, '/features/spoc/?sub=invitations')

    if request.method == 'POST':
        try:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip().lower()
            phone_number = request.POST.get('phone_number', '').strip()
            gender = request.POST.get('gender', '').strip()
            institution_name = request.POST.get('institution_name', '').strip()
            institution_email = request.POST.get('institution_email', '').strip().lower()
            institution_address = request.POST.get('institution_address', '').strip()
            institution_head_name = request.POST.get('institution_head_name', '').strip()
            institution_head_email = request.POST.get('institution_head_email', '').strip().lower()
            institution_contact = request.POST.get('institution_contact', '').strip()
            institution_location = request.POST.get('institution_location', '').strip()

            if not first_name or len(first_name) < 2:
                raise ValueError("First name must be at least 2 characters long.")
            if not last_name or len(last_name) < 2:
                raise ValueError("Last name must be at least 2 characters long.")
            
            if not email:
                raise ValueError("Email is required.")
            try:
                validate_email(email)
            except ValidationError:
                raise ValueError("Please enter a valid email address.")
            
            if email != invite.email:
                if SpocInvitation.objects.filter(email=email).exclude(id=invite.id).exists():
                    raise ValueError(f"An invitation already exists for {email}.")
                if User.objects.filter(email=email).exists():
                    raise ValueError("A user with this email already exists.")
            
            phone_number = _clean_indian_phone_number(phone_number)
            
            if not institution_name or len(institution_name) < 3:
                raise ValueError("Institution name must be at least 3 characters long.")
            
            if institution_name != invite.institution_name:
                from accounts.models import Institution
                existing_inst_inv = SpocInvitation.objects.filter(institution_name__iexact=institution_name).exclude(id=invite.id).exclude(status='rejected').first()
                existing_inst = Institution.objects.filter(name__iexact=institution_name).first()
                if existing_inst_inv or existing_inst:
                    raise ValueError(f"University/Institution '{institution_name}' has already been invited or registered.")
                
            if not institution_email:
                raise ValueError("Institution email is required.")
            try:
                validate_email(institution_email)
            except ValidationError:
                raise ValueError("Please enter a valid institution email address.")
                
            if not institution_address or len(institution_address) < 10:
                raise ValueError("Institution address must be at least 10 characters long.")
                
            if not institution_location or len(institution_location) < 3:
                raise ValueError("Institution location/city must be at least 3 characters long.")
                
            if institution_contact and institution_contact != '+91':
                institution_contact = _clean_indian_contact_number(institution_contact)
            else:
                institution_contact = ''
                
            if not institution_head_name or len(institution_head_name) < 2:
                raise ValueError("Institution head/principal name must be at least 2 characters long.")
                
            if not institution_head_email:
                raise ValueError("Institution head email is required.")
            try:
                validate_email(institution_head_email)
            except ValidationError:
                raise ValueError("Please enter a valid head/principal email address.")

            dob = request.POST.get('date_of_birth', '').strip()
            if dob:
                from datetime import datetime, date
                try:
                    dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                    today = date.today()
                    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                    if age < 18:
                        raise ValueError("SPOC must be at least 18 years old.")
                except ValueError as e:
                    if "18" in str(e):
                        raise e
                    raise ValueError("Please enter a valid date of birth in YYYY-MM-DD format.")
            else:
                dob_date = None

            if 'institution_logo' in request.FILES:
                _validate_image_file(request.FILES['institution_logo'], "Institution logo")
            
            if 'id_proof' in request.FILES:
                _validate_document_file(request.FILES['id_proof'], "Government ID proof")

            invite.first_name = first_name
            invite.last_name = last_name
            invite.email = email
            invite.phone_number = phone_number
            invite.gender = gender
            invite.institution_name = institution_name
            invite.institution_email = institution_email
            invite.institution_address = institution_address
            invite.institution_head_name = institution_head_name
            invite.institution_head_email = institution_head_email
            invite.institution_contact = institution_contact
            invite.institution_location = institution_location
            invite.date_of_birth = dob_date
            
            if 'institution_logo' in request.FILES:
                invite.institution_logo = request.FILES['institution_logo']
            if 'id_proof' in request.FILES:
                invite.id_proof = request.FILES['id_proof']
                
            invite.save()
            messages.success(request, f"SPOC application for '{invite.email}' updated.")
            return render_route(request, 'view_spoc_invitation', invite.id)
        except Exception as exc:
            logger.error(f"Edit SPOC application {invite_id}: {exc}", exc_info=True)
            messages.error(request, f"Update failed: {exc}")

    return render(request, 'features/spoc_invitation_edit.html', {
        'invite': invite,
        'tab': 'spoc_college',
        'sub': 'invitations',
    })


@login_required(login_url='/accounts/')
@require_POST
def approve_spoc_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied
    from accounts.models import SpocInvitation
    try:
        invite = SpocInvitation.objects.get(id=invite_id)
        if invite.status != 'pending':
            messages.warning(request, f"Invitation is '{invite.status}'.")
            return render_route(request, '/features/spoc/?sub=invitations')
        invite.institution_name = ' '.join((invite.institution_name or '').split())
        if not invite.institution_name:
            messages.error(request, "Institution name is required before approval.")
            return render_route(request, 'edit_spoc_invitation', invite.id)
        invite.status = 'approved'
        invite.approved_by = request.user
        invite.approved_at = timezone.now()
        invite.save(update_fields=['institution_name', 'status', 'approved_by', 'approved_at'])
        messages.success(request, f"SPOC '{invite.email}' approved. Account created.")
    except SpocInvitation.DoesNotExist:
        messages.error(request, "Invitation not found.")
    except Exception as exc:
        logger.error(f"Approve invite {invite_id}: {exc}", exc_info=True)
        messages.error(request, f"Failed: {exc}")
    return render_route(request, '/features/spoc/?sub=invitations')


@login_required(login_url='/accounts/')
@require_POST
def suspend_spoc_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied

    from accounts.models import SpocInvitation
    try:
        invite = SpocInvitation.objects.get(id=invite_id)
        if invite.status == 'approved':
            messages.warning(request, "Approved SPOCs must be suspended from the SPOC profile.")
            return render_route(request, '/features/spoc/?sub=invitations')

        if invite.status == 'suspended':
            invite.status = 'pending' if invite.submitted_at else 'invited'
            word = "reactivated"
        else:
            invite.status = 'suspended'
            word = "suspended"

        invite.save(update_fields=['status'])
        messages.success(request, f"SPOC application for '{invite.email}' {word}.")
    except SpocInvitation.DoesNotExist:
        messages.error(request, "Invitation not found.")
    except Exception as exc:
        logger.error(f"Suspend invite {invite_id}: {exc}", exc_info=True)
        messages.error(request, f"Failed: {exc}")
    return render_route(request, '/features/spoc/?sub=invitations')

@login_required(login_url='/accounts/')
@require_POST
def reject_spoc_invitation(request, invite_id):
    from accounts.models import SpocInvitation
    from django.urls import reverse

    if request.method != 'POST':
        return render_route(request, '/features/spoc/?sub=invitations')
    denied = _feature_permission_required(request, 'spoc_college_mgt')
    if denied:
        return denied
    try:
        invite = SpocInvitation.objects.get(id=invite_id)
        if invite.status != 'pending':
            messages.warning(request, f"Only pending SPOC applications can be rejected. Current status: {invite.status}.")
            return render_route(request, '/features/spoc/?sub=invitations')
        reason = request.POST.get('rejection_reason', '').strip()
        if not reason:
            messages.error(request, "Rejection reason is required.")
            return render_route(request, 'view_spoc_invitation', invite.id)
        invite.status = 'rejected'
        invite.rejection_reason = reason
        invite.save(update_fields=['status', 'rejection_reason'])
        form_link = request.build_absolute_uri(reverse('spoc_register_form', args=[invite.token]))
        _send_rejection_correction_email(invite.email, form_link, 'SPOC', reason, invite.hackathon)
        messages.success(request, f'Invitation for {invite.email} rejected.')
    except SpocInvitation.DoesNotExist:
        messages.error(request, "Not found.")
    except Exception as exc:
        logger.error(f"Reject SPOC invite {invite_id}: {exc}", exc_info=True)
        messages.error(request, f"Failed: {exc}")
    return render_route(request, '/features/spoc/?sub=invitations')


# ══════════════════════════════════════════════════════════════
#  FEATURE 2 : TEAM & EVENT MONITORING
# ══════════════════════════════════════════════════════════════

@login_required(login_url='/accounts/')
@never_cache
def team_event_monitoring(request):
    denied = _feature_permission_required(request, 'team_event_monitoring')
    if denied:
        return denied

    sub              = request.GET.get('sub', 'live_teams')
    hackathon_filter = request.GET.get('hackathon', '')
    status_filter    = request.GET.get('status', '')
    query            = request.GET.get('q', '')

    live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    all_hackathons = Hackathon.objects.exclude(status='Suspended').order_by('-created_at')

    active_hackathon = None
    if hackathon_filter and hackathon_filter.isdigit():
        active_hackathon = Hackathon.objects.filter(id=hackathon_filter).first()
    elif live_hackathon:
        active_hackathon = live_hackathon

    context = {
        'tab':              'team_monitoring',
        'sub':              sub,
        'live_hackathon':   live_hackathon,
        'active_hackathon': active_hackathon,
        'all_hackathons':   all_hackathons,
        'hackathon_filter': hackathon_filter or (str(live_hackathon.id) if live_hackathon else ''),
        'status_filter':    status_filter,
        'q':                query,
        'STATUS_CHOICES':   TeamStatusLog.STATUS_CHOICES,
        'has_team_perm':    _has_team_permission(request),
        'institutions':      Institution.objects.order_by('name'),
        'problem_statements': ProblemStatement.objects.filter(
            **({'hackathon': active_hackathon} if active_hackathon else {})
        ).order_by('title'),
    }
    context['pending_count'] = TeamRegistration.objects.filter(
        status='pending',
        **({'hackathon': active_hackathon} if active_hackathon else {})
    ).count()

    if sub == 'pending_approvals':
        regs = TeamRegistration.objects.select_related(
            'hackathon', 'team_leader', 'institution', 'problem_statement', 'mentor'
        ).filter(status='pending').order_by('-registered_at')

        if active_hackathon:
            regs = regs.filter(hackathon=active_hackathon)
        if query:
            regs = regs.filter(
                Q(team_name__icontains=query) |
                Q(team_leader__username__icontains=query) |
                Q(team_leader__email__icontains=query)
            )

        paginator = Paginator(regs, 15)
        page = request.GET.get('page')
        try:
            context['pending_regs'] = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            context['pending_regs'] = paginator.page(1)

    elif sub == 'live_teams':
        teams = Team.objects.select_related(
            'hackathon', 'institution', 'team_leader', 'problem_statement'
        ).order_by('team_name')

        if active_hackathon:
            teams = teams.filter(hackathon=active_hackathon)
        if status_filter:
            teams = teams.filter(status=status_filter)
        if query:
            teams = teams.filter(
                Q(team_name__icontains=query) |
                Q(team_leader__username__icontains=query) |
                Q(team_leader__email__icontains=query)
            )

        paginator = Paginator(teams, 15)
        page = request.GET.get('page')
        try:
            context['teams'] = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            context['teams'] = paginator.page(1)

        if active_hackathon:
            ht = Team.objects.filter(hackathon=active_hackathon)
            context['summary'] = {
                'total':     ht.count(),
                'active':    ht.filter(status__in=LIVE_APPROVED_STATUSES).count(),
                'pending':   ht.filter(status__in=['pending_mentor', 'pending_spoc']).count(),
                'submitted': ht.filter(status='submitted').count(),
                'evaluated': ht.filter(status='evaluated').count(),
                'suspended': ht.filter(status='disqualified').count(),
            }

    elif sub == 'all_hackathons':
        stats = []
        for h in all_hackathons:
            t = Team.objects.filter(hackathon=h)
            r = TeamRegistration.objects.filter(hackathon=h)
            stats.append({
                'hackathon':   h,
                'total':       t.count(),
                'active':      t.filter(status__in=LIVE_APPROVED_STATUSES).count(),
                'pending_reg': r.filter(status='pending').count(),
                'submitted':   t.filter(status='submitted').count(),
                'evaluated':   t.filter(status='evaluated').count(),
            })
        context['stats'] = stats

    elif sub == 'team_detail':
        team_id = request.GET.get('team_id')
        try:
            team = Team.objects.select_related(
                'hackathon', 'institution', 'team_leader', 'problem_statement'
            ).get(id=team_id)
            context.update({
                'team':    team,
                'members': TeamMember.objects.filter(team=team).select_related('user'),
                'mentors': TeamMentor.objects.filter(team=team).select_related('mentor__user'),
                'logs':    TeamStatusLog.objects.filter(team=team).select_related('changed_by'),
                'docs':    TeamDocument.objects.filter(team=team),
                'reg':     getattr(team, 'from_registration', None),
            })
            registration = getattr(team, 'from_registration', None)
            if registration:
                from mentor.mentor.models import MentorInvitation
                from team.team.models import TeamSupportMessage, TeamTravelDetail
                mentor_invite = MentorInvitation.objects.filter(
                    registration=registration
                ).select_related('created_user').order_by('-invited_at').first()
                context.update({
                    'leader_details': registration.leader_details or {},
                    'reg_members': registration.get_members_display(),
                    'mentor_invite': mentor_invite,
                    'travel_details': TeamTravelDetail.objects.filter(registration=registration),
                    'support_messages': TeamSupportMessage.objects.filter(registration=registration),
                })
        except Team.DoesNotExist:
            messages.error(request, "Team not found.")
            return render_route(request, '/features/teams/?sub=live_teams')

    elif sub == 'reg_detail':
        reg_id = request.GET.get('reg_id')
        try:
            from mentor.mentor.models import MentorInvitation
            from team.team.models import TeamSupportMessage, TeamTravelDetail

            reg = TeamRegistration.objects.select_related(
                'hackathon', 'team_leader', 'institution',
                'problem_statement', 'mentor', 'reviewed_by'
            ).get(id=reg_id)
            mentor_invite = MentorInvitation.objects.filter(
                registration=reg
            ).select_related('created_user').order_by('-invited_at').first()
            context.update({
                'reg':           reg,
                'docs':          TeamDocument.objects.filter(registration=reg),
                'mentor_invite': mentor_invite,
                'reg_members':   reg.get_members_display(),
                'leader_details': reg.leader_details or {},
                'travel_details': TeamTravelDetail.objects.filter(registration=reg),
                'support_messages': TeamSupportMessage.objects.filter(registration=reg),
            })
        except TeamRegistration.DoesNotExist:
            messages.error(request, "Registration not found.")
            return render_route(request, '/features/teams/?sub=pending_approvals')

    return render(request, 'features/team_monitoring.html', context)


@login_required(login_url='/accounts/')
def create_team(request):
    if request.method != 'POST':
        return render_route(request, '/features/teams/?sub=live_teams')

    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')

    hackathon_id = request.POST.get('hackathon_id', '').strip()
    team_name = request.POST.get('team_name', '').strip()
    institution_id = request.POST.get('institution_id', '').strip()
    problem_statement_id = request.POST.get('problem_statement_id', '').strip()
    status = request.POST.get('status', 'spoc_approved').strip() or 'spoc_approved'
    declared_member_count_raw = request.POST.get('declared_member_count', '').strip()

    redirect_url = f'/features/teams/?sub=live_teams&hackathon={hackathon_id}'

    try:
        if not hackathon_id or not team_name:
            raise ValueError("Hackathon and team name are required.")

        hackathon = Hackathon.objects.get(id=hackathon_id)
        if Team.objects.filter(hackathon=hackathon, team_name__iexact=team_name).exists():
            raise ValueError(f"A team named '{team_name}' already exists for this hackathon.")

        leader_email = request.POST.get('leader_email', '').strip().lower()
        leader_first_name = request.POST.get('leader_first_name', '').strip()
        leader_last_name = request.POST.get('leader_last_name', '').strip()
        leader_phone = request.POST.get('leader_phone_number', '').strip()
        leader_role = request.POST.get('leader_role_in_team', 'Leader').strip() or 'Leader'
        leader_aadhaar_proof = request.FILES.get('leader_aadhaar_proof')
        leader_college_id_proof = request.FILES.get('leader_college_id_proof')

        if not leader_email:
            raise ValueError("Team leader email is required.")
        if not leader_aadhaar_proof or not leader_college_id_proof:
            raise ValueError("Aadhaar proof and college ID proof are required for the team leader.")

        member_first_names = request.POST.getlist('member_first_name[]')
        member_last_names = request.POST.getlist('member_last_name[]')
        member_emails = request.POST.getlist('member_email[]')
        member_phones = request.POST.getlist('member_phone_number[]')
        member_roles = request.POST.getlist('member_role_in_team[]')
        member_indexes = request.POST.getlist('member_index[]')

        member_rows = []
        for index, email in enumerate(member_emails):
            email = email.strip()
            if not email:
                continue
            form_index = member_indexes[index] if index < len(member_indexes) else str(index)
            aadhaar_proof = request.FILES.get(f'member_aadhaar_proof_{form_index}')
            college_id_proof = request.FILES.get(f'member_college_id_proof_{form_index}')
            if not aadhaar_proof or not college_id_proof:
                raise ValueError(f"Aadhaar proof and college ID proof are required for member {index + 1}.")
            member_rows.append({
                'first_name': member_first_names[index].strip() if index < len(member_first_names) else '',
                'last_name': member_last_names[index].strip() if index < len(member_last_names) else '',
                'email': email,
                'phone_number': member_phones[index].strip() if index < len(member_phones) else '',
                'role_in_team': member_roles[index].strip() if index < len(member_roles) else 'Member',
                'aadhaar_proof': aadhaar_proof,
                'college_id_proof': college_id_proof,
            })

        total_members = len(member_rows) + 1
        try:
            declared_member_count = int(declared_member_count_raw)
        except (TypeError, ValueError):
            raise ValueError("Please mention a valid number of team members.")

        if declared_member_count != total_members:
            raise ValueError(
                f"Number of members ({declared_member_count}) mismatches the number of valid entries ({total_members}). "
                "Ensure all listed members have a valid email address."
            )

        if total_members < hackathon.min_team_size or total_members > hackathon.max_team_size:
            raise ValueError(
                f"Team size must be between {hackathon.min_team_size} and {hackathon.max_team_size} members."
            )

        from collections import Counter
        all_emails = [leader_email] + [row['email'].lower() for row in member_rows]
        email_counts = Counter(all_emails)
        duplicates = [email for email, count in email_counts.items() if count > 1]
        
        if duplicates:
            msg = f"Duplicate emails found: {', '.join(duplicates)}. Each member (including the leader) must have a unique email."
            raise ValueError(msg)

        valid_statuses = [value for value, _ in TeamStatusLog.STATUS_CHOICES]
        if status not in valid_statuses:
            status = 'spoc_approved'

        with transaction.atomic():
            leader = _get_or_create_team_user(
                leader_email,
                first_name=leader_first_name,
                last_name=leader_last_name,
                phone_number=leader_phone,
                role_name='Teamlead',
            )
            TeamleadProfile.objects.get_or_create(user=leader)

            team = Team.objects.create(
                team_name=team_name,
                hackathon=hackathon,
                institution_id=institution_id or None,
                team_leader=leader,
                problem_statement_id=problem_statement_id or None,
                declared_member_count=declared_member_count,
                leader_role_in_team=leader_role,
                leader_aadhaar_proof=leader_aadhaar_proof,
                leader_college_id_proof=leader_college_id_proof,
                status=status,
            )

            for row in member_rows:
                member_user = _get_or_create_team_user(
                    row['email'],
                    first_name=row['first_name'],
                    last_name=row['last_name'],
                    phone_number=row['phone_number'],
                )
                TeamMember.objects.create(
                    team=team,
                    user=member_user,
                    role_in_team=row['role_in_team'] or 'Member',
                    aadhaar_proof=row['aadhaar_proof'],
                    college_id_proof=row['college_id_proof'],
                )

            TeamStatusLog.objects.create(
                team=team,
                old_status='',
                new_status=status,
                changed_by=request.user,
                note=f"Team created directly by {request.user.get_username()}.",
            )

        messages.success(request, f"Team '{team.team_name}' created with {total_members} member(s).")
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team.id}&hackathon={hackathon.id}')

    except Hackathon.DoesNotExist:
        messages.error(request, "Selected hackathon was not found.")
    except Exception as exc:
        logger.error(f"Create team failed: {exc}", exc_info=True)
        messages.error(request, f"Team creation failed: {exc}")

    return render_route(request, redirect_url)


@login_required(login_url='/accounts/')
def approve_team_registration(request, reg_id):
    if request.method != 'POST':
        return render_route(request, '/features/teams/?sub=pending_approvals')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        reg = TeamRegistration.objects.get(id=reg_id)
        if reg.status != 'pending':
            messages.warning(request, f"Registration is already '{reg.status}'.")
            return render_route(request, '/features/teams/?sub=pending_approvals')
        reg.status      = 'approved'
        reg.reviewed_by = request.user
        reg.reviewed_at = timezone.now()
        reg.save()
        reg.refresh_from_db()
        if reg.created_team:
            _finalize_team_admin_approval(reg.created_team, request.user)

        messages.success(request, f"Team '{reg.team_name}' approved. Team record created and admin approval actions completed.")
    except TeamRegistration.DoesNotExist:
        messages.error(request, "Registration not found.")
    except Exception as exc:
        logger.error(f"Approve registration {reg_id}: {exc}", exc_info=True)
        messages.error(request, f"Approval failed: {exc}")
    return render_route(request, '/features/teams/?sub=pending_approvals')


@login_required(login_url='/accounts/')
@require_POST
def admin_approve_live_team(request, team_id):
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team = Team.objects.select_related('hackathon', 'team_leader', 'from_registration').get(id=team_id)
        changed = _finalize_team_admin_approval(team, request.user)
        if changed:
            messages.success(request, f"Team '{team.team_name}' approved by admin. Mentor credentials and team notifications were sent.")
        else:
            registration = getattr(team, 'from_registration', None)
            if registration:
                from mentor.mentor.models import MentorInvitation
                from mentor.mentor.signals import provision_mentor_account
                mentor_invite = MentorInvitation.objects.filter(
                    registration=registration
                ).order_by('-invited_at').first()
                if mentor_invite and mentor_invite.status in ('spoc_pending', 'spoc_approved', 'admin_approved'):
                    if mentor_invite.status != 'admin_approved':
                        mentor_invite.status = 'admin_approved'
                        mentor_invite.admin_decided_at = timezone.now()
                        if not mentor_invite.admin_note:
                            mentor_invite.admin_note = f"Admin approved with team finalization by {request.user.get_username()}."
                        mentor_invite.save(update_fields=['status', 'admin_decided_at', 'admin_note'])
                    provision_mentor_account(mentor_invite, resend_email=True)
                    messages.success(request, f"Mentor credentials were re-sent for team '{team.team_name}'.")
                else:
                    messages.info(request, f"Team '{team.team_name}' is already admin approved.")
            else:
                messages.info(request, f"Team '{team.team_name}' is already admin approved.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        logger.error(f"Admin live team approval {team_id}: {exc}", exc_info=True)
        messages.error(request, f"Admin approval failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def reject_team_registration(request, reg_id):
    if request.method != 'POST':
        return render_route(request, '/features/teams/?sub=pending_approvals')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        from accounts.signals import _send_team_rejection_email
        reg = TeamRegistration.objects.get(id=reg_id)
        note = request.POST.get('rejection_note', '').strip()
        reg.status         = 'rejected'
        reg.reviewed_by    = request.user
        reg.reviewed_at    = timezone.now()
        reg.rejection_note = note
        reg.save()
        try:
            _send_team_rejection_email(reg, note)
        except Exception:
            pass
        messages.success(request, f"Team '{reg.team_name}' registration rejected.")
    except TeamRegistration.DoesNotExist:
        messages.error(request, "Registration not found.")
    except Exception as exc:
        messages.error(request, f"Rejection failed: {exc}")
    return render_route(request, '/features/teams/?sub=pending_approvals')


@login_required(login_url='/accounts/')
def edit_team(request, team_id):
    if request.method != 'POST':
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team = Team.objects.get(id=team_id)
        new_name = request.POST.get('team_name', '').strip()
        if new_name:
            team.team_name = new_name
        ps_id = request.POST.get('problem_statement_id', '').strip()
        if ps_id and ps_id.isdigit():
            ps = ProblemStatement.objects.filter(id=ps_id).first()
            if ps:
                team.problem_statement = ps
        inst_id = request.POST.get('institution_id', '').strip()
        if inst_id and inst_id.isdigit():
            inst = Institution.objects.filter(id=inst_id).first()
            if inst:
                team.institution = inst
        team.save()
        messages.success(request, f"Team '{team.team_name}' updated.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        logger.error(f"Edit team {team_id}: {exc}", exc_info=True)
        messages.error(request, f"Update failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def suspend_team(request, team_id):
    if request.method != 'POST':
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team = Team.objects.get(id=team_id)
        note = request.POST.get('note', '').strip()
        old_status = team.status
        if team.status == 'disqualified':
            team.status = 'spoc_approved'
            word = "reactivated"
        else:
            team.status = 'disqualified'
            word = "suspended"
        team.save()
        TeamStatusLog.objects.create(
            team=team, old_status=old_status, new_status=team.status,
            changed_by=request.user, note=note or f"Admin {word} the team.",
        )
        messages.success(request, f"Team '{team.team_name}' {word}.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        logger.error(f"Suspend team {team_id}: {exc}", exc_info=True)
        messages.error(request, f"Failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def update_team_status(request, team_id):
    if request.method != 'POST':
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team = Team.objects.get(id=team_id)
        new_status = request.POST.get('new_status', '').strip()
        note       = request.POST.get('note', '').strip()
        valid = [s[0] for s in TeamStatusLog.STATUS_CHOICES]
        if new_status not in valid:
            messages.error(request, f"Invalid status: {new_status}")
            return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
        old_status = team.status
        team.status = new_status
        team.save()
        TeamStatusLog.objects.create(
            team=team, old_status=old_status, new_status=new_status,
            changed_by=request.user, note=note,
        )
        messages.success(request, f"Team '{team.team_name}' -> '{new_status}'.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        logger.error(f"Status update team {team_id}: {exc}", exc_info=True)
        messages.error(request, f"Failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def upload_team_document(request, team_id):
    if request.method != 'POST':
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team  = Team.objects.get(id=team_id)
        title = request.POST.get('title', '').strip()
        dtype = request.POST.get('doc_type', 'other')
        f     = request.FILES.get('file')
        if not title or not f:
            messages.error(request, "Title and file are required.")
            return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
        TeamDocument.objects.create(
            team=team, uploaded_by=request.user, doc_type=dtype, title=title, file=f,
        )
        messages.success(request, f"Document '{title}' uploaded.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        messages.error(request, f"Upload failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def delete_team_document(request, doc_id):
    if request.method != 'POST':
        return render_route(request, '/features/teams/?sub=live_teams')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    team_id = request.POST.get('team_id', '')
    try:
        doc = TeamDocument.objects.get(id=doc_id)
        doc.delete()
        messages.success(request, "Document deleted.")
    except TeamDocument.DoesNotExist:
        messages.error(request, "Document not found.")
    except Exception as exc:
        messages.error(request, f"Failed: {exc}")
    if team_id:
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    return render_route(request, '/features/teams/?sub=live_teams')


#  FEATURE 3 : CONTENT MANAGEMENT
# ══════════════════════════════════════════════════════════════

@login_required(login_url='/accounts/')
@never_cache
def content_management(request):
    denied = _feature_permission_required(request, 'problem_statement_content_mgt')
    if denied:
        return denied

    has_publication_scope = _podcast_publication_scope_supported()
    sub              = request.GET.get('sub', 'podcasts')
    query            = request.GET.get('q', '')
    hackathon_filter = request.GET.get('hackathon', '')
    hackathons       = Hackathon.objects.filter(status='Live').order_by('-created_at')

    edit_podcast_id  = request.GET.get('edit_podcast')
    edit_doc_id      = request.GET.get('edit_doc')
    edit_podcast_obj = None
    edit_doc_obj     = None

    podcast_type = request.GET.get('podcast_type', 'podcast').strip().lower()
    if podcast_type not in ['podcast', 'expert_talk']:
        podcast_type = 'podcast'

    if edit_podcast_id and str(edit_podcast_id).isdigit():
        edit_podcast_qs = Podcast.objects.all()
        if not has_publication_scope:
            edit_podcast_qs = edit_podcast_qs.defer('publication_scope')
        edit_podcast_obj = edit_podcast_qs.filter(id=edit_podcast_id).first()
        if edit_podcast_obj:
            podcast_type = edit_podcast_obj.podcast_type
            if not has_publication_scope:
                edit_podcast_obj.publication_scope = 'website' if edit_podcast_obj.is_published else 'draft'
    if edit_doc_id and str(edit_doc_id).isdigit():
        edit_doc_obj = Documentation.objects.filter(id=edit_doc_id).first()

    context = {
        'tab': 'content_mgt', 'sub': sub, 'hackathons': hackathons,
        'q': query, 'hackathon_filter': hackathon_filter,
        'DOC_TYPES': Documentation.DOC_TYPE_CHOICES,
        'landing_section_choices': LANDING_SECTION_CHOICES,
        'edit_podcast_obj': edit_podcast_obj, 'edit_doc_obj': edit_doc_obj,
        'podcast_type': podcast_type,
        'problem_statements': ProblemStatement.objects.filter(
            is_suspended=False).order_by('hackathon__name', 'title'),
    }

    if sub == 'podcasts':
        podcasts = Podcast.objects.select_related(
            'hackathon', 'problem_statement', 'created_by'
        ).filter(podcast_type=podcast_type).order_by('-created_at')
        if not has_publication_scope:
            podcasts = podcasts.defer('publication_scope')
        if query:
            podcasts = podcasts.filter(Q(title__icontains=query) | Q(description__icontains=query))
        if hackathon_filter and hackathon_filter.isdigit():
            podcasts = podcasts.filter(hackathon_id=hackathon_filter)
        paginator = Paginator(podcasts, 12)
        page = request.GET.get('page')
        try:
            context['podcasts'] = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            context['podcasts'] = paginator.page(1)
        if not has_publication_scope:
            for podcast in context['podcasts'].object_list:
                podcast.publication_scope = 'website' if podcast.is_published else 'draft'

    elif sub == 'docs':
        docs = Documentation.objects.select_related(
            'hackathon', 'problem_statement', 'created_by'
        ).order_by('-created_at')
        if query:
            docs = docs.filter(Q(title__icontains=query) | Q(doc_type__icontains=query))
        if hackathon_filter and hackathon_filter.isdigit():
            docs = docs.filter(hackathon_id=hackathon_filter)
        paginator = Paginator(docs, 12)
        page = request.GET.get('page')
        try:
            context['docs'] = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            context['docs'] = paginator.page(1)

    return render(request, 'features/content_management.html', context)


@login_required(login_url='/accounts/')
@require_POST
def create_podcast(request):
    podcast_type = request.POST.get('podcast_type', 'podcast').strip()
    if _feature_permission_required(request, 'problem_statement_content_mgt'):
        return render_route(request, f'/features/content/?sub=podcasts&podcast_type={podcast_type}')
    try:
        has_publication_scope = _podcast_publication_scope_supported()
        hackathon_id = request.POST.get('hackathon_id', '').strip()
        ps_id = request.POST.get('problem_statement_id') or None
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        video_url = request.POST.get('video_url', '').strip()
        landing_sections = _clean_landing_sections(request.POST.getlist('landing_sections'))
        action = request.POST.get('action', 'draft').strip()
        publication_scope = 'draft'
        if action == 'publish_website':
            publication_scope = 'website'
        elif action == 'publish_internal':
            publication_scope = 'internal'
        is_published = publication_scope in ('website', 'internal')
        podcast_id = request.POST.get('podcast_id', '').strip()
        if not title or not hackathon_id:
            messages.error(request, "Title and Hackathon required.")
            return render_route(request, f'/features/content/?sub=podcasts&podcast_type={podcast_type}')
        hackathon = Hackathon.objects.get(id=hackathon_id)
        ps = ProblemStatement.objects.filter(id=ps_id).first() if ps_id and str(ps_id).isdigit() else None
        if podcast_id and podcast_id.isdigit():
            p = Podcast.objects.get(id=podcast_id)
            p.hackathon = hackathon; p.problem_statement = ps; p.title = title
            p.description = description; p.video_url = video_url; p.is_published = is_published
            p.landing_sections = landing_sections
            p.podcast_type = podcast_type
            if has_publication_scope:
                p.publication_scope = publication_scope
            if 'thumbnail' in request.FILES:
                p.thumbnail = request.FILES['thumbnail']
            if 'video_file' in request.FILES:
                p.video_file = request.FILES['video_file']
            p.save()
            messages.success(request, f'Podcast "{title}" updated.')
        else:
            podcast_kwargs = {
                'hackathon': hackathon,
                'problem_statement': ps,
                'title': title,
                'description': description,
                'video_url': video_url,
                'is_published': is_published,
                'created_by': request.user,
                'landing_sections': landing_sections,
                'podcast_type': podcast_type,
            }
            if has_publication_scope:
                podcast_kwargs['publication_scope'] = publication_scope
            p = Podcast(**podcast_kwargs)
            if 'thumbnail' in request.FILES:
                p.thumbnail = request.FILES['thumbnail']
            if 'video_file' in request.FILES:
                p.video_file = request.FILES['video_file']
            p.save()
            if publication_scope == 'website':
                messages.success(request, f'Podcast "{title}" published to website.')
            elif publication_scope == 'internal':
                messages.success(request, f'Podcast "{title}" published to internal community.')
            else:
                messages.success(request, f'Podcast "{title}" saved as draft.')
    except Exception as exc:
        logger.error(f"Podcast save: {exc}", exc_info=True)
        messages.error(request, f"Error: {exc}")
    return render_route(request, f'/features/content/?sub=podcasts&podcast_type={podcast_type}')


@login_required(login_url='/accounts/')
@require_POST
def delete_podcast(request, podcast_id):
    if _feature_permission_required(request, 'problem_statement_content_mgt'):
        return render_route(request, '/features/content/?sub=podcasts')
    podcast_type = 'podcast'
    try:
        p = Podcast.objects.get(id=podcast_id)
        title = p.title
        podcast_type = p.podcast_type
        p.delete()
        messages.success(request, f'Podcast "{title}" deleted.')
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return render_route(request, f'/features/content/?sub=podcasts&podcast_type={podcast_type}')


@login_required(login_url='/accounts/')
@require_POST
def suspend_podcast(request, podcast_id):
    if _feature_permission_required(request, 'problem_statement_content_mgt'):
        return render_route(request, '/features/content/?sub=podcasts')
    podcast_type = 'podcast'
    try:
        p = Podcast.objects.get(id=podcast_id)
        podcast_type = p.podcast_type
        p.is_published = not p.is_published
        p.save()
        messages.success(request, f'Podcast "{p.title}" {"published" if p.is_published else "suspended"}.')
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return render_route(request, f'/features/content/?sub=podcasts&podcast_type={podcast_type}')


@login_required(login_url='/accounts/')
@require_POST
def create_documentation(request):
    if _feature_permission_required(request, 'problem_statement_content_mgt'):
        return render_route(request, '/features/content/?sub=docs')
    try:
        hackathon_id = request.POST.get('hackathon_id', '').strip()
        ps_id = request.POST.get('problem_statement_id') or None
        title = request.POST.get('title', '').strip()
        doc_type = request.POST.get('doc_type', 'other')
        description = request.POST.get('description', '').strip()
        external_url = request.POST.get('external_url', '').strip()
        landing_sections = _clean_landing_sections(request.POST.getlist('landing_sections'))
        is_published = request.POST.get('action') == 'publish'
        doc_id = request.POST.get('doc_id', '').strip()
        if not title or not hackathon_id:
            messages.error(request, "Title and Hackathon required.")
            return render_route(request, '/features/content/?sub=docs')
        hackathon = Hackathon.objects.get(id=hackathon_id)
        ps = ProblemStatement.objects.filter(id=ps_id).first() if ps_id and str(ps_id).isdigit() else None
        if doc_id and doc_id.isdigit():
            d = Documentation.objects.get(id=doc_id)
            d.hackathon = hackathon; d.problem_statement = ps
            d.title = title; d.doc_type = doc_type; d.description = description
            d.external_url = external_url; d.is_published = is_published
            d.landing_sections = landing_sections
            if 'file' in request.FILES:
                d.file = request.FILES['file']
            d.save()
            messages.success(request, f'Documentation "{title}" updated.')
        else:
            d = Documentation(hackathon=hackathon, problem_statement=ps, title=title,
                              doc_type=doc_type, description=description,
                              external_url=external_url, is_published=is_published,
                              created_by=request.user,
                              landing_sections=landing_sections)
            if 'file' in request.FILES:
                d.file = request.FILES['file']
            d.save()
            messages.success(request, f'Documentation "{title}" {"published" if is_published else "saved"}.')
    except Exception as exc:
        logger.error(f"Doc save: {exc}", exc_info=True)
        messages.error(request, f"Error: {exc}")
    return render_route(request, '/features/content/?sub=docs')


@login_required(login_url='/accounts/')
@require_POST
def delete_documentation(request, doc_id):
    if _feature_permission_required(request, 'problem_statement_content_mgt'):
        return render_route(request, '/features/content/?sub=docs')
    try:
        d = Documentation.objects.get(id=doc_id)
        title = d.title
        d.delete()
        messages.success(request, f'Documentation "{title}" deleted.')
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return render_route(request, '/features/content/?sub=docs')


@login_required(login_url='/accounts/')
@require_POST
def suspend_documentation(request, doc_id):
    if _feature_permission_required(request, 'problem_statement_content_mgt'):
        return render_route(request, '/features/content/?sub=docs')
    try:
        d = Documentation.objects.get(id=doc_id)
        d.is_published = not d.is_published
        d.save()
        messages.success(request, f'Documentation "{d.title}" {"published" if d.is_published else "suspended"}.')
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return render_route(request, '/features/content/?sub=docs')


@login_required(login_url='/accounts/')
@require_POST
def toggle_ps_publish(request, ps_id):
    if _feature_permission_required(request, 'problem_statement_content_mgt'):
        return render_route(request, '/features/content/?sub=podcasts')
    try:
        ps = ProblemStatement.objects.get(id=ps_id)
        ps.is_published = not ps.is_published
        ps.save()
        messages.success(request, f'Problem Statement "{ps.title}" {"published" if ps.is_published else "unpublished"}.')
    except Exception as exc:
        messages.error(request, f"Error: {exc}")
    return render_route(request, '/features/content/?sub=podcasts')


# ══════════════════════════════════════════════════════════════
#  FEATURE 4 : VENUE & LOGISTICS MANAGEMENT
# ══════════════════════════════════════════════════════════════

FACILITY_CHOICES = [
    'Stage', 'Audio System', 'Sitting Arrangement',
    'Stay/Accommodation', 'Refreshment', 'Conference Hall',
    'Event Hall', 'Registration Desk', 'Fooding',
    'Main Gate Security', 'High Speed Internet', 'Power Backup',
    'Volunteer Support', 'Projector & Screen', 'Medical Aid',
    'Parking Area', 'CCTV Surveillance', 'Green Room',
]


@login_required(login_url='/accounts/')
def save_venue(request):
    """Create or update a Venue record."""
    denied = _feature_permission_required(request, 'venue_logistics_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/venue/?sub=venues')

    hackathon_id = request.POST.get('hackathon_id')
    venue_id     = request.POST.get('venue_id')
    venue_name   = request.POST.get('venue_name', '').strip()
    location     = request.POST.get('location', '').strip()
    capacity_raw = request.POST.get('capacity', '').strip()
    landmark     = request.POST.get('landmark', '').strip()
    contact_det  = request.POST.get('contact_details', '').strip()
    event_date   = request.POST.get('event_date', '').strip()
    facilities   = request.POST.getlist('facilities')

    redirect_url = f'/features/venue/?sub=venues&hackathon={hackathon_id}'

    if not venue_name or not hackathon_id:
        messages.error(request, "Venue name and hackathon are required.")
        return render_route(request, redirect_url)

    try:
        capacity = int(capacity_raw) if capacity_raw else None
        if venue_id:
            venue = Venue.objects.get(id=venue_id)
            venue.venue_name      = venue_name
            venue.location        = location
            venue.capacity        = capacity
            venue.landmark        = landmark
            venue.contact_details = contact_det
            venue.event_date      = event_date
            venue.facilities      = facilities
            venue.save()
            messages.success(request, f'Venue "{venue_name}" updated successfully.')
        else:
            Venue.objects.create(
                hackathon_id=hackathon_id,
                venue_name=venue_name,
                location=location,
                capacity=capacity,
                landmark=landmark,
                contact_details=contact_det,
                event_date=event_date,
                facilities=facilities,
            )
            messages.success(request, f'Venue "{venue_name}" added successfully.')
    except Exception as exc:
        logger.error(f'save_venue error: {exc}', exc_info=True)
        messages.error(request, f'Error: {exc}')
    return render_route(request, redirect_url)


@login_required(login_url='/accounts/')
@never_cache
def view_venue(request, venue_id):
    """View venue details page."""
    denied = _feature_permission_required(request, 'venue_logistics_mgt')
    if denied:
        return denied
    venue = get_object_or_404(Venue.objects.select_related('hackathon'), id=venue_id)
    hackathon_filter = str(venue.hackathon_id)
    return render(request, 'features/venue_logistics.html', {
        'tab': 'venue_logistics',
        'sub': 'venue_detail',
        'venue': venue,
        'facility_choices': FACILITY_CHOICES,
        'hackathon_filter': hackathon_filter,
        'active_hackathon': venue.hackathon,
        'hackathons': Hackathon.objects.exclude(status='Suspended').order_by('-created_at'),
    })


@login_required(login_url='/accounts/')
def suspend_venue(request, venue_id):
    """Toggle Active / Suspended status for a Venue."""
    denied = _feature_permission_required(request, 'venue_logistics_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/venue/?sub=venues')
    try:
        venue = Venue.objects.get(id=venue_id)
        if venue.status == 'Active':
            venue.status = 'Suspended'
            word = 'suspended'
        else:
            venue.status = 'Active'
            word = 'activated'
        venue.save(update_fields=['status'])
        messages.success(request, f'Venue "{venue.venue_name}" {word}.')
    except Venue.DoesNotExist:
        messages.error(request, 'Venue not found.')
    except Exception as exc:
        messages.error(request, f'Error: {exc}')
    hackathon_id = request.POST.get('hackathon_id', '')
    return render_route(request, f'/features/venue/?sub=venues&hackathon={hackathon_id}')


@login_required(login_url='/accounts/')
@never_cache
def venue_logistics_management(request):
    denied = _feature_permission_required(request, 'venue_logistics_mgt')
    if denied:
        return denied

    sub = request.GET.get('sub', 'venues')
    hackathons = Hackathon.objects.exclude(status='Suspended').order_by('-created_at')
    hackathon_filter = request.GET.get('hackathon', '')

    active_hackathon = None
    if hackathon_filter and hackathon_filter.isdigit():
        active_hackathon = Hackathon.objects.filter(id=hackathon_filter).first()
    else:
        active_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
        if active_hackathon:
            hackathon_filter = str(active_hackathon.id)

    context = {
        'tab': 'venue_logistics',
        'sub': sub,
        'hackathons': hackathons,
        'hackathon_filter': hackathon_filter,
        'active_hackathon': active_hackathon,
        'facility_choices': FACILITY_CHOICES,
    }

    if active_hackathon:
        all_venues = Venue.objects.filter(hackathon=active_hackathon)
        context['venues'] = all_venues
        if sub == 'venues':
            pass  # venues already in context
        elif sub == 'allocation':
            context['allocations'] = VenueAllocation.objects.filter(hackathon=active_hackathon)
        elif sub == 'logistics':
            context['logistics'] = LogisticsPlan.objects.filter(hackathon=active_hackathon)
        elif sub == 'food':
            context['food'] = VenueFoodRefreshment.objects.filter(venue__in=all_venues)
        elif sub == 'volunteers':
            context['volunteers'] = VolunteerAssignment.objects.filter(hackathon=active_hackathon)

    return render(request, 'features/venue_logistics.html', context)


@login_required(login_url='/accounts/')
def save_venue_allocation(request):
    denied = _feature_permission_required(request, 'venue_logistics_mgt')
    if denied:
        return denied
    if request.method == 'POST':
        hackathon_id = request.POST.get('hackathon_id')
        venue_id = request.POST.get('venue_id')
        status = request.POST.get('status', 'Pending')
        allocated_date = request.POST.get('allocated_date') or None

        if not hackathon_id or not venue_id:
            messages.error(request, "Hackathon and Venue are required.")
            return render_route(request, '/features/venue/')

        alloc_id = request.POST.get('alloc_id')
        try:
            if alloc_id:
                alloc = VenueAllocation.objects.get(id=alloc_id)
                alloc.status = status
                alloc.allocated_date = allocated_date
                if 'confirmation_letter' in request.FILES:
                    alloc.confirmation_letter = request.FILES['confirmation_letter']
                alloc.save()
                messages.success(request, "Venue Allocation updated.")
            else:
                alloc = VenueAllocation.objects.create(
                    hackathon_id=hackathon_id, venue_id=venue_id,
                    status=status, allocated_date=allocated_date
                )
                if 'confirmation_letter' in request.FILES:
                    alloc.confirmation_letter = request.FILES['confirmation_letter']
                    alloc.save()
                messages.success(request, "Venue Allocation created.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render_route(request, '/features/venue/?sub=allocation&hackathon=' + str(request.POST.get('hackathon_id', '')))


@login_required(login_url='/accounts/')
def save_logistics(request):
    denied = _feature_permission_required(request, 'venue_logistics_mgt')
    if denied:
        return denied
    if request.method == 'POST':
        hackathon_id = request.POST.get('hackathon_id')
        plan_name = request.POST.get('plan_name')
        description = request.POST.get('description', '')
        infrastructure_readiness = request.POST.get('infrastructure_readiness', 0)
        logistics_id = request.POST.get('logistics_id')
        try:
            if logistics_id:
                log = LogisticsPlan.objects.get(id=logistics_id)
                log.plan_name = plan_name
                log.description = description
                log.infrastructure_readiness = infrastructure_readiness
                log.save()
                messages.success(request, "Logistics Plan updated.")
            else:
                LogisticsPlan.objects.create(
                    hackathon_id=hackathon_id, plan_name=plan_name,
                    description=description, infrastructure_readiness=infrastructure_readiness
                )
                messages.success(request, "Logistics Plan created.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render_route(request, '/features/venue/?sub=logistics&hackathon=' + str(request.POST.get('hackathon_id', '')))


@login_required(login_url='/accounts/')
def save_food_refreshment(request):
    denied = _feature_permission_required(request, 'venue_logistics_mgt', 'accommodation_health_mgt')
    if denied:
        return denied
    if request.method == 'POST':
        venue_id = request.POST.get('venue_id')
        vendor_name = request.POST.get('vendor_name')
        contact_info = request.POST.get('contact_info', '')
        menu_details = request.POST.get('menu_details', '')
        headcount = request.POST.get('headcount_estimation', 0)
        cost = request.POST.get('cost_estimation', 0)
        food_id = request.POST.get('food_id')
        try:
            if food_id:
                f = VenueFoodRefreshment.objects.get(id=food_id)
                f.vendor_name = vendor_name; f.contact_info = contact_info
                f.menu_details = menu_details; f.headcount_estimation = headcount
                f.cost_estimation = cost; f.save()
                messages.success(request, "Food & Refreshment details updated.")
            else:
                VenueFoodRefreshment.objects.create(
                    venue_id=venue_id, vendor_name=vendor_name, contact_info=contact_info,
                    menu_details=menu_details, headcount_estimation=headcount, cost_estimation=cost
                )
                messages.success(request, "Food & Refreshment details added.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render_route(request, '/features/venue/?sub=food&hackathon=' + str(request.POST.get('hackathon_id', '')))


@login_required(login_url='/accounts/')
def save_volunteer(request):
    denied = _feature_permission_required(request, 'venue_logistics_mgt')
    if denied:
        return denied
    if request.method == 'POST':
        hackathon_id = request.POST.get('hackathon_id')
        volunteer_name = request.POST.get('volunteer_name')
        contact_number = request.POST.get('contact_number')
        role_description = request.POST.get('role_description')
        assigned_venue_id = request.POST.get('assigned_venue_id') or None
        status = request.POST.get('status', 'Active')
        vol_id = request.POST.get('vol_id')
        try:
            if vol_id:
                v = VolunteerAssignment.objects.get(id=vol_id)
                v.volunteer_name = volunteer_name; v.contact_number = contact_number
                v.role_description = role_description; v.assigned_venue_id = assigned_venue_id
                v.status = status; v.save()
                messages.success(request, "Volunteer Assignment updated.")
            else:
                VolunteerAssignment.objects.create(
                    hackathon_id=hackathon_id, volunteer_name=volunteer_name,
                    contact_number=contact_number, role_description=role_description,
                    assigned_venue_id=assigned_venue_id, status=status
                )
                messages.success(request, "Volunteer Assignment created.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render_route(request, '/features/venue/?sub=volunteers&hackathon=' + str(request.POST.get('hackathon_id', '')))


# ══════════════════════════════════════════════════════════════
#  FEATURE 5 : FINANCIAL MANAGEMENT
# ══════════════════════════════════════════════════════════════

@login_required(login_url='/accounts/')
@never_cache
def finance_management(request):
    denied = _feature_permission_required(request, 'financial_mgt', 'media_sponsorship_mgt', 'reporting_result_mgt', 'awards_certification_mgt')
    if denied:
        return denied

    sub = request.GET.get('sub', 'budget')
    hackathons = Hackathon.objects.exclude(status='Suspended').order_by('-created_at')
    hackathon_filter = request.GET.get('hackathon', '')

    active_hackathon = None
    if hackathon_filter and hackathon_filter.isdigit():
        active_hackathon = Hackathon.objects.filter(id=hackathon_filter).first()
    else:
        active_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
        if active_hackathon:
            hackathon_filter = str(active_hackathon.id)

    context = {
        'tab': 'finance',
        'sub': sub,
        'hackathons': hackathons,
        'hackathon_filter': hackathon_filter,
        'active_hackathon': active_hackathon,
    }

    if active_hackathon:
        if sub == 'budget':
            context['budgets'] = EventBudget.objects.filter(hackathon=active_hackathon)
        elif sub == 'sponsorships':
            context['sponsorships'] = SponsorshipFund.objects.filter(hackathon=active_hackathon)
        elif sub == 'transactions':
            context['transactions'] = FinancialTransaction.objects.filter(
                hackathon=active_hackathon).order_by('-transaction_date')
            context['categories'] = FinancialTransaction.CATEGORY_CHOICES
        elif sub == 'reports':
            total_budget  = EventBudget.objects.filter(hackathon=active_hackathon).aggregate(total=Sum('total_budget'))['total'] or 0
            total_sponsor = SponsorshipFund.objects.filter(hackathon=active_hackathon).aggregate(total=Sum('amount_received'))['total'] or 0
            total_income  = FinancialTransaction.objects.filter(hackathon=active_hackathon, transaction_type='Income').aggregate(total=Sum('amount'))['total'] or 0
            total_expense = FinancialTransaction.objects.filter(hackathon=active_hackathon, transaction_type='Expense').aggregate(total=Sum('amount'))['total'] or 0
            category_expenses = FinancialTransaction.objects.filter(
                hackathon=active_hackathon, transaction_type='Expense'
            ).values('category').annotate(total=Sum('amount')).order_by('-total')
            context['report'] = {
                'total_budget': total_budget, 'total_sponsor': total_sponsor,
                'total_income': total_income, 'total_expense': total_expense,
                'net_balance': total_budget + total_sponsor + total_income - total_expense,
                'category_expenses': category_expenses,
            }

    return render(request, 'features/finance_management.html', context)


@login_required(login_url='/accounts/')
def save_budget(request):
    denied = _feature_permission_required(request, 'financial_mgt')
    if denied:
        return denied
    if request.method == 'POST':
        hackathon_id = request.POST.get('hackathon_id')
        total_budget = request.POST.get('total_budget', 0)
        allocated_budget = request.POST.get('allocated_budget', 0)
        notes = request.POST.get('notes', '')
        budget_id = request.POST.get('budget_id')
        try:
            if budget_id:
                b = EventBudget.objects.get(id=budget_id)
                b.total_budget = total_budget; b.allocated_budget = allocated_budget
                b.notes = notes; b.save()
                messages.success(request, "Budget updated.")
            else:
                EventBudget.objects.create(
                    hackathon_id=hackathon_id, total_budget=total_budget,
                    allocated_budget=allocated_budget, notes=notes
                )
                messages.success(request, "Budget created.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render_route(request, '/features/finance/?sub=budget&hackathon=' + str(request.POST.get('hackathon_id', '')))


@login_required(login_url='/accounts/')
def save_sponsorship(request):
    denied = _feature_permission_required(request, 'financial_mgt', 'media_sponsorship_mgt')
    if denied:
        return denied
    if request.method == 'POST':
        hackathon_id = request.POST.get('hackathon_id')
        sponsor_name = request.POST.get('sponsor_name')
        amount_pledged = request.POST.get('amount_pledged', 0)
        amount_received = request.POST.get('amount_received', 0)
        status = request.POST.get('status', 'Pending')
        date_received = request.POST.get('date_received') or None
        sponsor_id = request.POST.get('sponsor_id')
        try:
            if sponsor_id:
                s = SponsorshipFund.objects.get(id=sponsor_id)
                s.sponsor_name = sponsor_name; s.amount_pledged = amount_pledged
                s.amount_received = amount_received; s.status = status
                s.date_received = date_received; s.save()
                messages.success(request, "Sponsorship Fund updated.")
            else:
                SponsorshipFund.objects.create(
                    hackathon_id=hackathon_id, sponsor_name=sponsor_name,
                    amount_pledged=amount_pledged, amount_received=amount_received,
                    status=status, date_received=date_received
                )
                messages.success(request, "Sponsorship Fund created.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render_route(request, '/features/finance/?sub=sponsorships&hackathon=' + str(request.POST.get('hackathon_id', '')))


@login_required(login_url='/accounts/')
@require_POST
def delete_sponsorship(request, sponsor_id):
    denied = _feature_permission_required(request, 'financial_mgt', 'media_sponsorship_mgt')
    if denied:
        return denied
    s = get_object_or_404(SponsorshipFund, id=sponsor_id)
    hackathon_id = s.hackathon_id
    s.delete()
    messages.success(request, "Sponsorship Fund deleted.")
    return render_route(request, '/features/finance/?sub=sponsorships&hackathon=' + str(hackathon_id))


@login_required(login_url='/accounts/')
def save_transaction(request):
    denied = _feature_permission_required(request, 'financial_mgt')
    if denied:
        return denied
    if request.method == 'POST':
        hackathon_id = request.POST.get('hackathon_id')
        transaction_type = request.POST.get('transaction_type')
        category = request.POST.get('category')
        amount = request.POST.get('amount')
        transaction_date = request.POST.get('transaction_date')
        description = request.POST.get('description', '')
        tx_id = request.POST.get('tx_id')
        try:
            if tx_id:
                tx = FinancialTransaction.objects.get(id=tx_id)
                tx.transaction_type = transaction_type; tx.category = category
                tx.amount = amount; tx.transaction_date = transaction_date
                tx.description = description
                if 'receipt_file' in request.FILES:
                    tx.receipt_file = request.FILES['receipt_file']
                tx.save()
                messages.success(request, "Transaction updated.")
            else:
                tx = FinancialTransaction.objects.create(
                    hackathon_id=hackathon_id, transaction_type=transaction_type,
                    category=category, amount=amount, transaction_date=transaction_date,
                    description=description, processed_by=request.user
                )
                if 'receipt_file' in request.FILES:
                    tx.receipt_file = request.FILES['receipt_file']
                    tx.save()
                messages.success(request, "Transaction created.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render_route(request, '/features/finance/?sub=transactions&hackathon=' + str(request.POST.get('hackathon_id', '')))


@login_required(login_url='/accounts/')
@never_cache
def support_operations_management(request):
    denied = _feature_permission_required(request, 'feedback_support_mgt', 'accommodation_health_mgt')
    if denied:
        return denied

    from team.team.models import TeamSupportMessage, TeamTravelDetail

    focus = request.GET.get('focus', 'support')
    query = request.GET.get('q', '').strip()
    support_filter = request.GET.get('status', '').strip()

    support_messages = TeamSupportMessage.objects.select_related(
        'registration__hackathon', 'registration__institution', 'sender'
    ).order_by('-updated_at')
    if query:
        support_messages = support_messages.filter(
            Q(subject__icontains=query) |
            Q(message__icontains=query) |
            Q(registration__team_name__icontains=query)
        )
    if support_filter:
        support_messages = support_messages.filter(status=support_filter)

    context = _feature_context(
        request,
        tab='support_ops',
        focus=focus,
        q=query,
        support_filter=support_filter,
        support_messages=support_messages,
        support_statuses=TeamSupportMessage.STATUS_CHOICES,
        support_counts={
            'open': support_messages.filter(status='open').count(),
            'reviewed': support_messages.filter(status='reviewed').count(),
            'resolved': support_messages.filter(status='resolved').count(),
        },
        travel_details=TeamTravelDetail.objects.select_related(
            'registration__hackathon', 'registration__institution', 'submitted_by'
        ).order_by('-journey_date', '-created_at'),
        health_related_messages=support_messages.filter(category__in=['health', 'venue', 'logistics']),
        food_records=VenueFoodRefreshment.objects.select_related('venue', 'venue__hackathon').order_by('-id')[:20],
    )
    return render(request, 'features/support_operations.html', context)


@login_required(login_url='/accounts/')
@require_POST
def update_support_message(request, message_id):
    denied = _feature_permission_required(request, 'feedback_support_mgt', 'accommodation_health_mgt')
    if denied:
        return denied

    from team.team.models import TeamSupportMessage, TeamNotification

    support_message = get_object_or_404(TeamSupportMessage, id=message_id)
    support_message.status = request.POST.get('status', support_message.status)
    reply_text = request.POST.get('admin_reply', '').strip()
    if reply_text:
        support_message.admin_reply = f"[Admin Response]: {reply_text}"
    support_message.save(update_fields=['status', 'admin_reply', 'updated_at'])

    # Send TeamNotification to Team Leader
    if support_message.registration and support_message.registration.team_leader:
        try:
            TeamNotification.objects.create(
                team_leader=support_message.registration.team_leader,
                registration=support_message.registration,
                notif_type='system',
                title=f"Reply from Admin on '{support_message.subject}'",
                body=f"Response: {reply_text or 'Status updated to ' + support_message.status}",
            )
        except Exception as e:
            logger.error(f"Failed to create TeamNotification: {e}")

    messages.success(request, f'Support message "{support_message.subject}" updated and team notified.')
    return render_route(request, '/features/support/?focus=support')



# ══════════════════════════════════════════════════════════════
#  FEATURE 6 : JURY & EVALUATION MANAGEMENT
# ══════════════════════════════════════════════════════════════

def _send_jury_invite_email(email, form_link, hackathon=None):
    hn = hackathon.name if hackathon else "our upcoming Hackathon"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:540px;margin:0 auto;padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
        <h2 style="color:#7c3aed;">You've Been Selected as a Jury Member 🎉</h2>
        <p>You have been invited to serve as a <strong>Jury Member</strong> for <strong>{hn}</strong>.</p>
        <p>Please complete your registration using the link below:</p>
        <a href="{form_link}" style="background:#7c3aed;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;display:inline-block;margin:16px 0;">
            Complete Jury Registration →
        </a>
        <p style="color:#6b7280;font-size:13px;margin-top:20px;">This link is unique to you. Do not share it.</p>
    </div>"""
    msg = EmailMultiAlternatives(
        f"Jury Invitation — {hn}",
        f"Register here: {form_link}",
        settings.DEFAULT_FROM_EMAIL, [email]
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)

def _send_expert_invite_email(email, form_link, hackathon=None):
    hn = hackathon.name if hackathon else "our upcoming Hackathon"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:540px;margin:0 auto;padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
        <h2 style="color:#ea580c;">You've Been Selected as an Expert Member 🎉</h2>
        <p>You have been invited to serve as an <strong>Expert Member</strong> for <strong>{hn}</strong>.</p>
        <p>Please complete your registration using the link below:</p>
        <a href="{form_link}" style="background:#ea580c;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;display:inline-block;margin:16px 0;">
            Complete Expert Registration →
        </a>
        <p style="color:#6b7280;font-size:13px;margin-top:20px;">This link is unique to you. Do not share it.</p>
    </div>"""
    msg = EmailMultiAlternatives(
        f"Expert Invitation — {hn}",
        f"Register here: {form_link}",
        settings.DEFAULT_FROM_EMAIL, [email]
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


def _send_jury_welcome_email(user, password, hackathon=None):
    hn = hackathon.name if hackathon else "the Hackathon"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:540px;margin:0 auto;padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
        <h2 style="color:#059669;">Welcome, {user.get_full_name() or user.username}!</h2>
        <p>Your jury account for <strong>{hn}</strong> has been approved.</p>
        <table style="background:#f9fafb;padding:16px;border-radius:8px;width:100%;margin:16px 0;">
            <tr><td style="font-weight:700;padding:4px 8px;">Username:</td><td style="padding:4px 8px;font-family:monospace;">{user.username}</td></tr>
            <tr><td style="font-weight:700;padding:4px 8px;">Password:</td><td style="padding:4px 8px;font-family:monospace;">{password}</td></tr>
        </table>
        <p style="color:#dc2626;font-size:13px;font-weight:700;">Please change your password after first login.</p>
    </div>"""
    msg = EmailMultiAlternatives(
        f"Jury Account Approved — {hn}",
        f"Username: {user.username}  |  Password: {password}",
        settings.DEFAULT_FROM_EMAIL, [user.email]
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=True)


def sync_automatic_team_assignments(hackathon, round_number=None):
    """
    Automatically maps student Teams to JuryTeams based on their Problem Statement.
    If multiple panels (JuryTeams) exist for the same Problem Statement in a round,
    student teams are distributed equally (round-robin) among those panels.
    Sets TeamEvaluationAssignment for each team according to its assigned panel's evaluators.
    """
    if not hackathon:
        return
    from .models import TeamEvaluationAssignment, Team
    from events.models import JuryTeam

    rounds = [round_number] if round_number else list(range(1, (hackathon.number_of_rounds or 5) + 1))

    for r in rounds:
        student_teams = list(Team.objects.filter(
            hackathon=hackathon,
            current_round=r
        ).exclude(status='disqualified').select_related('problem_statement').order_by('id'))

        jury_teams_for_round = JuryTeam.objects.filter(
            hackathon=hackathon, round_number=r
        ).select_related('problem_statement').prefetch_related('juries', 'experts').order_by('display_order', 'id')

        # Group panels by problem statement
        ps_to_panels = {}
        for jt in jury_teams_for_round:
            if jt.problem_statement_id:
                ps_to_panels.setdefault(jt.problem_statement_id, []).append(jt)

        # Group teams by problem statement
        ps_to_teams = {}
        for team in student_teams:
            if team.problem_statement_id:
                ps_to_teams.setdefault(team.problem_statement_id, []).append(team)

        processed_team_ids = set()

        from events.models import RoundJuryConfig
        round_config = RoundJuryConfig.objects.filter(hackathon=hackathon, round_number=r).first()
        offset = round_config.alter_offset if round_config else 0
        alter = round_config.alter_assignment if round_config else False

        # Distribute teams equally among panels for each PS
        for ps_id, panels in ps_to_panels.items():
            teams_for_ps = ps_to_teams.get(ps_id, [])
            num_panels = len(panels)
            if num_panels > 1:
                if offset > 0:
                    shift = offset % num_panels
                    panels = panels[shift:] + panels[:shift]
                elif alter:
                    panels = list(reversed(panels))
            for idx, team in enumerate(teams_for_ps):
                processed_team_ids.add(team.id)
                jt = panels[idx % num_panels] if num_panels > 0 else None
                assignment, _ = TeamEvaluationAssignment.objects.get_or_create(team=team, round_number=r)

                if jt:
                    j_list = list(jt.juries.all())
                    e_list = list(jt.experts.all())
                    assignment.assigned_panel = jt
                    assignment.jury_1 = j_list[0] if len(j_list) > 0 else None
                    assignment.jury_2 = j_list[1] if len(j_list) > 1 else None
                    assignment.jury_3 = j_list[2] if len(j_list) > 2 else None
                    assignment.expert_1 = e_list[0] if len(e_list) > 0 else None
                    assignment.expert_2 = e_list[1] if len(e_list) > 1 else None
                    assignment.status = 'Assigned' if (assignment.jury_1 and assignment.expert_1) else 'Pending'
                else:
                    assignment.assigned_panel = None
                    assignment.jury_1 = None
                    assignment.jury_2 = None
                    assignment.jury_3 = None
                    assignment.expert_1 = None
                    assignment.expert_2 = None
                    assignment.status = 'Pending'

                assignment.save()

        # Reset teams that do not have a matching panel or PS
        unassigned_teams = [t for t in student_teams if t.id not in processed_team_ids]
        for team in unassigned_teams:
            assignment, _ = TeamEvaluationAssignment.objects.get_or_create(team=team, round_number=r)
            assignment.assigned_panel = None
            assignment.jury_1 = None
            assignment.jury_2 = None
            assignment.jury_3 = None
            assignment.expert_1 = None
            assignment.expert_2 = None
            assignment.status = 'Pending'
            assignment.save()


@login_required(login_url='/accounts/')
@never_cache
def jury_management(request):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt', 'evaluation_coordination')
    if denied:
        return denied

    hackathons, hackathon_filter, active_hackathon = _resolve_hackathon_scope(request)
    sub   = request.GET.get('sub', 'invitations')
    query = request.GET.get('q', '').strip()

    # ── Invitations sub-tab (Jury & Expert) ──
    invitations = JuryInvitation.objects.select_related(
        'invited_by', 'hackathon', 'approved_by', 'created_user'
    ).order_by('-invited_at')
    
    from accounts.models import ExpertInvitation, ExpertProfile
    expert_invitations = ExpertInvitation.objects.select_related(
        'invited_by', 'hackathon', 'approved_by', 'created_user'
    ).order_by('-invited_at')

    if query and (sub == 'invitations' or sub == 'expert_invitations'):
        invitations = invitations.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(organization__icontains=query)
        )
        expert_invitations = expert_invitations.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(organization__icontains=query)
        )

    # ── Jury Roster sub-tab ──
    from django.db.models import Count
    juries = JuryProfile.objects.select_related('user').annotate(
        assigned_teams_count=Count('assignments_as_jury1', distinct=True) + 
                             Count('assignments_as_jury2', distinct=True) + 
                             Count('assignments_as_jury3', distinct=True)
    ).order_by('-user__date_joined')
    if query and sub == 'jury_roster':
        juries = juries.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(domain__icontains=query)
        )

    # ── Expert Roster sub-tab ──
    experts = ExpertProfile.objects.select_related('user').annotate(
        assigned_teams_count=Count('assignments_as_expert1', distinct=True) + 
                             Count('assignments_as_expert2', distinct=True)
    ).order_by('-user__date_joined')
    if query and sub == 'expert_roster':
        experts = experts.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(domain__icontains=query)
        )

    # ── Evaluation sub-tab ──
    focus = request.GET.get('focus', 'parameters')
    parameters = RoundMarkingParameter.objects.none()
    teams_for_eval = Team.objects.none()
    registration_counts = {}
    problem_statements = ProblemStatement.objects.none()
    jury_teams_data = []
    round_jury_config = None
    selected_round = 1
    panels_summary = []
    ps_filter = request.GET.get('problem_statement', '').strip()
    selected_ps_id = int(ps_filter) if ps_filter.isdigit() else None
    panels_saved = request.GET.get('panels_saved') == 'true'
    show_assignments = request.GET.get('show_assignments') == 'true'

    try:
        selected_round = int(request.GET.get('round_number', active_hackathon.active_round['number'] if (active_hackathon and active_hackathon.active_round) else 1))
    except (ValueError, TypeError):
        selected_round = 1

    if active_hackathon:
        max_rounds = max(active_hackathon.number_of_rounds or 1, 5)
        if selected_round > max_rounds or selected_round < 1:
            selected_round = 1

        sync_automatic_team_assignments(active_hackathon, selected_round)

        problem_statements = ProblemStatement.objects.filter(hackathon=active_hackathon, is_suspended=False).order_by('title')
        from events.models import RoundJuryConfig, JuryTeam
        round_jury_config = RoundJuryConfig.objects.filter(hackathon=active_hackathon, round_number=selected_round).first()
        if not round_jury_config:
            round_jury_config = RoundJuryConfig.objects.create(
                hackathon=active_hackathon,
                round_number=selected_round,
                num_jury_per_team=1,
                num_experts_per_team=1,
            )

        all_jury_teams_in_round = list(JuryTeam.objects.filter(
            hackathon=active_hackathon, round_number=selected_round
        ).select_related('problem_statement').prefetch_related('juries', 'experts').order_by('display_order', 'id'))

        # Filter panels displayed if PS filter is active
        displayed_panels = all_jury_teams_in_round
        if selected_ps_id:
            displayed_panels = [p for p in all_jury_teams_in_round if p.problem_statement_id == selected_ps_id]

        # Find all assigned juries and experts across ALL panels in this round
        all_assigned_jury_ids = set()
        all_assigned_expert_ids = set()
        for jt in all_jury_teams_in_round:
            for j in jt.juries.all():
                all_assigned_jury_ids.add(j.id)
            for e in jt.experts.all():
                all_assigned_expert_ids.add(e.id)

        all_juries = list(JuryProfile.objects.select_related('user').filter(user__is_active=True).order_by('user__first_name'))
        all_experts = list(ExpertProfile.objects.select_related('user').filter(user__is_active=True).order_by('user__first_name'))

        for jt in displayed_panels:
            jt_jury_ids = set(j.id for j in jt.juries.all())
            jt_expert_ids = set(e.id for e in jt.experts.all())

            # Available juries for this panel: not assigned to OTHER panels in this round
            available_juries = [j for j in all_juries if (j.id in jt_jury_ids or j.id not in all_assigned_jury_ids)]
            # Available experts for this panel: not assigned to OTHER panels in this round
            available_experts = [e for e in all_experts if (e.id in jt_expert_ids or e.id not in all_assigned_expert_ids)]

            # Domain filtering based on Panel's Problem Statement
            ps_domain = ''
            if jt.problem_statement and jt.problem_statement.domain:
                ps_domain = jt.problem_statement.domain.strip().lower()

            # Check if any juries/experts with this domain exist in the system at all
            # (before cross-panel exclusion — used to distinguish "none exist" vs "all taken")
            has_domain_juries = True
            has_domain_experts = True

            if ps_domain:
                # Strictly filter to domain-matched only (no fallback to all domains)
                available_juries = [
                    j for j in available_juries
                    if (j.id in jt_jury_ids or (j.domain and any(d.strip().lower() == ps_domain for d in j.domain.split(','))))
                ]
                available_experts = [
                    e for e in available_experts
                    if (e.id in jt_expert_ids or (e.domain and any(d.strip().lower() == ps_domain for d in e.domain.split(','))))
                ]

                # Check against ALL juries/experts (ignoring panel assignments)
                has_domain_juries = any(
                    j.domain and any(d.strip().lower() == ps_domain for d in j.domain.split(','))
                    for j in all_juries
                )
                has_domain_experts = any(
                    e.domain and any(d.strip().lower() == ps_domain for d in e.domain.split(','))
                    for e in all_experts
                )

            selected_juries = list(jt.juries.all())
            selected_experts = list(jt.experts.all())

            num_jury_per_team = max(round_jury_config.num_jury_per_team, len(selected_juries))
            num_experts_per_team = max(round_jury_config.num_experts_per_team, len(selected_experts))

            # Build per-slot available lists, excluding members already used in earlier slots
            selected_jury_ids_so_far = set()
            jury_slots = []
            for idx in range(num_jury_per_team):
                val = selected_juries[idx].id if idx < len(selected_juries) else ''
                slot_available = [j for j in available_juries if j.id not in selected_jury_ids_so_far or j.id == val]
                jury_slots.append({
                    'slot_num': idx + 1,
                    'selected_id': val,
                    'available': slot_available,
                })
                if val:
                    selected_jury_ids_so_far.add(val)

            selected_expert_ids_so_far = set()
            expert_slots = []
            for idx in range(num_experts_per_team):
                val = selected_experts[idx].id if idx < len(selected_experts) else ''
                slot_available = [e for e in available_experts if e.id not in selected_expert_ids_so_far or e.id == val]
                expert_slots.append({
                    'slot_num': idx + 1,
                    'selected_id': val,
                    'available': slot_available,
                })
                if val:
                    selected_expert_ids_so_far.add(val)

            jury_teams_data.append({
                'panel': jt,
                'available_juries': available_juries,
                'available_experts': available_experts,
                'jury_slots': jury_slots,
                'expert_slots': expert_slots,
                'has_domain_juries': has_domain_juries,
                'has_domain_experts': has_domain_experts,
                'teams_count': jt.assigned_team_evaluations.filter(round_number=selected_round).count(),
            })

        parameters = RoundMarkingParameter.objects.filter(
            hackathon=active_hackathon
        ).order_by('round_number', 'name')
        teams_for_eval = Team.objects.filter(
            hackathon=active_hackathon,
            current_round__gte=selected_round
        ).select_related(
            'institution', 'team_leader', 'problem_statement'
        ).order_by('-updated_at')
        if selected_ps_id:
            teams_for_eval = teams_for_eval.filter(problem_statement_id=selected_ps_id)

        registration_counts = {
            'teams':     teams_for_eval.count(),
            'approved':  teams_for_eval.filter(status='admin_approved').count(),
            'submitted': teams_for_eval.filter(status='submitted').count(),
            'evaluated': teams_for_eval.filter(status='evaluated').count(),
        }

        # Build a summary for ALL panels in this round (regardless of PS filter)
        # used by the bottom Panel vs Teams summary card
        from .models import TeamEvaluationAssignment
        panels_summary = []
        for jt in all_jury_teams_in_round:
            panels_summary.append({
                'name': jt.name,
                'ps_name': jt.problem_statement.title if jt.problem_statement else '—',
                'teams_count': jt.assigned_team_evaluations.filter(round_number=selected_round).count(),
                'juries_count': jt.juries.count(),
                'experts_count': jt.experts.count(),
            })

    # Stats
    invite_counts = {
        'invited':   JuryInvitation.objects.filter(status='invited').count(),
        'pending':   JuryInvitation.objects.filter(status='pending').count(),
        'approved':  JuryInvitation.objects.filter(status='approved').count(),
    }
    expert_invite_counts = {
        'invited':   ExpertInvitation.objects.filter(status='invited').count(),
        'pending':   ExpertInvitation.objects.filter(status='pending').count(),
        'approved':  ExpertInvitation.objects.filter(status='approved').count(),
    }

    # Determine lock status and current jury round for the active hackathon
    is_round_promoted = False
    if active_hackathon:
        is_round_promoted = Team.objects.filter(
            hackathon=active_hackathon,
            current_round__gt=selected_round
        ).exists()
    is_round_completed = (active_hackathon.current_jury_round > selected_round) or is_round_promoted if active_hackathon else False

    is_round_locked = round_jury_config.is_locked if round_jury_config else False
    if is_round_completed:
        is_round_locked = True
    current_jury_round = active_hackathon.current_jury_round if active_hackathon else 1

    # Prepare teams for eval with their automatic assignments
    teams_for_eval_list = []
    if active_hackathon:
        teams_for_eval_list = list(teams_for_eval[:50])
        for team in teams_for_eval_list:
            assignment = team.evaluation_assignments.filter(round_number=selected_round).first()
            team.eval_assignment = assignment
            if not assignment or not assignment.is_mandatory_assigned():
                team.eval_status = "Pending Assignment"
            else:
                team.eval_status = "Assigned"

            # Determine qualification status for the selected round
            if team.status == 'disqualified':
                team.qualification_status = "Disqualified"
            elif team.current_round > selected_round:
                team.qualification_status = "Qualified"
            else:
                if is_round_completed:
                    team.qualification_status = "Not Qualified"
                else:
                    team.qualification_status = "Pending"

    num_rounds = max(active_hackathon.number_of_rounds if active_hackathon else 5, 5)

    # Group panels by problem statement when locked
    grouped_jury_teams_data = []
    if is_round_locked:
        from collections import defaultdict
        panels_by_ps = defaultdict(list)
        for item in jury_teams_data:
            ps = item['panel'].problem_statement
            if ps:
                panels_by_ps[ps].append(item)
            else:
                panels_by_ps['unassigned'].append(item)

        for ps in problem_statements:
            ps_panels = panels_by_ps.get(ps, [])
            if ps_panels:
                grouped_jury_teams_data.append({
                    'problem_statement': ps,
                    'panels': ps_panels,
                })
        
        unassigned_panels = panels_by_ps.get('unassigned', [])
        if unassigned_panels:
            grouped_jury_teams_data.append({
                'problem_statement': None,
                'panels': unassigned_panels,
            })

    context = _feature_context(
        request,
        tab='jury_ops',
        sub=sub,
        focus=focus,
        q=query,
        hackathons=hackathons,
        hackathon_filter=hackathon_filter,
        active_hackathon=active_hackathon,
        invitations=invitations,
        expert_invitations=expert_invitations,
        invite_counts=invite_counts,
        expert_invite_counts=expert_invite_counts,
        juries=juries,
        experts=experts,
        parameters=parameters,
        teams_for_eval=teams_for_eval_list,
        registration_counts=registration_counts,
        active_round=active_hackathon.active_round if active_hackathon else None,
        selected_round=selected_round,
        round_range=range(1, num_rounds + 1),
        problem_statements=problem_statements,
        jury_teams_data=jury_teams_data,
        grouped_jury_teams_data=grouped_jury_teams_data,
        round_jury_config=round_jury_config,
        ps_filter=ps_filter,
        selected_ps_id=selected_ps_id,
        is_round_locked=is_round_locked,
        is_round_completed=is_round_completed,
        current_jury_round=current_jury_round,
        panels_summary=panels_summary,
        panels_saved=panels_saved,
        show_assignments=show_assignments,
    )
    return render(request, 'features/jury_management.html', context)


@login_required(login_url='/accounts/')
@require_POST
def add_jury_panel(request):
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    round_number = int(request.POST.get('round_number', 1))
    panel_name = request.POST.get('panel_name', '').strip()
    problem_statement_id = request.POST.get('problem_statement_id')

    if not hackathon_id:
        messages.error(request, "Hackathon is required.")
        return render_route(request, '/features/jury/?sub=evaluation')

    from events.models import Hackathon, JuryTeam, ProblemStatement, RoundJuryConfig
    hackathon = get_object_or_404(Hackathon, id=hackathon_id)

    # ── ROUND GATE: Only allow panel creation for the current jury round ──
    if round_number != hackathon.current_jury_round:
        messages.error(
            request,
            f"Panels can only be created for the active jury round (Round {hackathon.current_jury_round}). "
            f"Promote teams to Round {round_number} first to unlock panel creation for that round."
        )
        redirect_url = f'/features/jury/?sub=evaluation&hackathon={hackathon.id}&round_number={round_number}'
        return redirect(redirect_url)

    # ── LOCK GATE: Block if the round is locked ──
    round_config = RoundJuryConfig.objects.filter(hackathon=hackathon, round_number=round_number).first()
    if round_config and round_config.is_locked:
        messages.error(
            request,
            f"Team assignments for Round {round_number} are locked. Unlock them first to add new panels."
        )
        redirect_url = f'/features/jury/?sub=evaluation&hackathon={hackathon.id}&round_number={round_number}'
        return redirect(redirect_url)

    ps_obj = None
    if problem_statement_id:
        ps_obj = ProblemStatement.objects.filter(id=problem_statement_id, hackathon=hackathon).first()

    existing_count = JuryTeam.objects.filter(hackathon=hackathon, round_number=round_number).count()
    if not panel_name:
        letter = chr(65 + existing_count) if existing_count < 26 else str(existing_count + 1)
        panel_name = f"Panel {letter}"

    JuryTeam.objects.create(
        hackathon=hackathon,
        round_number=round_number,
        name=panel_name,
        display_order=existing_count + 1,
        problem_statement=ps_obj
    )
    if round_config:
        round_config.has_assigned_teams = False
        round_config.save()
    messages.success(request, f"New panel '{panel_name}' added for Round {round_number}.")
    redirect_url = f'/features/jury/?sub=evaluation&hackathon={hackathon.id}&round_number={round_number}'
    if problem_statement_id:
        redirect_url += f'&problem_statement={problem_statement_id}'
    return redirect(redirect_url)


@login_required(login_url='/accounts/')
@require_POST
def delete_jury_panel(request, panel_id):
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    from events.models import JuryTeam
    jury_team = get_object_or_404(JuryTeam, id=panel_id)
    hackathon_id = jury_team.hackathon_id
    round_number = jury_team.round_number
    panel_name = jury_team.name

    jury_team.delete()

    from events.models import RoundJuryConfig
    round_config = RoundJuryConfig.objects.filter(hackathon_id=hackathon_id, round_number=round_number).first()
    if round_config:
        round_config.has_assigned_teams = False
        round_config.save()

    # Resync team assignments after panel removal
    from events.models import Hackathon
    hackathon = Hackathon.objects.filter(id=hackathon_id).first()
    if hackathon:
        sync_automatic_team_assignments(hackathon, round_number)

    messages.success(request, f"Panel '{panel_name}' removed successfully.")
    return redirect(f'/features/jury/?sub=evaluation&hackathon={hackathon_id}&round_number={round_number}')


@login_required(login_url='/accounts/')
@require_POST
def save_all_jury_panels(request):
    """Batch-save all jury panel assignments for a given hackathon round."""
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    round_number = int(request.POST.get('round_number', 1))

    if not hackathon_id:
        messages.error(request, "Hackathon is required.")
        return render_route(request, '/features/jury/?sub=evaluation')

    from events.models import Hackathon, JuryTeam, ProblemStatement, RoundJuryConfig
    from accounts.models import JuryProfile, ExpertProfile

    hackathon = get_object_or_404(Hackathon, id=hackathon_id)

    # Lock gate
    round_config = RoundJuryConfig.objects.filter(
        hackathon=hackathon, round_number=round_number
    ).first()
    if round_config and round_config.is_locked:
        messages.error(
            request,
            f"Team assignments for Round {round_number} are locked. "
            "Unlock them to make changes."
        )
        return redirect(
            f'/features/jury/?sub=evaluation&hackathon={hackathon_id}'
            f'&round_number={round_number}'
        )

    panels = JuryTeam.objects.filter(
        hackathon=hackathon, round_number=round_number
    ).order_by('display_order', 'id')

    saved_count = 0
    for panel in panels:
        prefix = f'panel_{panel.id}_'

        # Check if this panel was actually rendered and submitted in the form
        # (if it was hidden by a problem statement filter, skip saving to prevent data loss)
        if f'{prefix}problem_statement_id' not in request.POST:
            continue

        # Problem statement
        ps_id = request.POST.get(f'{prefix}problem_statement_id')
        if ps_id:
            ps = ProblemStatement.objects.filter(id=ps_id).first()
            panel.problem_statement = ps
        else:
            panel.problem_statement = None

        # Jury slots
        jury_ids = []
        for key in request.POST:
            if key.startswith(f'{prefix}jury_slot_') and request.POST[key]:
                try:
                    jury_ids.append(int(request.POST[key]))
                except ValueError:
                    pass
        juries_to_set = JuryProfile.objects.filter(id__in=jury_ids)
        panel.juries.set(juries_to_set)

        # Expert slots
        expert_ids = []
        for key in request.POST:
            if key.startswith(f'{prefix}expert_slot_') and request.POST[key]:
                try:
                    expert_ids.append(int(request.POST[key]))
                except ValueError:
                    pass
        experts_to_set = ExpertProfile.objects.filter(id__in=expert_ids)
        panel.experts.set(experts_to_set)

        panel.save()
        saved_count += 1

    # Sync automatic assignments
    sync_automatic_team_assignments(hackathon, round_number)

    from events.models import RoundJuryConfig
    round_config, _ = RoundJuryConfig.objects.get_or_create(
        hackathon=hackathon,
        round_number=round_number,
        defaults={'num_jury_per_team': 1, 'num_experts_per_team': 1}
    )

    action = request.POST.get('action')
    if action == 'done':
        from django.utils import timezone
        round_config.is_locked = True
        round_config.locked_at = timezone.now()
        round_config.locked_by = request.user
        round_config.save()
        messages.success(request, f"Panel creation finalized and locked for Round {round_number}.")
    else:
        round_config.has_assigned_teams = False
        round_config.save()
        messages.success(request, f"All {saved_count} panel assignments saved successfully for Round {round_number}.")

    ps_filter = request.POST.get('ps_filter', '').strip()
    redirect_url = f'/features/jury/?sub=evaluation&hackathon={hackathon_id}&round_number={round_number}&panels_saved=true'
    if ps_filter:
        redirect_url += f'&problem_statement={ps_filter}'
    return redirect(redirect_url)


@login_required(login_url='/accounts/')
@require_POST
def save_jury_team_assignment(request):
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    jury_team_id = request.POST.get('jury_team_id')
    problem_statement_id = request.POST.get('problem_statement_id')

    if not jury_team_id:
        messages.error(request, "Jury Panel is required.")
        return render_route(request, '/features/jury/?sub=evaluation')

    from events.models import JuryTeam, ProblemStatement, RoundJuryConfig
    from accounts.models import JuryProfile, ExpertProfile

    try:
        jury_team = get_object_or_404(JuryTeam, id=jury_team_id)

        # ── LOCK GATE: Block if the round is locked ──
        round_config = RoundJuryConfig.objects.filter(
            hackathon=jury_team.hackathon, round_number=jury_team.round_number
        ).first()
        if round_config and round_config.is_locked:
            messages.error(
                request,
                f"Team assignments for Round {jury_team.round_number} are locked. "
                "Unlock them to make changes."
            )
            return redirect(
                f'/features/jury/?sub=evaluation&hackathon={jury_team.hackathon_id}'
                f'&round_number={jury_team.round_number}'
            )

        if problem_statement_id:
            ps = get_object_or_404(ProblemStatement, id=problem_statement_id)
            jury_team.problem_statement = ps
        else:
            jury_team.problem_statement = None

        # Read jury slot inputs (e.g. jury_slot_1, jury_slot_2, ...)
        jury_ids = []
        for key in request.POST:
            if key.startswith('jury_slot_') and request.POST[key]:
                try:
                    jury_ids.append(int(request.POST[key]))
                except ValueError:
                    pass

        juries_to_set = JuryProfile.objects.filter(id__in=jury_ids)
        jury_team.juries.set(juries_to_set)

        # Read expert slot inputs (e.g. expert_slot_1, expert_slot_2, ...)
        expert_ids = []
        for key in request.POST:
            if key.startswith('expert_slot_') and request.POST[key]:
                try:
                    expert_ids.append(int(request.POST[key]))
                except ValueError:
                    pass

        experts_to_set = ExpertProfile.objects.filter(id__in=expert_ids)
        jury_team.experts.set(experts_to_set)

        jury_team.save()

        # Sync automatic assignments for student teams
        sync_automatic_team_assignments(jury_team.hackathon, jury_team.round_number)

        messages.success(request, f"Assignments for Panel '{jury_team.name}' updated successfully.")
        redirect_url = f'/features/jury/?sub=evaluation&hackathon={jury_team.hackathon.id}&round_number={jury_team.round_number}'
        ps_filter = request.POST.get('ps_filter', '').strip()
        if ps_filter:
            redirect_url += f'&problem_statement={ps_filter}'
        return redirect(redirect_url)
    except Exception as exc:
        messages.error(request, f"Failed to save panel assignment: {exc}")
        return render_route(request, '/features/jury/?sub=evaluation')


@login_required(login_url='/accounts/')
@require_POST
def lock_round_assignments(request):
    """Toggle the lock state of jury team assignments for a specific round.

    When locked:
      - No new panels can be added for this round.
      - Existing panel member assignments cannot be changed.
    When unlocked:
      - All editing is restored.
    """
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    round_number = int(request.POST.get('round_number', 1))

    if not hackathon_id:
        messages.error(request, "Hackathon is required.")
        return render_route(request, '/features/jury/?sub=evaluation')

    from events.models import Hackathon, RoundJuryConfig
    hackathon = get_object_or_404(Hackathon, id=hackathon_id)

    round_config, _ = RoundJuryConfig.objects.get_or_create(
        hackathon=hackathon,
        round_number=round_number,
        defaults={'num_jury_per_team': 1, 'num_experts_per_team': 1}
    )

    # Prevent unlocking if the round is completed/promoted
    from features.models import Team
    is_round_promoted = Team.objects.filter(
        hackathon=hackathon,
        current_round__gt=round_number
    ).exists()
    is_round_completed = (hackathon.current_jury_round > round_number) or is_round_promoted

    if is_round_completed and round_config.is_locked:
        messages.error(
            request,
            f"Round {round_number} assignments are permanently locked because the round is already completed/promoted."
        )
        return redirect(
            f'/features/jury/?sub=evaluation&hackathon={hackathon_id}&round_number={round_number}'
        )

    # Toggle the lock
    if round_config.is_locked:
        round_config.is_locked = False
        round_config.locked_at = None
        round_config.locked_by = None
        round_config.save(update_fields=['is_locked', 'locked_at', 'locked_by'])
        messages.success(
            request,
            f"Round {round_number} team assignments have been unlocked. "
            "You can now add or modify jury panels."
        )
    else:
        round_config.is_locked = True
        round_config.locked_at = timezone.now()
        round_config.locked_by = request.user
        round_config.save(update_fields=['is_locked', 'locked_at', 'locked_by'])
        messages.success(
            request,
            f"Round {round_number} team assignments are now locked. "
            "No further jury panel creation or member changes are allowed."
        )

    return redirect(
        f'/features/jury/?sub=evaluation&hackathon={hackathon_id}&round_number={round_number}'
    )


@login_required(login_url='/accounts/')
@require_POST
def alter_round_assignments(request):
    """Increment the alter_offset or reset it to 0 for a specific round's team assignments."""
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    round_number = int(request.POST.get('round_number', 1))
    reset = request.POST.get('reset') == 'true'

    if not hackathon_id:
        messages.error(request, "Hackathon is required.")
        return redirect('/features/jury/?sub=evaluation')

    from events.models import Hackathon, RoundJuryConfig
    hackathon = get_object_or_404(Hackathon, id=hackathon_id)

    # ── LOCK GATE: Block if the round is locked ──
    round_config = RoundJuryConfig.objects.filter(hackathon=hackathon, round_number=round_number).first()
    if round_config and round_config.is_locked:
        messages.error(
            request,
            f"Team assignments for Round {round_number} are locked. Unlock them first to alter assignments."
        )
        return redirect(f'/features/jury/?sub=evaluation&hackathon={hackathon.id}&round_number={round_number}')

    if not round_config:
        round_config = RoundJuryConfig.objects.create(
            hackathon=hackathon,
            round_number=round_number,
            num_jury_per_team=1,
            num_experts_per_team=1,
        )

    if reset:
        round_config.alter_offset = 0
        round_config.alter_assignment = False
        round_config.save()
        messages.success(request, f"Team assignments for Round {round_number} have been restored to standard order.")
    else:
        round_config.alter_offset += 1
        round_config.alter_assignment = True
        round_config.save()
        messages.success(request, f"Team assignments for Round {round_number} have been altered successfully (Shift #{round_config.alter_offset}).")

    # Re-sync automatic assignments with the new config
    sync_automatic_team_assignments(hackathon, round_number)

    return redirect(f'/features/jury/?sub=evaluation&hackathon={hackathon.id}&round_number={round_number}&show_assignments=true')


@login_required(login_url='/accounts/')
@require_POST
def assign_round_teams(request):
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    round_number = int(request.POST.get('round_number', 1))

    if not hackathon_id:
        messages.error(request, "Hackathon is required.")
        return redirect('/features/jury/?sub=evaluation')

    from events.models import Hackathon, RoundJuryConfig
    hackathon = get_object_or_404(Hackathon, id=hackathon_id)

    # ── LOCK GATE: Block if the round is locked ──
    round_config = RoundJuryConfig.objects.filter(hackathon=hackathon, round_number=round_number).first()
    if round_config and round_config.is_locked:
        messages.error(
            request,
            f"Team assignments for Round {round_number} are locked. Unlock them first to assign teams."
        )
        return redirect(f'/features/jury/?sub=evaluation&hackathon={hackathon.id}&round_number={round_number}')

    if not round_config:
        round_config = RoundJuryConfig.objects.create(
            hackathon=hackathon,
            round_number=round_number,
            num_jury_per_team=1,
            num_experts_per_team=1,
        )

    round_config.has_assigned_teams = True
    round_config.save()

    sync_automatic_team_assignments(hackathon, round_number)
    messages.success(request, f"Teams successfully assigned to panels for Round {round_number}.")

    return redirect(f'/features/jury/?sub=evaluation&hackathon={hackathon.id}&round_number={round_number}&show_assignments=true')


@login_required(login_url='/accounts/')
@require_POST
def save_team_evaluation_assignment(request):
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied
        
    team_id = request.POST.get('team_id')
    round_number = request.POST.get('round_number')
    jury_1_id = request.POST.get('jury_1_id')
    jury_2_id = request.POST.get('jury_2_id')
    jury_3_id = request.POST.get('jury_3_id')
    expert_1_id = request.POST.get('expert_1_id')
    expert_2_id = request.POST.get('expert_2_id')
    
    if not all([team_id, round_number]):
        messages.error(request, "Team and Round are required for assignment.")
        return render_route(request, '/features/jury/?sub=evaluation')
    
    # Mandatory Check
    if not jury_1_id or not expert_1_id:
        messages.error(request, "Jury 1 and Expert 1 are mandatory for each team.")
        return render_route(request, '/features/jury/?sub=evaluation')
        
    from .models import TeamEvaluationAssignment
    from accounts.models import JuryProfile, ExpertProfile
    
    try:
        team = get_object_or_404(Team, id=team_id)
        assignment, created = TeamEvaluationAssignment.objects.get_or_create(
            team=team, round_number=round_number
        )
        
        assignment.jury_1 = get_object_or_404(JuryProfile, id=jury_1_id) if jury_1_id else None
        assignment.jury_2 = get_object_or_404(JuryProfile, id=jury_2_id) if jury_2_id else None
        assignment.jury_3 = get_object_or_404(JuryProfile, id=jury_3_id) if jury_3_id else None
        assignment.expert_1 = get_object_or_404(ExpertProfile, id=expert_1_id) if expert_1_id else None
        assignment.expert_2 = get_object_or_404(ExpertProfile, id=expert_2_id) if expert_2_id else None
            
        if assignment.is_fully_assigned():
            assignment.status = 'Assigned'
        else:
            assignment.status = 'Pending'
            
        assignment.save()
        messages.success(request, f"Evaluation assignment for team '{team.team_name}' updated successfully.")
    except Exception as exc:
        messages.error(request, f"Failed to save assignment: {exc}")
        
    return render_route(request, '/features/jury/?sub=evaluation')



@login_required(login_url='/accounts/')
@never_cache
def send_evaluator_invite(request):
    """Unified invite endpoint: creates a JuryInvitation or ExpertInvitation based on role."""
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/jury/?sub=invitations')

    from django.urls import reverse
    email        = request.POST.get('email', '').strip().lower()
    hackathon_id = request.POST.get('hackathon_id', '').strip()
    role         = request.POST.get('role', 'jury')  # 'jury' or 'expert'

    if not email:
        messages.error(request, 'Email address is required.')
        return render_route(request, '/features/jury/?sub=invitations')

    try:
        validate_email(email)
    except ValidationError:
        messages.error(request, 'Invalid email address.')
        return render_route(request, '/features/jury/?sub=invitations')

    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, 'A user with this email already exists.')
        return render_route(request, '/features/jury/?sub=invitations')

    hackathon = None
    if hackathon_id and hackathon_id.isdigit():
        hackathon = Hackathon.objects.filter(id=hackathon_id).first()

    try:
        with transaction.atomic():
            token = uuid.uuid4().hex
            if role == 'expert':
                if ExpertInvitation.objects.filter(email__iexact=email).exists():
                    messages.warning(request, f'An expert invitation already exists for {email}.')
                    return render_route(request, '/features/jury/?sub=invitations')
                ExpertInvitation.objects.create(
                    invited_by=request.user, email=email,
                    hackathon=hackathon, token=token, status='invited',
                )
                form_link = request.build_absolute_uri(reverse('expert_register_form', args=[token]))
                _send_expert_invite_email(email, form_link, hackathon)
                messages.success(request, f'Expert invitation sent to {email}.')
            else:
                if JuryInvitation.objects.filter(email__iexact=email).exists():
                    messages.warning(request, f'A jury invitation already exists for {email}.')
                    return render_route(request, '/features/jury/?sub=invitations')
                JuryInvitation.objects.create(
                    invited_by=request.user, email=email,
                    hackathon=hackathon, token=token, status='invited',
                )
                form_link = request.build_absolute_uri(reverse('jury_register_form', args=[token]))
                _send_jury_invite_email(email, form_link, hackathon)
                messages.success(request, f'Jury invitation sent to {email}.')
    except Exception as exc:
        logger.error(f'Evaluator invite error {email}: {exc}', exc_info=True)
        messages.error(request, f'Failed to send invitation: {exc}')

    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@never_cache
def send_bulk_evaluator_invites(request):
    """Unified bulk invite endpoint for both jury and expert."""
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/jury/?sub=invitations')

    from django.urls import reverse
    csv_file     = request.FILES.get('csv_file')
    hackathon_id = request.POST.get('hackathon_id', '').strip()
    role         = request.POST.get('role', 'jury')

    if not csv_file:
        messages.error(request, 'Please upload a CSV file.')
        return render_route(request, '/features/jury/?sub=invitations')
    if not csv_file.name.lower().endswith('.csv'):
        messages.error(request, 'Only CSV files are supported.')
        return render_route(request, '/features/jury/?sub=invitations')

    try:
        decoded = csv_file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        messages.error(request, 'CSV file must be UTF-8 encoded.')
        return render_route(request, '/features/jury/?sub=invitations')

    emails = _extract_spoc_emails_from_csv(decoded)
    if not emails:
        messages.error(request, 'No valid email entries found in the CSV.')
        return render_route(request, '/features/jury/?sub=invitations')

    hackathon = None
    if hackathon_id and hackathon_id.isdigit():
        hackathon = Hackathon.objects.filter(id=hackathon_id).first()

    sent, failed = 0, []
    for email in emails:
        if User.objects.filter(email__iexact=email).exists():
            failed.append(f'{email} (user exists)')
            continue

        try:
            token = uuid.uuid4().hex
            if role == 'expert':
                if ExpertInvitation.objects.filter(email__iexact=email).exists():
                    failed.append(f'{email} (already invited)')
                    continue
                ExpertInvitation.objects.create(
                    invited_by=request.user, email=email,
                    hackathon=hackathon, token=token, status='invited',
                )
                form_link = request.build_absolute_uri(reverse('expert_register_form', args=[token]))
                _send_expert_invite_email(email, form_link, hackathon)
            else:
                if JuryInvitation.objects.filter(email__iexact=email).exists():
                    failed.append(f'{email} (already invited)')
                    continue
                JuryInvitation.objects.create(
                    invited_by=request.user, email=email,
                    hackathon=hackathon, token=token, status='invited',
                )
                form_link = request.build_absolute_uri(reverse('jury_register_form', args=[token]))
                _send_jury_invite_email(email, form_link, hackathon)
            sent += 1
        except Exception as exc:
            failed.append(f'{email} (error: {exc})')

    if sent > 0:
        messages.success(request, f'Successfully sent {sent} {role} invitations.')
    if failed:
        messages.warning(request, f'Failed to send {len(failed)} invites: {", ".join(failed[:5])}...')

    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@never_cache
def send_jury_invite(request):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/jury/?sub=invitations')

    from django.urls import reverse
    email        = request.POST.get('email', '').strip().lower()
    hackathon_id = request.POST.get('hackathon_id', '').strip()

    if not email:
        messages.error(request, 'Email address is required.')
        return render_route(request, '/features/jury/?sub=invitations')

    try:
        validate_email(email)
    except ValidationError:
        messages.error(request, 'Invalid email address.')
        return render_route(request, '/features/jury/?sub=invitations')

    if JuryInvitation.objects.filter(email__iexact=email).exists():
        messages.warning(request, f'An invitation already exists for {email}.')
        return render_route(request, '/features/jury/?sub=invitations')

    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, 'A user with this email already exists.')
        return render_route(request, '/features/jury/?sub=invitations')

    hackathon = None
    if hackathon_id and hackathon_id.isdigit():
        hackathon = Hackathon.objects.filter(id=hackathon_id).first()

    try:
        with transaction.atomic():
            token = uuid.uuid4().hex
            invite = JuryInvitation.objects.create(
                invited_by=request.user,
                email=email,
                hackathon=hackathon,
                token=token,
                status='invited',
            )
            form_link = request.build_absolute_uri(reverse('jury_register_form', args=[token]))
            _send_jury_invite_email(email, form_link, hackathon)
        messages.success(request, f'Jury invitation sent to {email}.')
    except Exception as exc:
        logger.error(f'Jury invite error {email}: {exc}', exc_info=True)
        messages.error(request, f'Failed to send invitation: {exc}')

    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@never_cache
def send_bulk_jury_invites(request):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/jury/?sub=invitations')

    from django.urls import reverse
    csv_file     = request.FILES.get('csv_file')
    hackathon_id = request.POST.get('hackathon_id', '').strip()

    if not csv_file:
        messages.error(request, 'Please upload a CSV file.')
        return render_route(request, '/features/jury/?sub=invitations')
    if not csv_file.name.lower().endswith('.csv'):
        messages.error(request, 'Only CSV files are supported.')
        return render_route(request, '/features/jury/?sub=invitations')

    try:
        decoded = csv_file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        messages.error(request, 'CSV file must be UTF-8 encoded.')
        return render_route(request, '/features/jury/?sub=invitations')

    emails = _extract_spoc_emails_from_csv(decoded)  # reuse SPOC CSV parser
    if not emails:
        messages.error(request, 'No valid email entries found in the CSV.')
        return render_route(request, '/features/jury/?sub=invitations')

    hackathon = None
    if hackathon_id and hackathon_id.isdigit():
        hackathon = Hackathon.objects.filter(id=hackathon_id).first()

    sent, failed = 0, []
    for email in emails:
        if JuryInvitation.objects.filter(email__iexact=email).exists():
            failed.append(f'{email} (already invited)')
            continue
        if User.objects.filter(email__iexact=email).exists():
            failed.append(f'{email} (user exists)')
            continue
        try:
            token = uuid.uuid4().hex
            JuryInvitation.objects.create(
                invited_by=request.user, email=email,
                hackathon=hackathon, token=token, status='invited',
            )
            form_link = request.build_absolute_uri(reverse('jury_register_form', args=[token]))
            _send_jury_invite_email(email, form_link, hackathon)
            sent += 1
        except Exception as exc:
            failed.append(f'{email} ({exc})')

    if sent:
        messages.success(request, f'Bulk invite complete. {sent} invitation(s) sent.')
    if failed:
        preview = '; '.join(failed[:5])
        extra = f' and {len(failed)-5} more' if len(failed) > 5 else ''
        messages.warning(request, f'{len(failed)} email(s) skipped: {preview}{extra}')

    return render_route(request, '/features/jury/?sub=invitations')


def jury_register_form(request, token):
    """Public token-based self-registration form for jury members."""
    try:
        invitation = JuryInvitation.objects.get(token=token)
    except JuryInvitation.DoesNotExist:
        return render(request, 'features/jury_register_invalid.html',
                      {'reason': 'Invalid or expired registration link.'})

    if invitation.status == 'suspended':
        return render(request, 'features/jury_register_invalid.html',
                      {'reason': 'This jury invitation is suspended. Please contact the administrator.'})
    if invitation.status == 'approved':
        return render(request, 'features/jury_register_invalid.html',
                      {'reason': 'This invitation has already been approved. You can now log in.'})
    if invitation.status == 'pending':
        return render(request, 'features/jury_register_invalid.html',
                      {'reason': 'Your application is already submitted and is under review.'})

    if request.method == 'POST':
        try:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone_number = request.POST.get('phone_number', '').strip()
            gender = request.POST.get('gender', '').strip()
            organization = request.POST.get('organization', '').strip()
            designation = request.POST.get('designation', '').strip()
            linkedin_url = request.POST.get('linkedin_url', '').strip()
            bio = request.POST.get('bio', '').strip()

            if not first_name or len(first_name) < 2:
                raise ValueError("First name must be at least 2 characters long.")
            if not last_name or len(last_name) < 2:
                raise ValueError("Last name must be at least 2 characters long.")
            
            phone_number = _clean_indian_phone_number(phone_number)
            
            if not organization or len(organization) < 3:
                raise ValueError("Organization must be at least 3 characters long.")
            if not designation or len(designation) < 2:
                raise ValueError("Designation must be at least 2 characters long.")
                
            domain_list = request.POST.getlist('domain')
            if domain_list:
                domain = ", ".join([d.strip() for d in domain_list if d.strip()])
            else:
                domain = request.POST.get('domain', '').strip()
            if not domain:
                raise ValueError("At least one judging domain/area of expertise must be selected or specified.")
                
            if linkedin_url:
                from django.core.validators import URLValidator
                val_url = URLValidator()
                try:
                    val_url(linkedin_url)
                except ValidationError:
                    raise ValueError("Please enter a valid LinkedIn URL.")
                    
            dob = request.POST.get('date_of_birth', '').strip()
            if dob:
                from datetime import datetime, date
                try:
                    dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                    today = date.today()
                    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                    if age < 18:
                        raise ValueError("Jury member must be at least 18 years old.")
                except ValueError as e:
                    if "18" in str(e):
                        raise e
                    raise ValueError("Please enter a valid date of birth in YYYY-MM-DD format.")
            else:
                dob_date = None

            if not invitation.id_proof and 'id_proof' not in request.FILES:
                raise ValueError("Government ID Proof is required.")
            if 'id_proof' in request.FILES:
                _validate_document_file(request.FILES['id_proof'], "Government ID proof")
            if 'photo' in request.FILES:
                _validate_image_file(request.FILES['photo'], "Photo")

            invitation.first_name = first_name
            invitation.last_name = last_name
            invitation.phone_number = phone_number
            invitation.gender = gender
            invitation.organization = organization
            invitation.designation = designation
            invitation.domain = domain
            invitation.linkedin_url = linkedin_url
            invitation.bio = bio
            invitation.date_of_birth = dob_date
            
            if 'id_proof' in request.FILES:
                invitation.id_proof = request.FILES['id_proof']
            if 'photo' in request.FILES:
                invitation.photo = request.FILES['photo']
                
            invitation.status       = 'pending'
            invitation.rejection_reason = ''
            invitation.submitted_at = timezone.now()
            invitation.save()
            return render(request, 'features/jury_register_success.html',
                          {'email': invitation.email})
        except Exception as exc:
            logger.error(f'Jury form token {token}: {exc}', exc_info=True)
            messages.error(request, f'Submission failed: {exc}')

    available_domains = []
    if invitation.hackathon:
        from events.models import HackathonDomain, ProblemStatement
        h_domains = list(HackathonDomain.objects.filter(hackathon=invitation.hackathon).values_list('name', flat=True))
        ps_domains = list(ProblemStatement.objects.filter(hackathon=invitation.hackathon).exclude(domain__isnull=True).exclude(domain='').values_list('domain', flat=True).distinct())
        domain_set = set()
        for d in h_domains + ps_domains:
            if d and d not in domain_set:
                domain_set.add(d)
                available_domains.append(d)

    selected_domains = [d.strip() for d in (invitation.domain or '').split(',')] if invitation.domain else []

    return render(request, 'features/jury_register_form.html', {
        'invitation': invitation,
        'is_rejected_resubmission': invitation.status == 'rejected',
        'available_domains': available_domains,
        'selected_domains': selected_domains,
    })


@login_required(login_url='/accounts/')
@never_cache
def view_jury_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    invite = get_object_or_404(
        JuryInvitation.objects.select_related('invited_by', 'hackathon', 'approved_by', 'created_user'),
        id=invite_id
    )
    return render(request, 'features/jury_invitation_detail.html', {
        'invite': invite, 'tab': 'jury_ops', 'sub': 'invitations',
    })


@login_required(login_url='/accounts/')
@never_cache
def edit_jury_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    invite = get_object_or_404(JuryInvitation, id=invite_id)

    if invite.status == 'approved':
        messages.warning(request, 'Approved jury members should be edited from their profile page.')
        return render_route(request, '/features/jury/?sub=invitations')

    if request.method == 'POST':
        try:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip().lower()
            phone_number = request.POST.get('phone_number', '').strip()
            gender = request.POST.get('gender', '').strip()
            organization = request.POST.get('organization', '').strip()
            designation = request.POST.get('designation', '').strip()
            linkedin_url = request.POST.get('linkedin_url', '').strip()
            bio = request.POST.get('bio', '').strip()

            if not first_name or len(first_name) < 2:
                raise ValueError("First name must be at least 2 characters long.")
            if not last_name or len(last_name) < 2:
                raise ValueError("Last name must be at least 2 characters long.")
            
            if not email:
                raise ValueError("Email is required.")
            try:
                validate_email(email)
            except ValidationError:
                raise ValueError("Please enter a valid email address.")
                
            if email != invite.email:
                if JuryInvitation.objects.filter(email=email).exclude(id=invite.id).exists():
                    raise ValueError(f"An invitation already exists for {email}.")
                if User.objects.filter(email=email).exists():
                    raise ValueError("A user with this email already exists.")
            
            phone_number = _clean_indian_phone_number(phone_number)
            
            if not organization or len(organization) < 3:
                raise ValueError("Organization must be at least 3 characters long.")
            if not designation or len(designation) < 2:
                raise ValueError("Designation must be at least 2 characters long.")
                
            domain_list = request.POST.getlist('domain')
            if domain_list:
                domain = ", ".join([d.strip() for d in domain_list if d.strip()])
            else:
                domain = request.POST.get('domain', '').strip()
            if not domain:
                raise ValueError("At least one judging domain/area of expertise must be selected or specified.")
                
            if linkedin_url:
                from django.core.validators import URLValidator
                val_url = URLValidator()
                try:
                    val_url(linkedin_url)
                except ValidationError:
                    raise ValueError("Please enter a valid LinkedIn URL.")
                    
            dob = request.POST.get('date_of_birth', '').strip()
            if dob:
                from datetime import datetime, date
                try:
                    dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                    today = date.today()
                    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                    if age < 18:
                        raise ValueError("Jury member must be at least 18 years old.")
                except ValueError as e:
                    if "18" in str(e):
                        raise e
                    raise ValueError("Please enter a valid date of birth in YYYY-MM-DD format.")
            else:
                dob_date = None

            if 'id_proof' in request.FILES:
                _validate_document_file(request.FILES['id_proof'], "Government ID proof")
            if 'photo' in request.FILES:
                _validate_image_file(request.FILES['photo'], "Photo")

            invite.first_name = first_name
            invite.last_name = last_name
            invite.email = email
            invite.phone_number = phone_number
            invite.gender = gender
            invite.organization = organization
            invite.designation = designation
            invite.domain = domain
            invite.linkedin_url = linkedin_url
            invite.bio = bio
            invite.date_of_birth = dob_date
            
            if 'id_proof' in request.FILES:
                invite.id_proof = request.FILES['id_proof']
            if 'photo' in request.FILES:
                invite.photo = request.FILES['photo']
                
            invite.save()
            messages.success(request, f"Jury application for '{invite.email}' updated.")
            return render_route(request, 'view_jury_invitation', invite.id)
        except Exception as exc:
            logger.error(f'Edit jury invitation {invite_id}: {exc}', exc_info=True)
            messages.error(request, f'Update failed: {exc}')

    target_hackathon = invite.hackathon or Hackathon.objects.first()
    available_domains = []
    if target_hackathon:
        from events.models import HackathonDomain, ProblemStatement
        h_domains = list(HackathonDomain.objects.filter(hackathon=target_hackathon).values_list('name', flat=True))
        ps_domains = list(ProblemStatement.objects.filter(hackathon=target_hackathon).exclude(domain__isnull=True).exclude(domain='').values_list('domain', flat=True).distinct())
        domain_set = set()
        for d in h_domains + ps_domains:
            if d and d not in domain_set:
                domain_set.add(d)
                available_domains.append(d)

    selected_domains = [d.strip() for d in (invite.domain or '').split(',')] if invite.domain else []

    return render(request, 'features/jury_invitation_edit.html', {
        'invite': invite,
        'available_domains': available_domains,
        'selected_domains': selected_domains,
        'tab': 'jury_ops', 'sub': 'invitations',
    })


@login_required(login_url='/accounts/')
@require_POST
def approve_jury_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied

    invite = get_object_or_404(JuryInvitation, id=invite_id)
    if invite.status != 'pending':
        messages.warning(request, f"Invitation status is '{invite.status}'. Only pending applications can be approved.")
        return render_route(request, '/features/jury/?sub=invitations')

    jury_role = Role.objects.filter(name__iexact='Jury').first()
    if not jury_role:
        messages.error(request, "The 'Jury' role is missing. Please create it in the admin panel first.")
        return render_route(request, '/features/jury/?sub=invitations')

    try:
        with transaction.atomic():
            password = _build_portal_password()
            user = User.objects.create_user(
                username=_build_unique_username(invite.email, 'jury'),
                email=invite.email,
                password=password,
                first_name=invite.first_name,
                last_name=invite.last_name,
                phone_number=invite.phone_number or None,
                gender=invite.gender or None,
                date_of_birth=invite.date_of_birth,
                role=jury_role,
                is_active=True,
                is_verified=True,
            )
            JuryProfile.objects.create(user=user, domain=invite.domain)
            invite.status      = 'approved'
            invite.approved_by = request.user
            invite.approved_at = timezone.now()
            invite.created_user = user
            invite.save(update_fields=['status', 'approved_by', 'approved_at', 'created_user'])
            _send_jury_welcome_email(user, password, invite.hackathon)
        messages.success(request, f"Jury member '{user.get_full_name() or user.email}' approved and account created.")
    except Exception as exc:
        logger.error(f'Approve jury invitation {invite_id}: {exc}', exc_info=True)
        messages.error(request, f'Approval failed: {exc}')

    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@require_POST
def reject_jury_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    from django.urls import reverse

    invite = get_object_or_404(JuryInvitation, id=invite_id)
    if invite.status != 'pending':
        messages.warning(request, f"Only pending jury applications can be rejected. Current status: {invite.status}.")
        return render_route(request, '/features/jury/?sub=invitations')
    reason = request.POST.get('rejection_reason', '').strip()
    if not reason:
        messages.error(request, 'Rejection reason is required.')
        return render_route(request, 'view_jury_invitation', invite.id)
    invite.status           = 'rejected'
    invite.rejection_reason = reason
    invite.save(update_fields=['status', 'rejection_reason'])
    form_link = request.build_absolute_uri(reverse('jury_register_form', args=[invite.token]))
    _send_rejection_correction_email(invite.email, form_link, 'Jury', reason, invite.hackathon)
    messages.success(request, f"Jury application for '{invite.email}' rejected.")
    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@require_POST
def suspend_jury_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied

    invite = get_object_or_404(JuryInvitation, id=invite_id)
    if invite.status == 'approved':
        messages.warning(request, 'Approved members must be suspended from the jury roster.')
        return render_route(request, '/features/jury/?sub=invitations')

    if invite.status == 'suspended':
        invite.status = 'pending' if invite.submitted_at else 'invited'
        word = 'reactivated'
    else:
        invite.status = 'suspended'
        word = 'suspended'

    invite.save(update_fields=['status'])
    messages.success(request, f"Jury application for '{invite.email}' {word}.")
    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@never_cache
def view_jury_member(request, jury_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    jury = get_object_or_404(JuryProfile.objects.select_related('user'), id=jury_id)
    invitation = JuryInvitation.objects.filter(created_user=jury.user).first()
    evaluator_profile = EvaluatorProfile.objects.filter(user=jury.user).first()
    testimonial_media_asset = _jury_testimonial_asset(jury.user)
    return render(request, 'features/jury_member_detail.html', {
        'jury': jury,
        'invitation': invitation,
        'evaluator_profile': evaluator_profile,
        'testimonial_media_asset': testimonial_media_asset,
        'tab': 'jury_ops', 'sub': 'jury_roster',
    })


@login_required(login_url='/accounts/')
@never_cache
def edit_jury_member(request, jury_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    jury = get_object_or_404(JuryProfile.objects.select_related('user'), id=jury_id)
    invitation = JuryInvitation.objects.filter(created_user=jury.user).first()

    if request.method == 'POST':
        try:
            user = jury.user
            user.first_name  = request.POST.get('first_name', user.first_name).strip()
            user.last_name   = request.POST.get('last_name', user.last_name).strip()
            user.email       = request.POST.get('email', user.email).strip()
            phone = request.POST.get('phone_number', '').strip()
            if phone:
                user.phone_number = phone
            user.save()

            domain_list = request.POST.getlist('domain')
            if domain_list:
                jury.domain = ", ".join([d.strip() for d in domain_list if d.strip()])
            else:
                jury.domain = request.POST.get('domain', jury.domain or '').strip()

            jury.save()
            messages.success(request, f"Jury member '{user.username}' updated.")
            return render_route(request, 'view_jury_member', jury_id)
        except Exception as exc:
            logger.error(f'Edit jury member {jury_id}: {exc}', exc_info=True)
            messages.error(request, f'Update failed: {exc}')

    target_hackathon = (invitation.hackathon if invitation else None) or Hackathon.objects.first()
    available_domains = []
    if target_hackathon:
        from events.models import HackathonDomain, ProblemStatement
        h_domains = list(HackathonDomain.objects.filter(hackathon=target_hackathon).values_list('name', flat=True))
        ps_domains = list(ProblemStatement.objects.filter(hackathon=target_hackathon).exclude(domain__isnull=True).exclude(domain='').values_list('domain', flat=True).distinct())
        domain_set = set()
        for d in h_domains + ps_domains:
            if d and d not in domain_set:
                domain_set.add(d)
                available_domains.append(d)

    selected_domains = [d.strip() for d in (jury.domain or '').split(',')] if jury.domain else []

    return render(request, 'features/jury_member_detail.html', {
        'jury': jury, 'edit_mode': True,
        'available_domains': available_domains,
        'selected_domains': selected_domains,
        'tab': 'jury_ops', 'sub': 'jury_roster',
    })


@login_required(login_url='/accounts/')
@require_POST
def send_jury_testimonial_to_media(request, jury_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied

    jury = get_object_or_404(JuryProfile.objects.select_related('user'), id=jury_id)
    evaluator_profile = EvaluatorProfile.objects.filter(user=jury.user).first()
    hackathon = _jury_testimonial_hackathon(jury.user)

    if not evaluator_profile or not evaluator_profile.testimonial_video:
        messages.error(request, 'No testimonial video has been uploaded by this jury member yet.')
        return render_route(request, 'view_jury_member', jury_id)
    if not hackathon:
        messages.error(request, 'This jury member is not linked to a hackathon yet.')
        return render_route(request, 'view_jury_member', jury_id)

    CreativeMaterial.objects.update_or_create(
        hackathon=hackathon,
        title=_jury_testimonial_title(jury.user),
        defaults={
            'file': evaluator_profile.testimonial_video,
            'is_published': False,
            'is_suspended': False,
        },
    )
    messages.success(request, 'Testimonial video sent to the Media, Sponsorship & Communication team.')
    return render_route(request, 'view_jury_member', jury_id)


@login_required(login_url='/accounts/')
@require_POST
def toggle_jury_member_status(request, jury_id):
    denied = _feature_permission_required(request, 'jury_onboarding_mgt')
    if denied:
        return denied
    jury = get_object_or_404(JuryProfile.objects.select_related('user'), id=jury_id)
    jury.user.is_active = not jury.user.is_active
    jury.user.save(update_fields=['is_active'])
    action = 'activated' if jury.user.is_active else 'suspended'
    messages.success(request, f'Jury member "{jury.user.get_full_name() or jury.user.email}" {action}.')
    sub = request.GET.get('sub', 'jury_roster')
    if sub not in ['jury_roster', 'invitations']:
        sub = 'jury_roster'
    return render_route(request, f'/features/jury/?sub={sub}')



# ── Expert Onboarding (Generated) ──

@login_required(login_url='/accounts/')
@never_cache
def send_expert_invite(request):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/jury/?sub=invitations')

    from django.urls import reverse
    email        = request.POST.get('email', '').strip().lower()
    hackathon_id = request.POST.get('hackathon_id', '').strip()

    if not email:
        messages.error(request, 'Email address is required.')
        return render_route(request, '/features/jury/?sub=invitations')

    try:
        validate_email(email)
    except ValidationError:
        messages.error(request, 'Invalid email address.')
        return render_route(request, '/features/jury/?sub=invitations')

    if ExpertInvitation.objects.filter(email__iexact=email).exists():
        messages.warning(request, f'An invitation already exists for {email}.')
        return render_route(request, '/features/jury/?sub=invitations')

    if User.objects.filter(email__iexact=email).exists():
        messages.error(request, 'A user with this email already exists.')
        return render_route(request, '/features/jury/?sub=invitations')

    hackathon = None
    if hackathon_id and hackathon_id.isdigit():
        hackathon = Hackathon.objects.filter(id=hackathon_id).first()

    try:
        with transaction.atomic():
            token = uuid.uuid4().hex
            invite = ExpertInvitation.objects.create(
                invited_by=request.user,
                email=email,
                hackathon=hackathon,
                token=token,
                status='invited',
            )
            form_link = request.build_absolute_uri(reverse('expert_register_form', args=[token]))
            _send_expert_invite_email(email, form_link, hackathon)
        messages.success(request, f'Expert invitation sent to {email}.')
    except Exception as exc:
        logger.error(f'Expert invite error {email}: {exc}', exc_info=True)
        messages.error(request, f'Failed to send invitation: {exc}')

    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@never_cache
def send_bulk_expert_invites(request):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied
    if request.method != 'POST':
        return render_route(request, '/features/jury/?sub=invitations')

    from django.urls import reverse
    csv_file     = request.FILES.get('csv_file')
    hackathon_id = request.POST.get('hackathon_id', '').strip()

    if not csv_file:
        messages.error(request, 'Please upload a CSV file.')
        return render_route(request, '/features/jury/?sub=invitations')
    if not csv_file.name.lower().endswith('.csv'):
        messages.error(request, 'Only CSV files are supported.')
        return render_route(request, '/features/jury/?sub=invitations')

    try:
        decoded = csv_file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        messages.error(request, 'CSV file must be UTF-8 encoded.')
        return render_route(request, '/features/jury/?sub=invitations')

    emails = _extract_spoc_emails_from_csv(decoded)  # reuse SPOC CSV parser
    if not emails:
        messages.error(request, 'No valid email entries found in the CSV.')
        return render_route(request, '/features/jury/?sub=invitations')

    hackathon = None
    if hackathon_id and hackathon_id.isdigit():
        hackathon = Hackathon.objects.filter(id=hackathon_id).first()

    sent, failed = 0, []
    for email in emails:
        if ExpertInvitation.objects.filter(email__iexact=email).exists():
            failed.append(f'{email} (already invited)')
            continue
        if User.objects.filter(email__iexact=email).exists():
            failed.append(f'{email} (user exists)')
            continue
        try:
            token = uuid.uuid4().hex
            ExpertInvitation.objects.create(
                invited_by=request.user, email=email,
                hackathon=hackathon, token=token, status='invited',
            )
            form_link = request.build_absolute_uri(reverse('expert_register_form', args=[token]))
            _send_expert_invite_email(email, form_link, hackathon)
            sent += 1
        except Exception as exc:
            failed.append(f'{email} ({exc})')

    if sent:
        messages.success(request, f'Bulk invite complete. {sent} invitation(s) sent.')
    if failed:
        preview = '; '.join(failed[:5])
        extra = f' and {len(failed)-5} more' if len(failed) > 5 else ''
        messages.warning(request, f'{len(failed)} email(s) skipped: {preview}{extra}')

    return render_route(request, '/features/jury/?sub=invitations')


def expert_register_form(request, token):
    """Public token-based self-registration form for expert members."""
    try:
        invitation = ExpertInvitation.objects.get(token=token)
    except ExpertInvitation.DoesNotExist:
        return render(request, 'features/expert_register_invalid.html',
                      {'reason': 'Invalid or expired registration link.'})

    if invitation.status == 'suspended':
        return render(request, 'features/expert_register_invalid.html',
                      {'reason': 'This expert invitation is suspended. Please contact the administrator.'})
    if invitation.status == 'approved':
        return render(request, 'features/expert_register_invalid.html',
                      {'reason': 'This invitation has already been approved. You can now log in.'})
    if invitation.status == 'pending':
        return render(request, 'features/expert_register_invalid.html',
                      {'reason': 'Your application is already submitted and is under review.'})

    if request.method == 'POST':
        try:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone_number = request.POST.get('phone_number', '').strip()
            gender = request.POST.get('gender', '').strip()
            organization = request.POST.get('organization', '').strip()
            designation = request.POST.get('designation', '').strip()
            linkedin_url = request.POST.get('linkedin_url', '').strip()
            bio = request.POST.get('bio', '').strip()

            if not first_name or len(first_name) < 2:
                raise ValueError("First name must be at least 2 characters long.")
            if not last_name or len(last_name) < 2:
                raise ValueError("Last name must be at least 2 characters long.")
            
            phone_number = _clean_indian_phone_number(phone_number)
            
            if not organization or len(organization) < 3:
                raise ValueError("Organization must be at least 3 characters long.")
            if not designation or len(designation) < 2:
                raise ValueError("Designation must be at least 2 characters long.")
                
            domain_list = request.POST.getlist('domain')
            if domain_list:
                domain = ", ".join([d.strip() for d in domain_list if d.strip()])
            else:
                domain = request.POST.get('domain', '').strip()
            if not domain:
                raise ValueError("At least one judging domain/area of expertise must be selected or specified.")
                
            if linkedin_url:
                from django.core.validators import URLValidator
                val_url = URLValidator()
                try:
                    val_url(linkedin_url)
                except ValidationError:
                    raise ValueError("Please enter a valid LinkedIn URL.")
                    
            dob = request.POST.get('date_of_birth', '').strip()
            if dob:
                from datetime import datetime, date
                try:
                    dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                    today = date.today()
                    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                    if age < 18:
                        raise ValueError("Expert member must be at least 18 years old.")
                except ValueError as e:
                    if "18" in str(e):
                        raise e
                    raise ValueError("Please enter a valid date of birth in YYYY-MM-DD format.")
            else:
                dob_date = None

            if not invitation.id_proof and 'id_proof' not in request.FILES:
                raise ValueError("Government ID Proof is required.")
            if 'id_proof' in request.FILES:
                _validate_document_file(request.FILES['id_proof'], "Government ID proof")
            if 'photo' in request.FILES:
                _validate_image_file(request.FILES['photo'], "Photo")

            invitation.first_name = first_name
            invitation.last_name = last_name
            invitation.phone_number = phone_number
            invitation.gender = gender
            invitation.organization = organization
            invitation.designation = designation
            invitation.domain = domain
            invitation.linkedin_url = linkedin_url
            invitation.bio = bio
            invitation.date_of_birth = dob_date
            
            if 'id_proof' in request.FILES:
                invitation.id_proof = request.FILES['id_proof']
            if 'photo' in request.FILES:
                invitation.photo = request.FILES['photo']
                
            invitation.status       = 'pending'
            invitation.rejection_reason = ''
            invitation.submitted_at = timezone.now()
            invitation.save()
            return render(request, 'features/expert_register_success.html',
                          {'email': invitation.email})
        except Exception as exc:
            logger.error(f'Expert form token {token}: {exc}', exc_info=True)
            messages.error(request, f'Submission failed: {exc}')

    available_domains = []
    if invitation.hackathon:
        from events.models import HackathonDomain, ProblemStatement
        h_domains = list(HackathonDomain.objects.filter(hackathon=invitation.hackathon).values_list('name', flat=True))
        ps_domains = list(ProblemStatement.objects.filter(hackathon=invitation.hackathon).exclude(domain__isnull=True).exclude(domain='').values_list('domain', flat=True).distinct())
        domain_set = set()
        for d in h_domains + ps_domains:
            if d and d not in domain_set:
                domain_set.add(d)
                available_domains.append(d)

    selected_domains = [d.strip() for d in (invitation.domain or '').split(',')] if invitation.domain else []

    return render(request, 'features/expert_register_form.html', {
        'invitation': invitation,
        'is_rejected_resubmission': invitation.status == 'rejected',
        'available_domains': available_domains,
        'selected_domains': selected_domains,
    })


@login_required(login_url='/accounts/')
@never_cache
def view_expert_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied
    invite = get_object_or_404(
        ExpertInvitation.objects.select_related('invited_by', 'hackathon', 'approved_by', 'created_user'),
        id=invite_id
    )
    return render(request, 'features/expert_invitation_detail.html', {
        'invite': invite, 'tab': 'expert_ops', 'sub': 'invitations',
    })


@login_required(login_url='/accounts/')
@never_cache
def edit_expert_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied
    invite = get_object_or_404(ExpertInvitation, id=invite_id)

    if invite.status == 'approved':
        messages.warning(request, 'Approved expert members should be edited from their profile page.')
        return render_route(request, '/features/jury/?sub=invitations')

    if request.method == 'POST':
        try:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip().lower()
            phone_number = request.POST.get('phone_number', '').strip()
            gender = request.POST.get('gender', '').strip()
            organization = request.POST.get('organization', '').strip()
            designation = request.POST.get('designation', '').strip()
            linkedin_url = request.POST.get('linkedin_url', '').strip()
            bio = request.POST.get('bio', '').strip()

            if not first_name or len(first_name) < 2:
                raise ValueError("First name must be at least 2 characters long.")
            if not last_name or len(last_name) < 2:
                raise ValueError("Last name must be at least 2 characters long.")
            
            if not email:
                raise ValueError("Email is required.")
            try:
                validate_email(email)
            except ValidationError:
                raise ValueError("Please enter a valid email address.")
                
            if email != invite.email:
                if ExpertInvitation.objects.filter(email=email).exclude(id=invite.id).exists():
                    raise ValueError(f"An invitation already exists for {email}.")
                if User.objects.filter(email=email).exists():
                    raise ValueError("A user with this email already exists.")
            
            phone_number = _clean_indian_phone_number(phone_number)
            
            if not organization or len(organization) < 3:
                raise ValueError("Organization must be at least 3 characters long.")
            if not designation or len(designation) < 2:
                raise ValueError("Designation must be at least 2 characters long.")
                
            domain_list = request.POST.getlist('domain')
            if domain_list:
                domain = ", ".join([d.strip() for d in domain_list if d.strip()])
            else:
                domain = request.POST.get('domain', '').strip()
            if not domain:
                raise ValueError("At least one judging domain/area of expertise must be selected or specified.")
                
            if linkedin_url:
                from django.core.validators import URLValidator
                val_url = URLValidator()
                try:
                    val_url(linkedin_url)
                except ValidationError:
                    raise ValueError("Please enter a valid LinkedIn URL.")
                    
            dob = request.POST.get('date_of_birth', '').strip()
            if dob:
                from datetime import datetime, date
                try:
                    dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
                    today = date.today()
                    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
                    if age < 18:
                        raise ValueError("Expert member must be at least 18 years old.")
                except ValueError as e:
                    if "18" in str(e):
                        raise e
                    raise ValueError("Please enter a valid date of birth in YYYY-MM-DD format.")
            else:
                dob_date = None

            if 'id_proof' in request.FILES:
                _validate_document_file(request.FILES['id_proof'], "Government ID proof")
            if 'photo' in request.FILES:
                _validate_image_file(request.FILES['photo'], "Photo")

            invite.first_name = first_name
            invite.last_name = last_name
            invite.email = email
            invite.phone_number = phone_number
            invite.gender = gender
            invite.organization = organization
            invite.designation = designation
            invite.domain = domain
            invite.linkedin_url = linkedin_url
            invite.bio = bio
            invite.date_of_birth = dob_date
            
            if 'id_proof' in request.FILES:
                invite.id_proof = request.FILES['id_proof']
            if 'photo' in request.FILES:
                invite.photo = request.FILES['photo']
                
            invite.save()
            messages.success(request, f"Expert application for '{invite.email}' updated.")
            return render_route(request, 'view_expert_invitation', invite.id)
        except Exception as exc:
            logger.error(f'Edit expert invitation {invite_id}: {exc}', exc_info=True)
            messages.error(request, f'Update failed: {exc}')

    return render(request, 'features/expert_invitation_edit.html', {
        'invite': invite, 'tab': 'expert_ops', 'sub': 'invitations',
    })


@login_required(login_url='/accounts/')
@require_POST
def approve_expert_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied

    invite = get_object_or_404(ExpertInvitation, id=invite_id)
    if invite.status != 'pending':
        messages.warning(request, f"Invitation status is '{invite.status}'. Only pending applications can be approved.")
        return render_route(request, '/features/jury/?sub=invitations')

    expert_role = Role.objects.filter(name__iexact='Expert').first()
    if not expert_role:
        messages.error(request, "The 'Expert' role is missing. Please create it in the admin panel first.")
        return render_route(request, '/features/jury/?sub=invitations')

    try:
        with transaction.atomic():
            password = _build_portal_password()
            user = User.objects.create_user(
                username=_build_unique_username(invite.email, 'expert'),
                email=invite.email,
                password=password,
                first_name=invite.first_name,
                last_name=invite.last_name,
                phone_number=invite.phone_number or None,
                gender=invite.gender or None,
                date_of_birth=invite.date_of_birth,
                role=expert_role,
                is_active=True,
                is_verified=True,
            )
            ExpertProfile.objects.create(user=user, domain=invite.domain)
            invite.status      = 'approved'
            invite.approved_by = request.user
            invite.approved_at = timezone.now()
            invite.created_user = user
            invite.save(update_fields=['status', 'approved_by', 'approved_at', 'created_user'])
            _send_jury_welcome_email(user, password, invite.hackathon)
        messages.success(request, f"Expert member '{user.get_full_name() or user.email}' approved and account created.")
    except Exception as exc:
        logger.error(f'Approve expert invitation {invite_id}: {exc}', exc_info=True)
        messages.error(request, f'Approval failed: {exc}')

    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@require_POST
def reject_expert_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied
    from django.urls import reverse

    invite = get_object_or_404(ExpertInvitation, id=invite_id)
    if invite.status != 'pending':
        messages.warning(request, f"Only pending expert applications can be rejected. Current status: {invite.status}.")
        return render_route(request, '/features/jury/?sub=invitations')
    reason = request.POST.get('rejection_reason', '').strip()
    if not reason:
        messages.error(request, 'Rejection reason is required.')
        return render_route(request, 'view_expert_invitation', invite.id)
    invite.status           = 'rejected'
    invite.rejection_reason = reason
    invite.save(update_fields=['status', 'rejection_reason'])
    form_link = request.build_absolute_uri(reverse('expert_register_form', args=[invite.token]))
    _send_rejection_correction_email(invite.email, form_link, 'Expert', reason, invite.hackathon)
    messages.success(request, f"Expert application for '{invite.email}' rejected.")
    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@require_POST
def suspend_expert_invitation(request, invite_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied

    invite = get_object_or_404(ExpertInvitation, id=invite_id)
    if invite.status == 'approved':
        messages.warning(request, 'Approved members must be suspended from the expert roster.')
        return render_route(request, '/features/jury/?sub=invitations')

    if invite.status == 'suspended':
        invite.status = 'pending' if invite.submitted_at else 'invited'
        word = 'reactivated'
    else:
        invite.status = 'suspended'
        word = 'suspended'

    invite.save(update_fields=['status'])
    messages.success(request, f"Expert application for '{invite.email}' {word}.")
    return render_route(request, '/features/jury/?sub=invitations')


@login_required(login_url='/accounts/')
@never_cache
def view_expert_member(request, expert_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied
    expert = get_object_or_404(ExpertProfile.objects.select_related('user'), id=expert_id)
    invitation = ExpertInvitation.objects.filter(created_user=expert.user).first()
    evaluator_profile = EvaluatorProfile.objects.filter(user=expert.user).first()
    testimonial_media_asset = _expert_testimonial_asset(expert.user)
    return render(request, 'features/expert_member_detail.html', {
        'expert': expert, 'invitation': invitation,
        'evaluator_profile': evaluator_profile,
        'testimonial_media_asset': testimonial_media_asset,
        'tab': 'expert_ops', 'sub': 'expert_roster',
    })


@login_required(login_url='/accounts/')
@never_cache
def edit_expert_member(request, expert_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied
    expert = get_object_or_404(ExpertProfile.objects.select_related('user'), id=expert_id)
    invitation = ExpertInvitation.objects.filter(created_user=expert.user).first()

    if request.method == 'POST':
        try:
            user = expert.user
            user.first_name  = request.POST.get('first_name', user.first_name).strip()
            user.last_name   = request.POST.get('last_name', user.last_name).strip()
            user.email       = request.POST.get('email', user.email).strip()
            phone = request.POST.get('phone_number', '').strip()
            if phone:
                user.phone_number = phone
            user.save()

            domain_list = request.POST.getlist('domain')
            if domain_list:
                expert.domain = ", ".join([d.strip() for d in domain_list if d.strip()])
            else:
                expert.domain = request.POST.get('domain', expert.domain or '').strip()

            expert.save()
            messages.success(request, f"Expert member '{user.username}' updated.")
            return render_route(request, 'view_expert_member', expert_id)
        except Exception as exc:
            logger.error(f'Edit expert member {expert_id}: {exc}', exc_info=True)
            messages.error(request, f'Update failed: {exc}')

    target_hackathon = (invitation.hackathon if invitation else None) or Hackathon.objects.first()
    available_domains = []
    if target_hackathon:
        from events.models import HackathonDomain, ProblemStatement
        h_domains = list(HackathonDomain.objects.filter(hackathon=target_hackathon).values_list('name', flat=True))
        ps_domains = list(ProblemStatement.objects.filter(hackathon=target_hackathon).exclude(domain__isnull=True).exclude(domain='').values_list('domain', flat=True).distinct())
        domain_set = set()
        for d in h_domains + ps_domains:
            if d and d not in domain_set:
                domain_set.add(d)
                available_domains.append(d)

    selected_domains = [d.strip() for d in (expert.domain or '').split(',')] if expert.domain else []

    return render(request, 'features/expert_member_detail.html', {
        'expert': expert, 'edit_mode': True,
        'available_domains': available_domains,
        'selected_domains': selected_domains,
        'tab': 'expert_ops', 'sub': 'expert_roster',
    })


@login_required(login_url='/accounts/')
@require_POST
def send_expert_testimonial_to_media(request, expert_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied

    expert = get_object_or_404(ExpertProfile.objects.select_related('user'), id=expert_id)
    evaluator_profile = EvaluatorProfile.objects.filter(user=expert.user).first()
    hackathon = _expert_testimonial_hackathon(expert.user)

    if not evaluator_profile or not evaluator_profile.testimonial_video:
        messages.error(request, 'No testimonial video has been uploaded by this expert member yet.')
        return render_route(request, 'view_expert_member', expert_id)
    if not hackathon:
        messages.error(request, 'This expert member is not linked to a hackathon yet.')
        return render_route(request, 'view_expert_member', expert_id)

    CreativeMaterial.objects.update_or_create(
        hackathon=hackathon,
        title=_expert_testimonial_title(expert.user),
        defaults={
            'file': evaluator_profile.testimonial_video,
            'is_published': False,
            'is_suspended': False,
        },
    )
    messages.success(request, 'Expert testimonial video sent to the Media, Sponsorship & Communication team.')
    return render_route(request, 'view_expert_member', expert_id)


@login_required(login_url='/accounts/')
@require_POST
def toggle_expert_member_status(request, expert_id):
    denied = _feature_permission_required(request, 'expert_onboarding_mgt')
    if denied:
        return denied
    expert = get_object_or_404(ExpertProfile.objects.select_related('user'), id=expert_id)
    expert.user.is_active = not expert.user.is_active
    expert.user.save(update_fields=['is_active'])
    action = 'activated' if expert.user.is_active else 'suspended'
    messages.success(request, f'Expert member "{expert.user.get_full_name() or expert.user.email}" {action}.')
    sub = request.GET.get('sub', 'expert_roster')
    if sub not in ['expert_roster', 'invitations']:
        sub = 'expert_roster'
    return render_route(request, f'/features/jury/?sub={sub}')



@login_required(login_url='/accounts/')
@require_POST
def save_marking_parameter(request):
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    round_number = request.POST.get('round_number')
    name         = request.POST.get('name', '').strip()
    param_id     = request.POST.get('param_id', '').strip()

    if not hackathon_id or not round_number or not name:
        messages.error(request, 'Hackathon, round, and parameter name are required.')
        return render_route(request, f'/features/jury/?sub=evaluation&hackathon={hackathon_id}')

    try:
        if param_id:
            param = RoundMarkingParameter.objects.get(id=param_id)
            param.round_number = int(round_number)
            param.name = name
            param.save(update_fields=['round_number', 'name'])
            messages.success(request, 'Marking parameter updated.')
        else:
            RoundMarkingParameter.objects.create(
                hackathon_id=hackathon_id,
                round_number=int(round_number),
                name=name,
            )
            messages.success(request, 'Marking parameter added.')
    except Exception as exc:
        messages.error(request, f'Unable to save marking parameter: {exc}')

    return render_route(request, f'/features/jury/?sub=evaluation&hackathon={hackathon_id}')


@login_required(login_url='/accounts/')
@require_POST
def delete_marking_parameter(request, param_id):
    denied = _feature_permission_required(request, 'evaluation_coordination')
    if denied:
        return denied

    param = get_object_or_404(RoundMarkingParameter, id=param_id)
    hackathon_id = param.hackathon_id
    param.delete()
    messages.success(request, 'Marking parameter removed.')

@login_required(login_url='/accounts/')
@never_cache
def media_communications_management(request):
    denied = _feature_permission_required(
        request,
        'social_media_creative_mgt',
        'media_sponsorship_mgt',
        'announcement_communication_sys',
    )
    if denied:
        return denied

    hackathons, hackathon_filter, active_hackathon = _resolve_hackathon_scope(request)
    focus = request.GET.get('focus', 'creative-elements')
    testimonial_kind = request.GET.get('testimonial_kind', 'jury').strip().lower()
    if testimonial_kind not in TESTIMONIAL_PREFIX_MAP:
        testimonial_kind = 'jury'
    selected_testimonial_id = request.GET.get('testimonial', '').strip()
    edit_testimonial_id = request.GET.get('edit', '').strip()

    creatives = CreativeMaterial.objects.none()
    creative_items = []
    gallery_items = []
    news_items = []
    feed_items = []
    testimonial_lists = {key: [] for key in TESTIMONIAL_PREFIX_MAP}
    selected_testimonial = None
    edit_testimonial = None
    current_testimonials = []
    total_testimonials = 0
    edit_creative = None
    edit_gallery = None
    edit_news = None
    edit_news_kind = 'news'
    edit_feed = None
    edit_creative_id = request.GET.get('edit_creative', '').strip()
    edit_gallery_id = request.GET.get('edit_gallery', '').strip()
    edit_news_id = request.GET.get('edit_news', '').strip()
    edit_feed_id = request.GET.get('edit_feed', '').strip()
    edit_voice_inspiration_id = request.GET.get('edit_voice_inspiration', '').strip()
    voice_inspiration_items = []
    edit_voice_inspiration = None
    faq_items = []
    edit_faq = None
    edit_faq_id = request.GET.get('edit_faq', '').strip()

    if active_hackathon:
        creative_queryset = CreativeMaterial.objects.filter(hackathon=active_hackathon).order_by('-uploaded_at')
        testimonial_filter = (
            Q(title__startswith=JURY_TESTIMONIAL_PREFIX) |
            Q(title__startswith=EXPERT_TESTIMONIAL_PREFIX) |
            Q(title__startswith=TEAM_TESTIMONIAL_PREFIX) |
            Q(title__startswith=VIP_TESTIMONIAL_PREFIX) |
            Q(title__startswith=GALLERY_PREFIX) |
            Q(title__icontains='testimonial')
        )
        creatives = creative_queryset.exclude(testimonial_filter).exclude(
            Q(material_type='voice_of_inspiration') | Q(landing_sections__contains='voice-of-inspiration')
        )
        voice_inspiration_assets = creative_queryset.filter(
            Q(material_type='voice_of_inspiration') | Q(landing_sections__contains='voice-of-inspiration')
        ).order_by('-uploaded_at')
        voice_inspiration_items = [
            {
                'asset': asset,
                'display_title': asset.speaker_name or _display_asset_title(asset.title),
            }
            for asset in voice_inspiration_assets
        ]
        gallery_assets = _extract_prefixed_assets(creative_queryset, GALLERY_PREFIX)
        creative_items = [
            {
                'asset': asset,
                'display_title': _display_asset_title(asset.title),
                'landing_section': _extract_landing_section(asset.title),
                'landing_section_label': LANDING_SECTION_LABELS.get(_extract_landing_section(asset.title), 'Not selected'),
            }
            for asset in creatives
        ]
        gallery_items = [
            {
                'asset': asset,
                'display_title': _normalize_testimonial_title(_strip_asset_prefix(asset.title, GALLERY_PREFIX)),
            }
            for asset in gallery_assets
        ]
        news_queryset = Documentation.objects.filter(
            hackathon=active_hackathon,
        ).filter(
            Q(title__startswith=NEWS_PREFIX) | Q(title__startswith=ANNOUNCEMENT_PREFIX)
        ).order_by('-created_at')
        news_items = [
            {
                'item': item,
                'display_title': _strip_landing_section(
                    _strip_asset_prefix(_strip_asset_prefix(item.title, NEWS_PREFIX), ANNOUNCEMENT_PREFIX)
                ),
                'kind': _news_item_kind(item.title),
                'kind_label': 'Announcement' if _news_item_kind(item.title) == 'announcement' else 'News',
            }
            for item in news_queryset
        ]
        feed_queryset = Documentation.objects.filter(
            hackathon=active_hackathon,
            title__startswith=FEED_PREFIX,
        ).order_by('-created_at')
        feed_items = []
        for item in feed_queryset:
            parsed = _parse_feed_description(item.description)
            feed_items.append({
                'item': item,
                'display_title': _normalize_testimonial_title(_strip_asset_prefix(item.title, FEED_PREFIX)),
                'platform': parsed['platform'],
                'platform_label': FEED_PLATFORM_LABELS.get(parsed['platform'], 'Other'),
                'published_date': parsed['published_date'],
            })
        jury_assets = _extract_testimonial_assets(creative_queryset, 'jury')
        expert_assets = _extract_testimonial_assets(creative_queryset, 'expert')
        team_assets = _extract_testimonial_assets(creative_queryset, 'team')
        vip_assets = _extract_testimonial_assets(creative_queryset, 'vip')
        jury_users = {
            user.id: user
            for user in User.objects.filter(
                from_jury_invitation__hackathon=active_hackathon
            ).select_related('from_jury_invitation')
        }
        expert_users = {
            user.id: user
            for user in User.objects.filter(
                from_expert_invitation__hackathon=active_hackathon
            ).select_related('from_expert_invitation')
        }
        evaluator_profiles = {
            profile.user_id: profile
            for profile in EvaluatorProfile.objects.filter(user_id__in=list(jury_users.keys()) + list(expert_users.keys()))
        }
        for asset in jury_assets:
            user_id = None
            try:
                user_id = int(asset.title.replace(JURY_TESTIMONIAL_PREFIX, '', 1).strip().split('|', 1)[0].strip())
            except (TypeError, ValueError, IndexError):
                user_id = None
            user = jury_users.get(user_id)
            testimonial_lists['jury'].append({
                'asset': asset,
                'user': user,
                'profile': evaluator_profiles.get(user.id) if user else None,
                'kind': 'jury',
                'display_title': (user.get_full_name() or user.username) if user else _normalize_testimonial_title(asset.title),
                'landing_section': _extract_landing_section(_strip_asset_prefix(asset.title, JURY_TESTIMONIAL_PREFIX)),
                'landing_section_label': LANDING_SECTION_LABELS.get(_extract_landing_section(_strip_asset_prefix(asset.title, JURY_TESTIMONIAL_PREFIX)), 'Not selected'),
            })
        for asset in expert_assets:
            user_id = None
            try:
                user_id = int(asset.title.replace(EXPERT_TESTIMONIAL_PREFIX, '', 1).strip().split('|', 1)[0].strip())
            except (TypeError, ValueError, IndexError):
                user_id = None
            user = expert_users.get(user_id)
            profile = evaluator_profiles.get(user.id) if user else None
            testimonial_lists['expert'].append({
                'asset': asset,
                'user': user,
                'profile': profile,
                'kind': 'expert',
                'display_title': (user.get_full_name() or user.username) if user else _normalize_testimonial_title(asset.title),
                'landing_section': _extract_landing_section(_strip_asset_prefix(asset.title, EXPERT_TESTIMONIAL_PREFIX)),
                'landing_section_label': LANDING_SECTION_LABELS.get(_extract_landing_section(_strip_asset_prefix(asset.title, EXPERT_TESTIMONIAL_PREFIX)), 'Not selected'),
            })
        for asset in team_assets:
            testimonial_lists['team'].append({
                'asset': asset,
                'user': None,
                'profile': None,
                'kind': 'team',
                'display_title': _normalize_testimonial_title(asset.title),
                'landing_section': _extract_landing_section(_strip_asset_prefix(asset.title, TEAM_TESTIMONIAL_PREFIX)),
                'landing_section_label': LANDING_SECTION_LABELS.get(_extract_landing_section(_strip_asset_prefix(asset.title, TEAM_TESTIMONIAL_PREFIX)), 'Not selected'),
            })
        for asset in vip_assets:
            testimonial_lists['vip'].append({
                'asset': asset,
                'user': None,
                'profile': None,
                'kind': 'vip',
                'display_title': _normalize_testimonial_title(asset.title),
                'landing_section': _extract_landing_section(_strip_asset_prefix(asset.title, VIP_TESTIMONIAL_PREFIX)),
                'landing_section_label': LANDING_SECTION_LABELS.get(_extract_landing_section(_strip_asset_prefix(asset.title, VIP_TESTIMONIAL_PREFIX)), 'Not selected'),
            })

        if selected_testimonial_id.isdigit():
            selected_id = int(selected_testimonial_id)
            for item in testimonial_lists.get(testimonial_kind, []):
                if item['asset'].id == selected_id:
                    selected_testimonial = item
                    break
        if edit_testimonial_id.isdigit():
            edit_id = int(edit_testimonial_id)
            for item in testimonial_lists.get(testimonial_kind, []):
                if item['asset'].id == edit_id:
                    edit_testimonial = item
                    break
        current_testimonials = testimonial_lists.get(testimonial_kind, [])
        total_testimonials = sum(len(items) for items in testimonial_lists.values())
        if edit_creative_id.isdigit():
            edit_creative = next((item for item in creative_items if item['asset'].id == int(edit_creative_id)), None)
        if edit_gallery_id.isdigit():
            edit_gallery = next((item for item in gallery_items if item['asset'].id == int(edit_gallery_id)), None)
        if edit_news_id.isdigit():
            edit_news = next((item for item in news_items if item['item'].id == int(edit_news_id)), None)
            if edit_news:
                edit_news_kind = edit_news['kind']
        if edit_feed_id.isdigit():
            edit_feed = next((item for item in feed_items if item['item'].id == int(edit_feed_id)), None)
        if edit_voice_inspiration_id.isdigit():
            edit_voice_inspiration = next((item for item in voice_inspiration_items if item['asset'].id == int(edit_voice_inspiration_id)), None)

        # FAQ items
        faq_items = list(FAQItem.objects.filter(hackathon=active_hackathon).order_by('display_order', '-created_at'))
        if edit_faq_id.isdigit():
            edit_faq = next((item for item in faq_items if item.id == int(edit_faq_id)), None)

    context = _feature_context(
        request,
        tab='media_ops',
        focus=focus,
        testimonial_kind=testimonial_kind,
        hackathons=hackathons,
        hackathon_filter=hackathon_filter,
        active_hackathon=active_hackathon,
        creatives=creatives,
        creative_items=creative_items,
        gallery_items=gallery_items,
        news_items=news_items,
        feed_items=feed_items,
        testimonial_lists=testimonial_lists,
        current_testimonials=current_testimonials,
        total_testimonials=total_testimonials,
        selected_testimonial=selected_testimonial,
        edit_testimonial=edit_testimonial,
        edit_creative=edit_creative,
        edit_gallery=edit_gallery,
        edit_news=edit_news,
        edit_news_kind=edit_news_kind,
        edit_feed=edit_feed,
        landing_section_choices=LANDING_SECTION_CHOICES,
        feed_platform_choices=FEED_PLATFORM_CHOICES,
        voice_inspiration_items=voice_inspiration_items,
        edit_voice_inspiration=edit_voice_inspiration,
        faq_items=faq_items,
        edit_faq=edit_faq,
    )
    return render(request, 'features/media_communications.html', context)


@login_required(login_url='/accounts/')
@require_POST
def save_creative_asset(request):
    denied = _feature_permission_required(request, 'social_media_creative_mgt', 'media_sponsorship_mgt')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    title = request.POST.get('title', '').strip()
    creative_id = request.POST.get('creative_id', '').strip()
    action = request.POST.get('action', 'draft')
    upload = request.FILES.get('file')
    asset_kind = request.POST.get('asset_kind', 'creative').strip()
    focus = request.POST.get('focus', 'creative-elements').strip() or 'creative-elements'
    testimonial_kind = request.POST.get('testimonial_kind', 'jury').strip().lower()
    if testimonial_kind not in TESTIMONIAL_PREFIX_MAP:
        testimonial_kind = 'jury'

    # Voice of Inspiration sends the image as 'profile_image', not 'file'
    is_voice_inspiration = (focus == 'voice-inspiration')
    profile_image_upload = request.FILES.get('profile_image')
    if is_voice_inspiration and upload is None:
        upload = profile_image_upload

    landing_sections = _clean_landing_sections(request.POST.getlist('landing_sections'))
    legacy_landing_section = request.POST.get('landing_section', '').strip()
    if not landing_sections and legacy_landing_section:
        landing_sections = _clean_landing_sections([legacy_landing_section])
    if not landing_sections:
        if is_voice_inspiration:
            landing_sections = ['voice-of-inspiration']
        elif asset_kind == 'testimonial':
            landing_sections = ['testimonials']
        elif asset_kind == 'gallery':
            landing_sections = ['gallery']
        else:
            landing_sections = ['gallery']

    if not hackathon_id or not title:
        label = 'testimonial' if asset_kind == 'testimonial' else 'creative element'
        messages.error(request, f'Hackathon and title are required for {label}s.')
        suffix = f'&testimonial_kind={testimonial_kind}' if focus == 'testimonials' else ''
        return redirect(f'/features/media-comms/?focus={focus}&hackathon={hackathon_id}{suffix}')

    if asset_kind == 'testimonial':
        stored_title = _testimonial_title(testimonial_kind, title, landing_sections[0] if landing_sections else '')
    elif asset_kind == 'gallery':
        stored_title = _prefixed_title(GALLERY_PREFIX, title)
    else:
        stored_title = _attach_landing_section(title, landing_sections[0] if landing_sections else '')

    # Voice of Inspiration extra fields
    voi_speaker_name = request.POST.get('title', '').strip() if is_voice_inspiration else ''
    voi_designation = request.POST.get('designation', '').strip() if is_voice_inspiration else ''
    voi_institute = request.POST.get('institute_name', '').strip() if is_voice_inspiration else ''
    voi_quote = request.POST.get('quote_text', '').strip() if is_voice_inspiration else ''
    voi_priority = 0
    if is_voice_inspiration:
        try:
            voi_priority = int(request.POST.get('display_priority', 0))
        except (ValueError, TypeError):
            voi_priority = 0

    try:
        if creative_id:
            creative = CreativeMaterial.objects.get(id=creative_id)
            creative.hackathon_id = hackathon_id
            creative.title = stored_title
            if upload:
                creative.file = upload
            creative.is_published = action == 'publish'
            creative.landing_sections = landing_sections
            if is_voice_inspiration:
                creative.speaker_name = voi_speaker_name
                creative.designation = voi_designation
                creative.institute_name = voi_institute
                creative.quote_text = voi_quote
                creative.display_priority = voi_priority
                if profile_image_upload:
                    creative.profile_image = profile_image_upload
            elif asset_kind == 'testimonial':
                creative.speaker_name = request.POST.get('speaker_name', '').strip()
                creative.designation = request.POST.get('designation', '').strip()
                creative.institute_name = request.POST.get('institute_name', '').strip()
                creative.quote_text = request.POST.get('quote_text', '').strip()
                if profile_image_upload:
                    creative.profile_image = profile_image_upload
            creative.save()
            label = (
                'Voice of Inspiration item' if is_voice_inspiration
                else f'{testimonial_kind.title()} testimonial' if asset_kind == 'testimonial'
                else 'media gallery item' if asset_kind == 'gallery'
                else 'creative element'
            )
            messages.success(request, f'{label.title()} "{title}" updated.')
        else:
            if upload is None and not is_voice_inspiration:
                label = 'testimonial video' if asset_kind == 'testimonial' else 'gallery image' if asset_kind == 'gallery' else 'creative file'
                messages.error(request, f'Please upload a {label}.')
                suffix = f'&testimonial_kind={testimonial_kind}' if focus == 'testimonials' else ''
                return redirect(f'/features/media-comms/?focus={focus}&hackathon={hackathon_id}{suffix}')
            if is_voice_inspiration and not profile_image_upload:
                messages.error(request, 'Please upload a profile image for Voice of Inspiration.')
                return redirect(f'/features/media-comms/?focus={focus}&hackathon={hackathon_id}')

            create_kwargs = {
                'hackathon_id': hackathon_id,
                'title': stored_title,
                'is_published': action == 'publish',
                'landing_sections': landing_sections,
            }
            if is_voice_inspiration:
                create_kwargs['file'] = profile_image_upload
                create_kwargs['profile_image'] = profile_image_upload
                create_kwargs['speaker_name'] = voi_speaker_name
                create_kwargs['designation'] = voi_designation
                create_kwargs['institute_name'] = voi_institute
                create_kwargs['quote_text'] = voi_quote
                create_kwargs['display_priority'] = voi_priority
                create_kwargs['material_type'] = 'voice_of_inspiration'
            elif asset_kind == 'testimonial':
                create_kwargs['file'] = upload
                create_kwargs['speaker_name'] = request.POST.get('speaker_name', '').strip()
                create_kwargs['designation'] = request.POST.get('designation', '').strip()
                create_kwargs['institute_name'] = request.POST.get('institute_name', '').strip()
                create_kwargs['quote_text'] = request.POST.get('quote_text', '').strip()
                create_kwargs['material_type'] = 'testimonial'
                if profile_image_upload:
                    create_kwargs['profile_image'] = profile_image_upload
            else:
                create_kwargs['file'] = upload

            CreativeMaterial.objects.create(**create_kwargs)
            label = (
                'Voice of Inspiration item' if is_voice_inspiration
                else f'{testimonial_kind.title()} testimonial' if asset_kind == 'testimonial'
                else 'media gallery item' if asset_kind == 'gallery'
                else 'creative element'
            )
            messages.success(request, f'{label.title()} "{title}" created.')
    except Exception as exc:
        messages.error(request, f'Unable to save item: {exc}')

    suffix = f'&testimonial_kind={testimonial_kind}' if focus == 'testimonials' else ''
    return redirect(f'/features/media-comms/?focus={focus}&hackathon={hackathon_id}{suffix}')


@login_required(login_url='/accounts/')
@require_POST
def toggle_creative_asset_status(request, creative_id):
    denied = _feature_permission_required(request, 'social_media_creative_mgt', 'media_sponsorship_mgt')
    if denied:
        return denied

    creative = get_object_or_404(CreativeMaterial, id=creative_id)
    focus = request.POST.get('focus', 'creative-elements').strip() or 'creative-elements'
    creative.is_suspended = not creative.is_suspended
    creative.save(update_fields=['is_suspended'])
    state = 'suspended' if creative.is_suspended else 'reactivated'
    messages.success(request, f'Item "{_normalize_testimonial_title(creative.title)}" {state}.')
    testimonial_kind = request.POST.get('testimonial_kind', '').strip().lower()
    suffix = f'&testimonial_kind={testimonial_kind}' if focus == 'testimonials' and testimonial_kind in TESTIMONIAL_PREFIX_MAP else ''
    return redirect(f'/features/media-comms/?focus={focus}&hackathon={creative.hackathon_id}{suffix}')


@login_required(login_url='/accounts/')
@require_POST
def save_news_press_item(request):
    denied = _feature_permission_required(request, 'social_media_creative_mgt', 'media_sponsorship_mgt')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    title = request.POST.get('title', '').strip()
    item_id = request.POST.get('item_id', '').strip()
    news_kind = request.POST.get('news_kind', 'news').strip().lower()
    action = request.POST.get('action', 'draft')
    upload = request.FILES.get('file')
    external_url = request.POST.get('external_url', '').strip()
    landing_sections = _clean_landing_sections(request.POST.getlist('landing_sections'))
    if not landing_sections:
        landing_sections = ['latest-news']
    prefix = ANNOUNCEMENT_PREFIX if news_kind == 'announcement' else NEWS_PREFIX
    kind_label = 'Announcement' if news_kind == 'announcement' else 'News'

    if not hackathon_id or not title:
        messages.error(request, 'Hackathon and title are required for news and press releases.')
        return render_route(request, f'/features/media-comms/?focus=news-press-release&hackathon={hackathon_id}')

    try:
        if item_id:
            item = Documentation.objects.get(id=item_id)
            item.hackathon_id = hackathon_id
            item.title = _prefixed_title(prefix, title)
            item.external_url = external_url
            if upload:
                item.file = upload
            item.is_published = action == 'publish'
            item.landing_sections = landing_sections
            item.save()
            messages.success(request, f'{kind_label} "{title}" updated.')
        else:
            Documentation.objects.create(
                hackathon_id=hackathon_id,
                title=_prefixed_title(prefix, title),
                doc_type='other',
                file=upload,
                external_url=external_url,
                is_published=action == 'publish',
                created_by=request.user,
                landing_sections=landing_sections,
            )
            messages.success(request, f'{kind_label} "{title}" created.')
    except Exception as exc:
        messages.error(request, f'Unable to save {kind_label.lower()}: {exc}')

    return render_route(request, f'/features/media-comms/?focus=news-press-release&hackathon={hackathon_id}')


@login_required(login_url='/accounts/')
@require_POST
def save_social_feed_item(request):
    denied = _feature_permission_required(request, 'social_media_creative_mgt', 'media_sponsorship_mgt')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    title = request.POST.get('title', '').strip()
    item_id = request.POST.get('item_id', '').strip()
    platform = request.POST.get('platform', 'other').strip().lower()
    published_date = request.POST.get('published_date', '').strip()
    external_url = request.POST.get('external_url', '').strip()
    action = request.POST.get('action', 'publish')

    if platform not in FEED_PLATFORM_LABELS:
        platform = 'other'

    if not hackathon_id or not title or not published_date or not external_url:
        messages.error(request, 'Title, date, platform, and URL are required for feeds.')
        return render_route(request, f'/features/media-comms/?focus=feeds&hackathon={hackathon_id}')

    try:
        if item_id:
            item = Documentation.objects.get(id=item_id)
            item.hackathon_id = hackathon_id
            item.title = _prefixed_title(FEED_PREFIX, title)
            item.external_url = external_url
            item.description = _feed_description(platform, published_date)
            item.is_published = action == 'publish'
            item.save()
            messages.success(request, f'Feed "{title}" updated.')
        else:
            Documentation.objects.create(
                hackathon_id=hackathon_id,
                title=_prefixed_title(FEED_PREFIX, title),
                doc_type='other',
                external_url=external_url,
                description=_feed_description(platform, published_date),
                is_published=action == 'publish',
                created_by=request.user,
                landing_sections=landing_sections,
            )
            messages.success(request, f'Feed "{title}" created.')
    except Exception as exc:
        messages.error(request, f'Unable to save feed: {exc}')

    return render_route(request, f'/features/media-comms/?focus=feeds&hackathon={hackathon_id}')


@login_required(login_url='/accounts/')
@require_POST
def delete_creative_asset(request, creative_id):
    denied = _feature_permission_required(request, 'social_media_creative_mgt', 'media_sponsorship_mgt')
    if denied:
        return denied

    creative = get_object_or_404(CreativeMaterial, id=creative_id)
    focus = request.POST.get('focus', 'creative-elements').strip() or 'creative-elements'
    hackathon_id = creative.hackathon_id
    title = _normalize_testimonial_title(creative.title)
    creative.delete()
    messages.success(request, f'Item "{title}" deleted.')
    testimonial_kind = request.POST.get('testimonial_kind', '').strip().lower()
    suffix = f'&testimonial_kind={testimonial_kind}' if focus == 'testimonials' and testimonial_kind in TESTIMONIAL_PREFIX_MAP else ''
    return redirect(f'/features/media-comms/?focus={focus}&hackathon={hackathon_id}{suffix}')


@login_required(login_url='/accounts/')
@require_POST
def save_faq_item(request):
    denied = _feature_permission_required(request, 'social_media_creative_mgt', 'media_sponsorship_mgt', 'announcement_communication_sys')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    question = request.POST.get('question', '').strip()
    answer = request.POST.get('answer', '').strip()
    display_order = request.POST.get('display_order', '0').strip()
    item_id = request.POST.get('item_id', '').strip()
    action = request.POST.get('action', 'publish')

    try:
        display_order = int(display_order)
    except (TypeError, ValueError):
        display_order = 0

    if not hackathon_id or not question or not answer:
        messages.error(request, 'Question and Answer are required.')
        return redirect(f'/features/media-comms/?focus=faq&hackathon={hackathon_id}')

    try:
        if item_id:
            faq = FAQItem.objects.get(id=item_id)
            faq.hackathon_id = hackathon_id
            faq.question = question
            faq.answer = answer
            faq.display_order = display_order
            faq.is_published = action == 'publish'
            faq.save()
            messages.success(request, f'FAQ updated.')
        else:
            FAQItem.objects.create(
                hackathon_id=hackathon_id,
                question=question,
                answer=answer,
                display_order=display_order,
                is_published=action == 'publish',
                created_by=request.user,
            )
            messages.success(request, f'FAQ created.')
    except Exception as exc:
        messages.error(request, f'Unable to save FAQ: {exc}')

    return redirect(f'/features/media-comms/?focus=faq&hackathon={hackathon_id}')


@login_required(login_url='/accounts/')
@require_POST
def toggle_faq_status(request, faq_id):
    denied = _feature_permission_required(request, 'social_media_creative_mgt', 'media_sponsorship_mgt', 'announcement_communication_sys')
    if denied:
        return denied

    faq = get_object_or_404(FAQItem, id=faq_id)
    hackathon_id = faq.hackathon_id
    faq.is_suspended = not faq.is_suspended
    faq.save()
    status_label = 'suspended' if faq.is_suspended else 'activated'
    messages.success(request, f'FAQ {status_label}.')
    return redirect(f'/features/media-comms/?focus=faq&hackathon={hackathon_id}')


@login_required(login_url='/accounts/')
@require_POST
def delete_faq_item(request, faq_id):
    denied = _feature_permission_required(request, 'social_media_creative_mgt', 'media_sponsorship_mgt', 'announcement_communication_sys')
    if denied:
        return denied

    faq = get_object_or_404(FAQItem, id=faq_id)
    hackathon_id = faq.hackathon_id
    faq.delete()
    messages.success(request, f'FAQ deleted.')
    return redirect(f'/features/media-comms/?focus=faq&hackathon={hackathon_id}')


def _notify_team_not_qualified(team, round_number):
    try:
        from team.team.models import TeamNotification
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        
        # Create in-app notification
        TeamNotification.objects.create(
            team_leader=team.team_leader,
            notif_type='system',
            title=f"Not Qualified for Round {round_number + 1}",
            body=f"We regret to inform you that your team '{team.team_name}' did not meet the required cutoff scores in Round {round_number} and has not qualified for the next round.",
        )
        
        # Send email notification
        subject = f"Evaluation Outcome - Round {round_number} - {team.hackathon.name}"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;
                    padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
            <h2 style="color:#dc2626;">Evaluation Outcome</h2>
            <p>Hello <strong>{team.team_leader.get_full_name() or team.team_leader.username}</strong>,</p>
            <p>Thank you for your participation in the <strong>{team.hackathon.name}</strong>.</p>
            <p>After compiling the evaluator marks for <strong>Round {round_number}</strong>, your team <strong>{team.team_name}</strong> did not meet the cutoff thresholds required to qualify for the next round.</p>
            <p>As a result, your team dashboard has been suspended. We wish you the best of luck in your future endeavors!</p>
        </div>"""
        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"Hello, we regret to inform you that your team '{team.team_name}' did not qualify for the next round of {team.hackathon.name}.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[team.team_leader.email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to notify unqualified team {team.id}: {exc}", exc_info=True)


@login_required(login_url='/accounts/')
@never_cache
def results_reporting_management(request):
    denied = _feature_permission_required(request, 'reporting_result_mgt', 'awards_certification_mgt')
    if denied:
        return denied

    hackathons, hackathon_filter, active_hackathon = _resolve_hackathon_scope(request)
    
    from decimal import Decimal
    from jury.models import TeamEvaluation
    from events.models import RoundMarkingParameter
    from features.models import Team, TeamStatusLog

    selected_round = 1
    if active_hackathon:
        active_round_data = active_hackathon.active_round
        if active_round_data:
            selected_round = active_round_data['number']
    
    round_param = request.GET.get('round')
    if round_param:
        try:
            selected_round = int(round_param)
        except ValueError:
            pass

    teams = Team.objects.none()
    params = RoundMarkingParameter.objects.none()
    teams_data = []
    show_qualified = request.GET.get('show_qualified') == 'true'
    show_top_10 = request.GET.get('top_10') == 'true'

    if active_hackathon:
        # Get marking parameters for this hackathon and round
        params = RoundMarkingParameter.objects.filter(
            hackathon=active_hackathon,
            round_number=selected_round
        ).order_by('id')
        
        # Get all teams in this hackathon and selected round
        teams = Team.objects.filter(
            hackathon=active_hackathon,
            current_round=selected_round
        ).select_related('institution', 'team_leader', 'problem_statement').order_by('-updated_at')

        # Handle POST actions (Save Cutoffs / Promote Teams)
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'save_cutoffs':
                for param in params:
                    cutoff_val_raw = request.POST.get(f'cutoff_{param.id}', '').strip()
                    if cutoff_val_raw:
                        try:
                            cutoff_val = Decimal(cutoff_val_raw)
                            if Decimal('0') <= cutoff_val <= Decimal('100'):
                                param.cutoff_score = cutoff_val
                                param.save(update_fields=['cutoff_score'])
                            else:
                                messages.error(request, f"Cutoff for {param.name} must be between 0 and 100.")
                        except (ValueError, Exception):
                            messages.error(request, f"Invalid cutoff score for {param.name}.")

                # Calculate qualified count under updated cutoffs
                qualified_count = 0
                for t in teams:
                    t_evals = TeamEvaluation.objects.filter(team=t, round_number=selected_round)
                    evaluators_count = t_evals.values('evaluator').distinct().count()
                    
                    is_q = evaluators_count > 0
                    for param in params:
                        scores = [ev.score for ev in t_evals if ev.parameter_id == param.id]
                        avg = sum(scores, Decimal('0')) / len(scores) if scores else Decimal('0')
                        if avg < param.cutoff_score:
                            is_q = False
                            break
                    if is_q:
                        qualified_count += 1

                messages.success(request, f"Cutoff thresholds saved successfully. Currently, {qualified_count} teams are qualified.")
                redirect_url = f"{request.path}?hackathon={hackathon_filter}&round={selected_round}"
                if show_qualified:
                    redirect_url += "&show_qualified=true"
                if show_top_10:
                    redirect_url += "&top_10=true"
                return redirect(redirect_url)

            elif action == 'promote_team':
                team_id = request.POST.get('team_id')
                team_to_promote = get_object_or_404(Team, id=team_id, hackathon=active_hackathon, current_round=selected_round)
                
                # Check if team is qualified (we must compute it)
                team_evals = TeamEvaluation.objects.filter(team=team_to_promote, round_number=selected_round)
                evaluators_count = team_evals.values('evaluator').distinct().count()
                
                is_qualified = evaluators_count > 0
                for param in params:
                    scores = [ev.score for ev in team_evals if ev.parameter_id == param.id]
                    avg = sum(scores, Decimal('0')) / len(scores) if scores else Decimal('0')
                    if avg < param.cutoff_score:
                        is_qualified = False
                        break
                
                if not is_qualified:
                    messages.error(request, f"Team '{team_to_promote.team_name}' is not qualified for promotion based on cutoff scores.")
                else:
                    old_round = team_to_promote.current_round
                    team_to_promote.current_round += 1
                    team_to_promote.save(update_fields=['current_round'])

                    TeamStatusLog.objects.create(
                        team=team_to_promote,
                        old_status=team_to_promote.status,
                        new_status=team_to_promote.status,
                        changed_by=request.user,
                        note=f"Promoted from Round {old_round} to Round {team_to_promote.current_round} after qualifying evaluation."
                    )

                    # Advance hackathon.current_jury_round if this team is now in a higher round
                    if team_to_promote.current_round > active_hackathon.current_jury_round:
                        active_hackathon.current_jury_round = team_to_promote.current_round
                        active_hackathon.save(update_fields=['current_jury_round'])

                    messages.success(request, f"Successfully promoted team '{team_to_promote.team_name}' to Round {team_to_promote.current_round}!")
                redirect_url = f"{request.path}?hackathon={hackathon_filter}&round={selected_round}"
                if show_qualified: redirect_url += "&show_qualified=true"
                if show_top_10: redirect_url += "&top_10=true"
                return redirect(redirect_url)

            elif action == 'promote_qualified':
                promoted_count = 0
                suspended_count = 0
                for team in teams:
                    team_evals = TeamEvaluation.objects.filter(team=team, round_number=selected_round)
                    evaluators_count = team_evals.values('evaluator').distinct().count()
                    
                    is_qualified = evaluators_count > 0
                    for param in params:
                        scores = [ev.score for ev in team_evals if ev.parameter_id == param.id]
                        avg = sum(scores, Decimal('0')) / len(scores) if scores else Decimal('0')
                        if avg < param.cutoff_score:
                            is_qualified = False
                            break
                    
                    if is_qualified:
                        old_round = team.current_round
                        team.current_round += 1
                        team.save(update_fields=['current_round'])
                        
                        TeamStatusLog.objects.create(
                            team=team,
                            old_status=team.status,
                            new_status=team.status,
                            changed_by=request.user,
                            note=f"Promoted from Round {old_round} to Round {team.current_round} via bulk promotion threshold."
                        )
                        promoted_count += 1
                    else:
                        # Suspend dashboard and notify team lead
                        old_status = team.status
                        team.status = 'disqualified'
                        team.save(update_fields=['status'])
                        
                        TeamStatusLog.objects.create(
                            team=team,
                            old_status=old_status,
                            new_status='disqualified',
                            changed_by=request.user,
                            note=f"Suspended: Did not meet cutoff score in Round {selected_round}."
                        )
                        _notify_team_not_qualified(team, selected_round)
                        suspended_count += 1
                
                if promoted_count > 0 or suspended_count > 0:
                    # Advance hackathon.current_jury_round if any teams moved to a higher round
                    if promoted_count > 0:
                        next_round = selected_round + 1
                        if next_round > active_hackathon.current_jury_round:
                            active_hackathon.current_jury_round = next_round
                            active_hackathon.save(update_fields=['current_jury_round'])

                    messages.success(
                        request,
                        f"Successfully promoted {promoted_count} qualified teams to Round {selected_round + 1}, "
                        f"and suspended {suspended_count} unqualified teams."
                    )
                else:
                    messages.warning(request, "No teams were found to promote or suspend.")
                redirect_url = f"{request.path}?hackathon={hackathon_filter}&round={selected_round}"
                if show_qualified: redirect_url += "&show_qualified=true"
                if show_top_10: redirect_url += "&top_10=true"
                return redirect(redirect_url)

        # Query all evaluations for these teams in the current round
        all_evals = TeamEvaluation.objects.filter(
            team__in=teams,
            round_number=selected_round
        ).select_related('evaluator', 'parameter')

        # Build detailed team data
        from features.models import TeamEvaluationAssignment
        qualified_teams_count = 0
        for team in teams:
            team_evals = [e for e in all_evals if e.team_id == team.id]
            
            # Find all assigned evaluators for this team & round
            assignment = TeamEvaluationAssignment.objects.filter(
                team=team, round_number=selected_round
            ).first()
            
            assigned_evaluators = []
            if assignment:
                if assignment.jury_1: assigned_evaluators.append(assignment.jury_1.user)
                if assignment.jury_2: assigned_evaluators.append(assignment.jury_2.user)
                if assignment.jury_3: assigned_evaluators.append(assignment.jury_3.user)
                if assignment.expert_1: assigned_evaluators.append(assignment.expert_1.user)
                if assignment.expert_2: assigned_evaluators.append(assignment.expert_2.user)
            
            # Group scores by evaluator user
            evaluations_by_evaluator = {}
            # Initialize for all assigned evaluators
            for evaluator in assigned_evaluators:
                evaluations_by_evaluator[evaluator.id] = {
                    'user': evaluator,
                    'scores': {},
                    'remarks': "",
                    'has_submitted': False
                }
            
            # Populate actual evaluations
            for ev in team_evals:
                evaluator_id = ev.evaluator_id
                if evaluator_id not in evaluations_by_evaluator:
                    evaluations_by_evaluator[evaluator_id] = {
                        'user': ev.evaluator,
                        'scores': {},
                        'remarks': ev.remarks or "",
                        'has_submitted': True
                    }
                evaluations_by_evaluator[evaluator_id]['scores'][ev.parameter_id] = ev.score
                evaluations_by_evaluator[evaluator_id]['remarks'] = ev.remarks or ""
                evaluations_by_evaluator[evaluator_id]['has_submitted'] = True
            
            # Calculate parameter averages
            parameter_averages = {}
            submitted_evals_count = sum(1 for e in evaluations_by_evaluator.values() if e['has_submitted'])
            is_qualified = submitted_evals_count > 0
            
            for param in params:
                param_scores = [ev.score for ev in team_evals if ev.parameter_id == param.id]
                avg = sum(param_scores, Decimal('0')) / len(param_scores) if param_scores else Decimal('0')
                parameter_averages[param.id] = avg
                
                if avg < param.cutoff_score:
                    is_qualified = False
            
            overall_score = sum(parameter_averages.values(), Decimal('0')) / len(params) if params else Decimal('0')
            
            if is_qualified:
                qualified_teams_count += 1

            item = {
                'team': team,
                'evaluations_by_evaluator': list(evaluations_by_evaluator.values()),
                'parameter_averages': parameter_averages,
                'is_qualified': is_qualified,
                'overall_score': overall_score,
                'evaluators_count': submitted_evals_count,
            }
            
            if not show_qualified or is_qualified:
                teams_data.append(item)

        # Apply Top 10 filter
        if show_top_10:
            teams_data.sort(key=lambda x: x['overall_score'], reverse=True)
            teams_data = teams_data[:10]

    is_round_promoted = False
    if active_hackathon:
        is_round_promoted = Team.objects.filter(
            hackathon=active_hackathon,
            current_round__gt=selected_round
        ).exists()
    is_round_completed = (active_hackathon.current_jury_round > selected_round) or is_round_promoted if active_hackathon else False

    total_rounds_range = range(1, (active_hackathon.number_of_rounds if active_hackathon else 5) + 1)

    context = _feature_context(
        request,
        tab='results_ops',
        hackathons=hackathons,
        hackathon_filter=hackathon_filter,
        active_hackathon=active_hackathon,
        selected_round=selected_round,
        total_rounds_range=total_rounds_range,
        params=params,
        teams_data=teams_data,
        show_qualified=show_qualified,
        show_top_10=show_top_10,
        qualified_teams_count=qualified_teams_count,
        total_teams_count=teams.count() if active_hackathon else 0,
        is_round_completed=is_round_completed,
    )
    return render(request, 'features/results_reporting.html', context)


@login_required(login_url='/accounts/')
@require_POST
def reset_evaluation_data(request):
    """
    Resets all team evaluations, promotions, panel creations, and locks
    for the active hackathon back to Round 1 status.
    """
    denied = _feature_permission_required(request, 'reporting_result_mgt', 'evaluation_coordination')
    if denied:
        return denied

    hackathon_id = request.POST.get('hackathon_id')
    if not hackathon_id:
        messages.error(request, "Hackathon ID is required.")
        return redirect('/features/results-reporting/')

    from events.models import Hackathon, JuryTeam, RoundJuryConfig
    from features.models import Team, TeamEvaluationAssignment, TeamStatusLog
    from jury.models import TeamEvaluation

    hackathon = get_object_or_404(Hackathon, id=hackathon_id)

    # 1. Delete all panel configurations (JuryTeam) for this hackathon
    deleted_panels, _ = JuryTeam.objects.filter(hackathon=hackathon).delete()

    # 2. Delete all RoundJuryConfig (lock states, etc.)
    deleted_configs, _ = RoundJuryConfig.objects.filter(hackathon=hackathon).delete()

    # 3. Delete all TeamEvaluationAssignment (auto-assignments)
    teams = Team.objects.filter(hackathon=hackathon)
    deleted_assignments, _ = TeamEvaluationAssignment.objects.filter(team__in=teams).delete()

    # 4. Delete all evaluations (TeamEvaluation)
    deleted_evals, _ = TeamEvaluation.objects.filter(team__in=teams).delete()

    # 5. Reset teams to Round 1 and 'submitted' status
    updated_teams_count = 0
    for team in teams:
        if team.current_round > 1 or team.status in ['evaluated', 'disqualified']:
            team.current_round = 1
            team.status = 'submitted'
            team.save(update_fields=['current_round', 'status'])
            updated_teams_count += 1

            # Log status change
            TeamStatusLog.objects.create(
                team=team,
                old_status=team.status,
                new_status='submitted',
                changed_by=request.user,
                note="Reset: Reset back to Round 1 evaluation state by admin."
            )

    # 6. Reset hackathon current_jury_round to 1
    hackathon.current_jury_round = 1
    hackathon.save(update_fields=['current_jury_round'])

    messages.success(
        request,
        f"Reset complete! Deleted {deleted_panels} panels, {deleted_evals} evaluations, "
        f"and reset {updated_teams_count} teams back to Round 1."
    )
    return redirect(f'/features/results-reporting/?hackathon={hackathon.id}')


# ══════════════════════════════════════════════════════════════
#  MENTOR INVITATION ADMIN MANAGEMENT
# ══════════════════════════════════════════════════════════════

@login_required(login_url='/accounts/')
@never_cache
def mentor_invitations_admin(request):
    """Admin view: list all mentor invitations awaiting admin approval."""
    if not _superadmin_required(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')

    from mentor.mentor.models import MentorInvitation
    sub = request.GET.get('sub', 'pending')
    if sub == 'pending':
        invites = MentorInvitation.objects.filter(status='spoc_approved').order_by('-invited_at')
    else:
        invites = MentorInvitation.objects.exclude(status__in=['invited', 'accepted', 'spoc_approved']).order_by('-invited_at')

    context = {'invites': invites, 'sub': sub, 'tab': 'mentor_admin'}
    return render(request, 'features/mentor_admin.html', context)


@login_required(login_url='/accounts/')
@require_POST
def mentor_admin_approve(request, invite_id):
    if not _superadmin_required(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')

    from mentor.mentor.models import MentorInvitation
    from mentor.mentor.signals import provision_mentor_account
    from django.utils import timezone
    invite = get_object_or_404(MentorInvitation, id=invite_id)
    invite.status = 'admin_approved'
    invite.admin_decided_at = timezone.now()
    invite.admin_note = request.POST.get('note', '')
    invite.save(update_fields=['status', 'admin_decided_at', 'admin_note'])
    provision_mentor_account(invite, resend_email=True)
    messages.success(request, f"Mentor '{invite.mentor_name}' approved. Account credentials sent.")
    return render_route(request, '/features/mentors/?sub=pending')


@login_required(login_url='/accounts/')
@require_POST
def mentor_admin_reject(request, invite_id):
    if not _superadmin_required(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')

    from mentor.mentor.models import MentorInvitation
    from django.utils import timezone
    invite = get_object_or_404(MentorInvitation, id=invite_id)
    invite.status = 'admin_rejected'
    invite.admin_decided_at = timezone.now()
    invite.admin_note = request.POST.get('rejection_reason', '')
    invite.save()
    messages.success(request, f"Mentor '{invite.mentor_name}' rejected.")
    return render_route(request, '/features/mentors/?sub=pending')
