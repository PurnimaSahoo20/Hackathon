from django.contrib import admin

from .models import (
    TeamMemberInvite,
    TeamNotification,
    TeamSolution,
    TeamSupportMessage,
    TeamTravelDetail,
)

admin.site.register(TeamMemberInvite)
admin.site.register(TeamNotification)
admin.site.register(TeamSolution)
admin.site.register(TeamTravelDetail)
admin.site.register(TeamSupportMessage)
