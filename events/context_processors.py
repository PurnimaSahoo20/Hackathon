from .models import Hackathon


def active_event(request):
    active_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    return {
        'global_active_hackathon': active_hackathon,
        'global_active_round': active_hackathon.active_round if active_hackathon else None,
    }
