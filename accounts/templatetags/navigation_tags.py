from django import template
from django.urls import NoReverseMatch, reverse


register = template.Library()


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
    if getattr(user, "is_superuser", False) or role == "super admin":
        return {"label": "Super Admin", "url": _safe_reverse("superadmin_dashboard")}
    return {"label": "Admin Portal", "url": _safe_reverse("admin_dashboard")}


def _resolve_current_label(request, active_nav="", tab=""):
    if tab:
        return TAB_LABELS.get(tab, tab.replace("_", " ").title())
    if active_nav:
        return ACTIVE_NAV_LABELS.get(active_nav, active_nav.replace("_", " ").title())

    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "") if resolver_match else ""
    if url_name:
        return URL_NAME_LABELS.get(url_name, url_name.replace("_", " ").title())

    return "Page"


@register.inclusion_tag("includes/breadcrumbs.html", takes_context=True)
def render_breadcrumbs(context):
    request = context.get("request")
    if not request:
        return {"breadcrumbs": []}

    active_nav = context.get("active_nav", "") or request.GET.get("active_nav", "")
    tab = context.get("tab", "") or request.GET.get("tab", "")

    portal = _portal_for_context(request)
    current_label = _resolve_current_label(request, active_nav=active_nav, tab=tab)
    breadcrumbs = [portal]

    if current_label != portal["label"]:
        breadcrumbs.append({"label": current_label, "url": ""})

    return {"breadcrumbs": breadcrumbs}
