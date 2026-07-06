"""
accounts/models.py

Contains ONLY:
  - Role, AdminPermission
  - User (custom AbstractUser)
  - SuperadminProfile, AdminProfile, SpocProfile, MentorProfile,
    JuryProfile, ExecutiveProfile, TeamleadProfile
  - OTPVerification
  - AuditLog
  - SpocInvitation, Institution, InstitutionExtended, SpocInstitutionMap

Models moved to other apps:
  - events:   Hackathon, ProblemStatement, CreativeMaterial
  - features: Team, Venue, TeamMember, TeamStatusLog, TeamMentor,
              TeamRegistration, TeamDocument, Podcast, Documentation,
              LogisticsPlan, VenueAllocation, VenueFoodRefreshment,
              VolunteerAssignment, EventBudget, SponsorshipFund, FinancialTransaction
"""
from django.db import models
from django.db.models.deletion import ProtectedError
from django.contrib.auth.models import AbstractUser


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class AdminPermission(models.Model):
    name = models.CharField(max_length=255)
    codename = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)
    is_2fa_enabled = models.BooleanField(default=False)
    id_proof = models.FileField(upload_to='id_proofs/', null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    profile_image = models.ImageField(upload_to='profiles/', null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class SuperadminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='superadmin_profile')


class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    permissions = models.ManyToManyField(AdminPermission, blank=True)


class SpocProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='spoc_profile')
    institution_name = models.CharField(max_length=255, null=True, blank=True)
    approved_by = models.ForeignKey(AdminProfile, null=True, blank=True, on_delete=models.SET_NULL)


class MentorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mentor_profile')
    expertise = models.CharField(max_length=255, null=True, blank=True)


class JuryProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='jury_profile')
    domain = models.CharField(max_length=255, null=True, blank=True)


class ExpertProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='expert_profile')
    domain = models.CharField(max_length=255, null=True, blank=True)


class ExecutiveProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='executive_profile')
    assigned_admin = models.ForeignKey(AdminProfile, null=True, blank=True, on_delete=models.SET_NULL)


class InAppMessage(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replies',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender} -> {self.recipient}: {self.subject or 'Message'}"


class TeamleadProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teamlead_profile')


class OTPVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        from django.utils import timezone
        import datetime
        return timezone.now() > self.created_at + datetime.timedelta(minutes=5)

    def __str__(self):
        return f"OTP for {self.user.username}"


class AuditLogQuerySet(models.QuerySet):
    def delete(self):
        raise ProtectedError("Audit logs cannot be deleted.", self)


class AuditLogManager(models.Manager):
    def get_queryset(self):
        return AuditLogQuerySet(self.model, using=self._db)


class AuditLog(models.Model):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'

    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
    ]

    actor = models.ForeignKey(
        'User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
    )
    actor_username = models.CharField(max_length=150, blank=True)
    actor_email = models.EmailField(blank=True)

    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    app_label = models.CharField(max_length=100, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    object_pk = models.CharField(max_length=255, db_index=True)
    object_repr = models.TextField(blank=True)

    changes = models.JSONField(default=dict, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)

    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['app_label', 'model_name', 'object_pk']),
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]

    def delete(self, *args, **kwargs):
        raise ProtectedError("Audit logs cannot be deleted.", [self])

    def __str__(self):
        return f"{self.get_action_display()} {self.app_label}.{self.model_name} #{self.object_pk}"


class SpocInvitation(models.Model):
    """
    Stores a pending SPOC application.
    Created when super-admin sends invite email.
    SPOC fills the public form → data lands here.
    After approval → User + SpocProfile are created via post_save signal.
    """
    STATUS_CHOICES = [
        ('invited',  'Invited'),
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    ]

    invited_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='spoc_invitations_sent'
    )

    email = models.EmailField(unique=True)
    # ForeignKey to events.Hackathon using string reference to avoid circular import
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, null=True, blank=True
    )

    token = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='invited')

    first_name = models.CharField(max_length=100, blank=True)
    last_name  = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    gender     = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    institution_name    = models.CharField(max_length=255, blank=True)
    city                = models.CharField(max_length=100, blank=True)
    state               = models.CharField(max_length=100, blank=True)
    institution_email   = models.EmailField(blank=True)
    institution_address = models.TextField(blank=True)
    institution_head_name   = models.CharField(max_length=255, blank=True)
    institution_head_email  = models.EmailField(blank=True)
    institution_contact     = models.CharField(max_length=20, blank=True)
    institution_location    = models.CharField(max_length=255, blank=True)
    institution_logo        = models.ImageField(upload_to='institution_logos/', null=True, blank=True)

    id_proof = models.FileField(upload_to='spoc_id_proofs/', null=True, blank=True)

    invited_at   = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    approved_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='spoc_approvals'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_user = models.OneToOneField(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='from_invitation'
    )

    def __str__(self):
        return f"Invite → {self.email} [{self.status}]"


class Institution(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, null=True, blank=True)
    approved_by = models.ForeignKey(AdminProfile, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.name


class InstitutionExtended(models.Model):
    """Extended institution data collected from SPOC form."""
    institution = models.OneToOneField(
        'Institution', on_delete=models.CASCADE, related_name='extended'
    )
    email                 = models.EmailField(blank=True)
    address               = models.TextField(blank=True)
    institution_head_name = models.CharField(max_length=255, blank=True)
    institution_head_email = models.EmailField(blank=True)
    contact_no            = models.CharField(max_length=20, blank=True)
    logo                  = models.ImageField(upload_to='institution_logos/', null=True, blank=True)

    def __str__(self):
        return f"Extended: {self.institution.name}"


class SpocInstitutionMap(models.Model):
    """Many-to-many between SPOC and Institution."""
    spoc        = models.ForeignKey('SpocProfile', on_delete=models.CASCADE)
    institution = models.ForeignKey('Institution', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('spoc', 'institution')

    def __str__(self):
        return f"{self.spoc.user.username} → {self.institution.name}"


class JuryInvitation(models.Model):
    """
    Staged invitation record for jury member onboarding.
    Created when super-admin sends an invite email.
    Jury member fills a public form → data lands here.
    After admin approval → User + JuryProfile are created inline.
    """
    STATUS_CHOICES = [
        ('invited',   'Invited'),
        ('pending',   'Pending Review'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('suspended', 'Suspended'),
    ]

    invited_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jury_invitations_sent'
    )
    email = models.EmailField(unique=True)
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, null=True, blank=True
    )

    token  = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='invited')

    # Personal details (filled by jury member via public form)
    first_name   = models.CharField(max_length=100, blank=True)
    last_name    = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    gender       = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Professional details
    organization = models.CharField(max_length=255, blank=True,
                                    help_text="Affiliated institution / company")
    designation  = models.CharField(max_length=255, blank=True,
                                    help_text="Job title / designation")
    domain       = models.CharField(max_length=255, blank=True,
                                    help_text="Area of expertise / judging domain")
    linkedin_url = models.URLField(blank=True)
    bio          = models.TextField(blank=True, help_text="Short professional bio")

    id_proof = models.FileField(upload_to='jury_id_proofs/', null=True, blank=True)
    photo    = models.ImageField(upload_to='jury_photos/', null=True, blank=True)

    invited_at   = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    approved_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jury_approvals'
    )
    approved_at      = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_user = models.OneToOneField(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='from_jury_invitation'
    )

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def __str__(self):
        return f"Jury Invite → {self.email} [{self.status}]"


class ExpertInvitation(models.Model):
    """
    Staged invitation record for expert member onboarding.
    Created when super-admin sends an invite email.
    Expert member fills a public form → data lands here.
    After admin approval → User + ExpertProfile are created inline.
    """
    STATUS_CHOICES = [
        ('invited',   'Invited'),
        ('pending',   'Pending Review'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('suspended', 'Suspended'),
    ]

    invited_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expert_invitations_sent'
    )
    email = models.EmailField(unique=True)
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, null=True, blank=True
    )

    token  = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='invited')

    # Personal details (filled by expert member via public form)
    first_name   = models.CharField(max_length=100, blank=True)
    last_name    = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    gender       = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Professional details
    organization = models.CharField(max_length=255, blank=True,
                                    help_text="Affiliated institution / company")
    designation  = models.CharField(max_length=255, blank=True,
                                    help_text="Job title / designation")
    domain       = models.CharField(max_length=255, blank=True,
                                    help_text="Area of expertise / judging domain")
    linkedin_url = models.URLField(blank=True)
    bio          = models.TextField(blank=True, help_text="Short professional bio")

    id_proof = models.FileField(upload_to='expert_id_proofs/', null=True, blank=True)
    photo    = models.ImageField(upload_to='expert_photos/', null=True, blank=True)

    invited_at   = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    approved_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expert_approvals'
    )
    approved_at      = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_user = models.OneToOneField(
        'User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='from_expert_invitation'
    )

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def __str__(self):
        return f"Expert Invite → {self.email} [{self.status}]"
