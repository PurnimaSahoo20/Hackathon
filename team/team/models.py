"""
team/models.py

Models for the Team portal.
"""
from django.db import models


class TeamMemberInvite(models.Model):
    """Invite sent by team lead to add a new member."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    registration = models.ForeignKey(
        'features.TeamRegistration', on_delete=models.CASCADE,
        related_name='member_invites'
    )
    inviter = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='sent_member_invites'
    )
    email = models.EmailField()
    name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=100, default='Member')
    token = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-invited_at']

    def __str__(self):
        return f"MemberInvite -> {self.email} [{self.status}]"


class TeamNotification(models.Model):
    NOTIF_TYPES = [
        ('mentor_accepted', 'Mentor Accepted'),
        ('mentor_rejected', 'Mentor Rejected'),
        ('spoc_approved', 'SPOC Approved'),
        ('spoc_rejected', 'SPOC Rejected'),
        ('admin_approved', 'Admin Approved'),
        ('member_joined', 'Member Joined'),
        ('system', 'System'),
    ]

    team_leader = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='team_notifications'
    )
    registration = models.ForeignKey(
        'features.TeamRegistration', on_delete=models.CASCADE,
        null=True, blank=True, related_name='notifications'
    )
    notif_type = models.CharField(max_length=30, choices=NOTIF_TYPES, default='system')
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"TeamNotif({self.notif_type}): {self.title}"


class TeamSolution(models.Model):
    """Solution submission by the team."""
    DOC_TYPES = [
        ('ppt', 'Presentation'),
        ('report', 'Report / Document'),
        ('code', 'Code / Zip'),
        ('video', 'Demo Video URL'),
        ('other', 'Other'),
    ]

    registration = models.ForeignKey(
        'features.TeamRegistration', on_delete=models.CASCADE,
        related_name='solutions'
    )
    uploaded_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=255)
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES, default='other')
    file = models.FileField(upload_to='team_solutions/', null=True, blank=True)
    video_url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title} - {self.registration.team_name}"


class TeamTravelDetail(models.Model):
    """Travel details uploaded by the team for admin review."""
    TRAVEL_MODE_CHOICES = [
        ('train', 'Train'),
        ('bus', 'Bus'),
        ('flight', 'Flight'),
        ('car', 'Car'),
        ('other', 'Other'),
    ]

    registration = models.ForeignKey(
        'features.TeamRegistration', on_delete=models.CASCADE,
        related_name='travel_details'
    )
    submitted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    journey_date = models.DateField()
    travel_mode = models.CharField(max_length=20, choices=TRAVEL_MODE_CHOICES, default='train')
    traveler_name = models.CharField(max_length=255, blank=True)
    ticket_number = models.CharField(max_length=100, blank=True)
    ticket_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    ticket_file = models.FileField(upload_to='team_travel/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-journey_date', '-created_at']

    def __str__(self):
        return f"{self.registration.team_name}: {self.origin} -> {self.destination}"


class TeamSupportMessage(models.Model):
    """Support and communication messages raised by a team."""
    CATEGORY_CHOICES = [
        ('venue', 'Venue Admin'),
        ('health', 'Health Admin'),
        ('grievance', 'Grievance Admin'),
        ('logistics', 'Logistics Admin'),
        ('spoc', 'SPOC'),
        ('mentor', 'Mentor'),
        ('general', 'General Support'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('reviewed', 'Reviewed'),
        ('resolved', 'Resolved'),
    ]

    registration = models.ForeignKey(
        'features.TeamRegistration', on_delete=models.CASCADE,
        related_name='support_messages'
    )
    sender = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='team_support_messages'
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general')
    subject = models.CharField(max_length=255)
    message = models.TextField()
    attachment = models.FileField(upload_to='team_support/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    admin_reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.registration.team_name} [{self.category}] {self.subject}"
