"""team/signals.py — notify team lead when mentor accepts, SPOC/admin approves."""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

@receiver(post_save, sender='mentor.MentorInvitation')
def notify_team_on_mentor_accept(sender, instance, created, **kwargs):
    if created or instance.status not in ('accepted', 'admin_approved'):
        return
    try:
        from .models import TeamNotification
        title = 'Mentor Accepted' if instance.status == 'accepted' else 'Mentor Approved by Admin'
        body  = (f"{instance.mentor_name} has accepted your mentor invitation. "
                 f"Pending SPOC verification." if instance.status == 'accepted'
                 else f"{instance.mentor_name} has been approved as your mentor!")
        TeamNotification.objects.get_or_create(
            team_leader=instance.team_leader,
            notif_type='mentor_accepted',
            title=title,
            defaults={'registration': instance.registration, 'body': body},
        )
    except Exception as exc:
        logger.error(f"Team notify mentor accept: {exc}")

@receiver(post_save, sender='features.TeamRegistration')
def notify_team_on_status_change(sender, instance, created, **kwargs):
    if created:
        return
    try:
        from .models import TeamNotification
        if instance.status == 'approved':
            TeamNotification.objects.create(
                team_leader=instance.team_leader,
                registration=instance,
                notif_type='spoc_approved',
                title='🎉 Your Team is Approved!',
                body=f"Your team '{instance.team_name}' has been approved by the SPOC. Your full dashboard is now active!",
            )
        elif instance.status == 'rejected':
            TeamNotification.objects.create(
                team_leader=instance.team_leader,
                registration=instance,
                notif_type='spoc_rejected',
                title='Team Registration Not Approved',
                body=f"Your team '{instance.team_name}' was not approved. Reason: {instance.rejection_note or 'See dashboard for details.'}",
            )
    except Exception as exc:
        logger.error(f"Team notify status change: {exc}")
