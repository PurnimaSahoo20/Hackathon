"""spoc/signals.py — push notifications to SPOC when teams register/modify."""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='features.TeamRegistration')
def notify_spoc_on_team_registration(sender, instance, created, **kwargs):
    """When a new team registration is created, notify the relevant SPOC."""
    if not created:
        return
    try:
        from accounts.models import SpocProfile, SpocInstitutionMap
        from .models import SpocNotification
        # Find SPOC linked to this institution
        if instance.institution:
            maps = SpocInstitutionMap.objects.filter(
                institution=instance.institution
            ).select_related('spoc')
            for m in maps:
                SpocNotification.objects.create(
                    spoc=m.spoc,
                    notif_type='team_reg',
                    title=f"New Team Registration: {instance.team_name}",
                    body=f"{instance.team_name} has registered for {instance.hackathon.name}. Review pending.",
                    link=f"/spoc/teams/",
                )
    except Exception as exc:
        logger.error(f"SPOC notification error: {exc}", exc_info=True)
