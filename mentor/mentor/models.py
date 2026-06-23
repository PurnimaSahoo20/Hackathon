"""
mentor/models.py

Models for the Mentor portal:
  - MentorInvitation  (team lead sends invite → mentor fills form → SPOC verifies → Admin approves)
  - MentorNotification
  - MentorMessage
"""
from django.db import models


class MentorInvitation(models.Model):
    STATUS_CHOICES = [
        ('invited',          'Invited'),
        ('accepted',         'Accepted by Mentor'),
        ('spoc_pending',     'Pending SPOC Verification'),
        ('spoc_approved',    'SPOC Approved'),
        ('spoc_rejected',    'SPOC Rejected'),
        ('admin_approved',   'Admin Approved'),
        ('admin_rejected',   'Admin Rejected'),
        ('active',           'Active'),
    ]

    # Who sent the invite
    team_leader = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='mentor_invitations_sent'
    )
    registration = models.ForeignKey(
        'features.TeamRegistration', on_delete=models.CASCADE,
        null=True, blank=True, related_name='mentor_invitations'
    )
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, null=True, blank=True
    )

    # Mentor info (filled before account creation)
    mentor_name  = models.CharField(max_length=255)
    mentor_email = models.EmailField()

    # Token for the mentor's accept link
    token = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='invited')

    # Mentor fills these when accepting
    mentor_designation = models.CharField(max_length=255, blank=True)
    mentor_institution  = models.CharField(max_length=255, blank=True)
    mentor_phone        = models.CharField(max_length=20, blank=True)
    mentor_expertise    = models.CharField(max_length=255, blank=True)
    id_proof            = models.FileField(upload_to='mentor_id_proofs/', null=True, blank=True)

    # Timestamps
    invited_at   = models.DateTimeField(auto_now_add=True)
    accepted_at  = models.DateTimeField(null=True, blank=True)
    spoc_decided_at  = models.DateTimeField(null=True, blank=True)
    admin_decided_at = models.DateTimeField(null=True, blank=True)

    # SPOC / Admin notes
    spoc_note  = models.TextField(blank=True)
    admin_note = models.TextField(blank=True)

    # After admin approval a User is created
    created_user = models.OneToOneField(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='from_mentor_invitation'
    )

    class Meta:
        ordering = ['-invited_at']

    def __str__(self):
        return f"MentorInvite → {self.mentor_email} [{self.status}]"


class MentorNotification(models.Model):
    NOTIF_TYPES = [
        ('invite',       'Invitation Received'),
        ('spoc_update',  'SPOC Update'),
        ('admin_update', 'Admin Update'),
        ('team_msg',     'Team Message'),
        ('system',       'System'),
    ]
    mentor = models.ForeignKey(
        'accounts.MentorProfile', on_delete=models.CASCADE,
        related_name='mentor_notifications'
    )
    notif_type = models.CharField(max_length=30, choices=NOTIF_TYPES, default='system')
    title  = models.CharField(max_length=255)
    body   = models.TextField(blank=True)
    link   = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"MentorNotif({self.notif_type}): {self.title}"


class MentorMessage(models.Model):
    sender    = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='mentor_sent')
    recipient = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='mentor_received')
    body      = models.TextField()
    is_read   = models.BooleanField(default=False)
    sent_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f"{self.sender} → {self.recipient}: {self.body[:40]}"
