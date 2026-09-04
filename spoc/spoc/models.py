"""
spoc/models.py

Models specific to the SPOC portal:
  - SpocDashboardActivity
  - SpocTeamApproval
  - SpocModificationDecision
  - SpocMessage
  - SpocNotification

All heavy data lives in accounts/features apps — these are lightweight portal models.
"""
from django.db import models


class SpocDashboardActivity(models.Model):
    """Activity log entries visible on the SPOC dashboard."""
    spoc = models.ForeignKey(
        'accounts.SpocProfile', on_delete=models.CASCADE,
        related_name='dashboard_activities'
    )
    icon = models.CharField(max_length=10, default='📋')
    color = models.CharField(max_length=30, default='#2563eb')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Activity for {self.spoc} at {self.created_at}"


class SpocTeamApproval(models.Model):
    """Tracks SPOC-level decisions on team registrations."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    spoc = models.ForeignKey(
        'accounts.SpocProfile', on_delete=models.CASCADE,
        related_name='team_approvals'
    )
    registration = models.ForeignKey(
        'features.TeamRegistration', on_delete=models.CASCADE,
        related_name='spoc_approvals'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    auth_letter = models.FileField(upload_to='spoc/auth_letters/', max_length=255, null=True, blank=True)
    final_auth_letter = models.FileField(upload_to='spoc/final_auth_letters/', max_length=255, null=True, blank=True)
    final_submitted_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('spoc', 'registration')
        ordering = ['-created_at']

    def __str__(self):
        return f"SPOC approval for {self.registration} [{self.status}]"


class SpocModificationDecision(models.Model):
    """SPOC decision on a team modification request."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    spoc = models.ForeignKey(
        'accounts.SpocProfile', on_delete=models.CASCADE,
        related_name='mod_decisions'
    )
    # team stored as string FK to avoid tight coupling
    team_name = models.CharField(max_length=255)
    requested_change = models.CharField(max_length=500)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    auth_letter = models.FileField(upload_to='spoc/mod_letters/', max_length=255, null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"Mod decision: {self.team_name} [{self.status}]"


class SpocMessage(models.Model):
    """Direct messages between SPOC and team leads/members."""
    sender = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='spoc_sent_messages'
    )
    recipient = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='spoc_received_messages'
    )
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f"{self.sender} → {self.recipient}: {self.body[:40]}"


class SpocNotification(models.Model):
    """In-app notifications for SPOC users."""
    NOTIF_TYPES = [
        ('team_reg', 'New Team Registration'),
        ('mod_req', 'Modification Request'),
        ('admin_msg', 'Admin Message'),
        ('system', 'System'),
    ]
    spoc = models.ForeignKey(
        'accounts.SpocProfile', on_delete=models.CASCADE,
        related_name='notifications'
    )
    notif_type = models.CharField(max_length=30, choices=NOTIF_TYPES, default='system')
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notif({self.notif_type}) for {self.spoc}: {self.title}"





class Kishan(models.Model):
    name = models.CharField(max_length=123)
    age = models.IntegerField()
    bio_data = models.TextField()


    def __str__(self):
        return self.name



   