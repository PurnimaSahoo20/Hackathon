from django.urls import NoReverseMatch, reverse


ACTIVE_NAV_LABELS = {
    "dashboard": "Dashboard",
    "details": "Team Members",
    "mentor": "Mentor",
    "communication": "Communication",
    "submission": "Submit Solution",
    "travel": "Travel Details",
    "content": "Problem Statement",
    "announcements": "Announcements",
    "results": "Results",
    "memories": "Memories",
    "media": "Podcast and Media",
    "notifications": "Notifications",
    "profile": "Profile",
    "messages": "Messages",
    "teams": "Team Registrations",
    "modifications": "Modification Requests",
    "activity": "Activity Log",
    "mentors": "Mentor Verifications",
}

SUB_LABELS = {
    "live_teams": "Live Teams",
    "pending_approvals": "Pending Approvals",
    "all_hackathons": "All Hackathons",
    "team_detail": "Team Detail",
    "reg_detail": "Registration Detail",
    "spocs": "SPOCs",
    "institutions": "Institutions",
    "invitations": "Invitations",
    "podcasts": "Podcasts",
    "media": "Media Elements",
    "venues": "Venues",
    "rooms": "Rooms",
    "facilities": "Facilities",
    "budget": "Budget",
    "expenses": "Expenses",
    "sponsors": "Sponsors",
    "pending": "Pending",
    "active": "Active",
    "completed": "Completed",
    "results": "Results",
}


TAB_LABELS = {
    "overview": "Overview",
    "events": "Events",
    "problem_statements": "Problem Statements",
    "creatives": "Creative Elements",
    "admin_mgt": "Admin Management",
    "exec_mgt": "Executive Management",
    "user_mgt": "Other Users",
    "profile": "My Profile",
}


TAB_SECTION_LABELS = {
    "overview": "Overview",
    "events": "Overview",
    "problem_statements": "Overview",
    "creatives": "Overview",
    "admin_mgt": "User Management",
    "exec_mgt": "User Management",
    "user_mgt": "User Management",
    "profile": "Settings",
}


ACTIVE_NAV_SECTION_LABELS = {
    "dashboard": "My Team",
    "details": "My Team",
    "mentor": "My Team",
    "communication": "My Team",
    "submission": "My Team",
    "travel": "My Team",
    "content": "Info",
    "announcements": "Info",
    "results": "Info",
    "memories": "Info",
    "media": "Info",
    "notifications": "Account",
    "profile": "Account",
    "messages": "Communication",
    "teams": "Management",
    "modifications": "Management",
    "activity": "Communication",
    "mentors": "Management",
}


URL_NAME_LABELS = {
    "team_dashboard": "Dashboard",
    "team_details": "Team Members",
    "team_invite_mentor": "Mentor",
    "team_communication": "Communication",
    "team_submission": "Submit Solution",
    "team_travel": "Travel Details",
    "team_content": "Problem Statement",
    "team_announcements": "Announcements",
    "team_results": "Results",
    "team_memories": "Memories",
    "team_media": "Podcast and Media",
    "team_notifications": "Notifications",
    "team_profile": "Profile",
    "team_register": "Register Team",
    "mentor_dashboard": "Dashboard",
    "mentor_team_detail": "Team Details",
    "mentor_team_problem_statement": "Problem Statement",
    "mentor_team_resources": "Podcast & Documentary",
    "mentor_messages": "Messages",
    "mentor_profile": "Profile",
    "spoc_dashboard": "Dashboard",
    "spoc_teams": "Team Registrations",
    "spoc_modifications": "Modification Requests",
    "spoc_results": "Results",
    "spoc_mentor_invitations": "Mentor Verifications",
    "spoc_messages": "Messages",
    "spoc_announcements": "Announcements",
    "spoc_activity_log": "Activity Log",
    "spoc_profile": "Profile & Settings",
    "admin_dashboard": "Admin Dashboard",
    "executive_dashboard": "Executive Dashboard",
    "executive_profile": "My Profile",
    "executive_user_status": "User Status",
    "executive_inbox": "Inbox",
    "executive_message_detail": "Message Detail",
    "superadmin_dashboard": "Overview",
    "spoc_college_management": "SPOC & College Mgt",
    "team_event_monitoring": "Team & Event Monitor",
    "content_management": "Problem Statement & Content Management",
    "venue_logistics_management": "Venue & Logistics Management",
    "finance_management": "Financial Management",
    "jury_management": "Jury & Evaluation",
    "support_operations_management": "Support & Stay Ops",
    "media_communications_management": "Media & Communications",
    "results_reporting_management": "Results & Awards",
    "superadmin_profile": "My Profile",
    "view_hackathon": "View Event",
    "edit_hackathon": "Edit Event",
    "edit_problem_statement": "Edit Problem Statement",
}


URL_NAME_SECTION_LABELS = {
    "team_dashboard": "My Team",
    "team_details": "My Team",
    "team_invite_mentor": "My Team",
    "team_communication": "My Team",
    "team_submission": "My Team",
    "team_travel": "My Team",
    "team_content": "Info",
    "team_announcements": "Info",
    "team_results": "Info",
    "team_memories": "Info",
    "team_media": "Info",
    "team_notifications": "Account",
    "team_profile": "Account",
    "mentor_dashboard": "Portal",
    "mentor_team_detail": "Portal",
    "mentor_team_problem_statement": "Portal",
    "mentor_team_resources": "Portal",
    "mentor_messages": "Portal",
    "mentor_profile": "Portal",
    "spoc_dashboard": "Management",
    "spoc_teams": "Management",
    "spoc_modifications": "Management",
    "spoc_results": "Management",
    "spoc_mentor_invitations": "Management",
    "spoc_messages": "Communication",
    "spoc_announcements": "Communication",
    "spoc_activity_log": "Communication",
    "spoc_profile": "Account",
    "admin_dashboard": "Workspace",
    "executive_dashboard": "Workspace",
    "executive_profile": "Account",
    "executive_user_status": "Workspace",
    "executive_inbox": "Communication",
    "executive_message_detail": "Communication",
    "superadmin_dashboard": "Overview",
    "spoc_college_management": "Features",
    "team_event_monitoring": "Features",
    "content_management": "Features",
    "venue_logistics_management": "Features",
    "finance_management": "Features",
    "jury_management": "Features",
    "support_operations_management": "Features",
    "media_communications_management": "Features",
    "results_reporting_management": "Features",
    "superadmin_profile": "Settings",
    "view_hackathon": "Events",
    "edit_hackathon": "Events",
    "edit_problem_statement": "Problem Statements",
}


BREADCRUMB_DESCRIPTIONS = {
    "Overview": "High-level platform analytics and current event visibility.",
    "Events": "Create, publish, and manage hackathon event timelines.",
    "Problem Statements": "Review and maintain challenge briefs and domains.",
    "Creative Elements": "Organize media assets, visuals, and brand files.",
    "User Management": "Control access, roles, and user onboarding workflows.",
    "Features": "Access operational tools and cross-team management modules.",
    "Management": "Track approvals, registrations, and operational updates.",
    "My Team": "Navigate core team actions, members, and submissions.",
    "Info": "Browse event information, updates, results, and memories.",
    "Communication": "Stay on top of messages, announcements, and activity.",
    "Account": "Manage profile settings, alerts, and personal preferences.",
    "Settings": "Update account preferences and configuration.",
    "Workspace": "Administrative control center for the platform.",
    "Portal": "Mentor workspace for guidance, updates, and collaboration.",
}


def _safe_reverse(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return ""


def _role_name(user):
    role = getattr(getattr(user, "role", None), "name", "")
    return role or ""


def _portal_for_context(request):
    path = (getattr(request, "path", "") or "").lower()
    user = getattr(request, "user", None)
    role = _role_name(user).lower()

    if path.startswith("/team/"):
        return {"label": "Team Portal", "url": _safe_reverse("team_dashboard")}
    if path.startswith("/mentor/"):
        return {"label": "Mentor Portal", "url": _safe_reverse("mentor_dashboard")}
    if path.startswith("/spoc/"):
        return {"label": "SPOC Portal", "url": _safe_reverse("spoc_dashboard")}
    if path.startswith("/accounts/executive-") or path.startswith("/accounts/executive/"):
        return {"label": "Executive Portal", "url": _safe_reverse("executive_dashboard")}
    if getattr(user, "is_superuser", False) or role == "super admin":
        return {"label": "Super Admin", "url": _safe_reverse("superadmin_dashboard")}
    if role == "executive":
        return {"label": "Executive Portal", "url": _safe_reverse("executive_dashboard")}
    return {"label": "Admin Portal", "url": _safe_reverse("admin_dashboard")}


def _resolve_current_label(request):
    tab = request.GET.get("tab", "")
    active_nav = request.GET.get("active_nav", "")

    if tab:
        return TAB_LABELS.get(tab, tab.replace("_", " ").title())
    if active_nav:
        return ACTIVE_NAV_LABELS.get(active_nav, active_nav.replace("_", " ").title())

    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "") if resolver_match else ""
    if url_name:
        return URL_NAME_LABELS.get(url_name, url_name.replace("_", " ").title())

    return "Page"


def _resolve_section_label(request):
    tab = request.GET.get("tab", "")
    active_nav = request.GET.get("active_nav", "")

    if tab:
        return TAB_SECTION_LABELS.get(tab, "Section")
    if active_nav:
        return ACTIVE_NAV_SECTION_LABELS.get(active_nav, "Section")

    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "") if resolver_match else ""
    if url_name:
        return URL_NAME_SECTION_LABELS.get(url_name, "Section")

    return "Section"


def _build_breadcrumbs(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return []

    portal = _portal_for_context(request)
    current_label = _resolve_current_label(request)
    section_label = _resolve_section_label(request)
    breadcrumbs = [portal]

    # Try to build a reasonable URL for current label
    current_url = request.path
    if request.GET.get("tab"):
        current_url += f"?tab={request.GET.get('tab')}"
    elif request.GET.get("active_nav"):
        current_url += f"?active_nav={request.GET.get('active_nav')}"

    if section_label and section_label != portal["label"]:
        breadcrumbs.append({"label": section_label, "url": portal["url"]})
    if current_label and current_label != section_label and current_label != portal["label"]:
        breadcrumbs.append({"label": current_label, "url": current_url})

    sub = request.GET.get("sub", "")
    if sub:
        sub_label = SUB_LABELS.get(sub, sub.replace("_", " ").title())
        if sub_label != current_label:
            breadcrumbs.append({"label": sub_label, "url": request.get_full_path()})

    return breadcrumbs


def _build_breadcrumb_context(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    portal = _portal_for_context(request)
    section_label = _resolve_section_label(request)
    current_label = _resolve_current_label(request)

    return {
        "portal_label": portal["label"],
        "section_label": section_label,
        "current_label": current_label,
        "description": BREADCRUMB_DESCRIPTIONS.get(section_label, "Navigate the current workspace and active page."),
    }


def admin_permissions(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'permissions': [], 'is_super_admin_user': False, 'breadcrumbs': [], 'breadcrumb_context': {}}

    is_super_admin_user = bool(
        request.user.is_superuser or
        (getattr(request.user, 'role', None) and request.user.role.name == 'Super Admin')
    )

    if is_super_admin_user:
        permission_codes = []
    elif hasattr(request.user, 'admin_profile'):
        permission_codes = list(
            request.user.admin_profile.permissions.values_list('codename', flat=True)
        )
    elif hasattr(request.user, 'executive_profile') and request.user.executive_profile.assigned_admin_id:
        permission_codes = list(
            request.user.executive_profile.assigned_admin.permissions.values_list('codename', flat=True)
        )
    else:
        permission_codes = []

    return {
        'permissions': permission_codes,
        'is_super_admin_user': is_super_admin_user,
        'breadcrumbs': _build_breadcrumbs(request),
        'breadcrumb_context': _build_breadcrumb_context(request),
    }
