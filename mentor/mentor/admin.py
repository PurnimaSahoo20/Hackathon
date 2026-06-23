from django.contrib import admin
from .models import MentorInvitation, MentorNotification, MentorMessage
admin.site.register(MentorInvitation)
admin.site.register(MentorNotification)
admin.site.register(MentorMessage)
