"""spoc/context_processors.py — injects sidebar badge counts for all SPOC views."""


def spoc_context(request):
    ctx = {
        'pending_teams_count': 0,
        'pending_mods_count': 0,
        'unread_msg_count': 0,
        'recent_activities': [],
    }
    if not request.user.is_authenticated:
        return ctx
    if not hasattr(request.user, 'spoc_profile'):
        return ctx

    spoc = request.user.spoc_profile

    try:
        from accounts.models import SpocInstitutionMap
        from features.models import TeamRegistration
        from .models import SpocModificationDecision, SpocMessage, SpocDashboardActivity

        inst_map = SpocInstitutionMap.objects.filter(spoc=spoc).first()
        if inst_map:
            ctx['pending_teams_count'] = TeamRegistration.objects.filter(
                institution=inst_map.institution, status='pending'
            ).count()

        ctx['pending_mods_count'] = SpocModificationDecision.objects.filter(
            spoc=spoc, status='pending'
        ).count()

        ctx['unread_msg_count'] = SpocMessage.objects.filter(
            recipient=request.user, is_read=False
        ).count()

        from .models import SpocNotification
        ctx['unread_notifications_count'] = SpocNotification.objects.filter(
            spoc=spoc, is_read=False
        ).count()

        ctx['recent_activities'] = SpocDashboardActivity.objects.filter(spoc=spoc)[:5]

    except Exception:
        pass

    return ctx
