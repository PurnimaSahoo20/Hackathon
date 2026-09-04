"""
features/models.py

Contains: Team, Venue, TeamMember, TeamStatusLog, TeamMentor,
          TeamRegistration, TeamDocument, Podcast, Documentation,
          LogisticsPlan, VenueAllocation, VenueFoodRefreshment,
          VolunteerAssignment, EventBudget, SponsorshipFund, FinancialTransaction

IMPORTANT: db_table is set to preserve existing database table names
(originally created by the accounts app) so NO data migration is needed.
All cross-app ForeignKeys use string 'app_label.ModelName' format.
"""
from django.db import models


# ─────────────────────────────────────────────────────────────
# TEAM & MEMBERS
# ─────────────────────────────────────────────────────────────

class Team(models.Model):
    team_name = models.CharField(max_length=255)
    hackathon = models.ForeignKey('events.Hackathon', on_delete=models.CASCADE)
    institution = models.ForeignKey(
        'accounts.Institution', null=True, blank=True, on_delete=models.SET_NULL
    )
    team_leader = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='led_teams'
    )
    problem_statement = models.ForeignKey(
        'events.ProblemStatement', null=True, blank=True, on_delete=models.SET_NULL
    )
    declared_member_count = models.PositiveIntegerField(default=1)
    leader_role_in_team = models.CharField(max_length=100, default='Leader')
    leader_aadhaar_proof = models.FileField(upload_to='team_documents/aadhaar/', max_length=255, null=True, blank=True)
    leader_college_id_proof = models.FileField(upload_to='team_documents/college_ids/', max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, default='Active')
    current_round = models.IntegerField(default=1, help_text="The round this team is currently in")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_team'

    def __str__(self):
        return self.team_name


class TeamMember(models.Model):
    """Individual members of a team (apart from team leader)."""
    team = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    role_in_team = models.CharField(max_length=100, blank=True, default='Member')
    aadhaar_proof = models.FileField(upload_to='team_documents/aadhaar/', max_length=255, null=True, blank=True)
    college_id_proof = models.FileField(upload_to='team_documents/college_ids/', max_length=255, null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_teammember'
        unique_together = ('team', 'user')

    def __str__(self):
        return f"{self.user.username} in {self.team.team_name}"


class TeamStatusLog(models.Model):
    """
    Audit trail every time a team's status changes.
    """
    STATUS_CHOICES = [
        ('registered',       'Registered'),
        ('pending_mentor',   'Pending Mentor Verification'),
        ('mentor_approved',  'Mentor Approved'),
        ('mentor_rejected',  'Mentor Rejected'),
        ('pending_spoc',     'Pending SPOC Verification'),
        ('spoc_approved',    'SPOC Approved / Active'),
        ('admin_approved',   'Admin Approved'),
        ('spoc_rejected',    'SPOC Rejected'),
        ('submitted',        'Submission Done'),
        ('evaluated',        'Evaluated'),
        ('disqualified',     'Disqualified'),
    ]

    team = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='status_logs')
    old_status = models.CharField(max_length=50, blank=True)
    new_status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    changed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    note = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_teamstatuslog'
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.team.team_name}: {self.old_status} → {self.new_status}"


class TeamMentor(models.Model):
    """Which mentor is assigned to which team."""
    team = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='assigned_mentors')
    mentor = models.ForeignKey('accounts.MentorProfile', on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_teammentor'
        unique_together = ('team', 'mentor')

    def __str__(self):
        return f"Mentor {self.mentor.user.username} → {self.team.team_name}"


class TeamRegistration(models.Model):
    """
    Staging table for team registrations before admin approval.
    """
    STATUS_CHOICES = [
        ('pending',    'Pending Review'),
        ('approved',   'Approved'),
        ('rejected',   'Rejected'),
        ('suspended',  'Suspended'),
    ]

    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='team_registrations'
    )
    team_name = models.CharField(max_length=255)
    team_leader = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='led_registrations'
    )
    institution = models.ForeignKey(
        'accounts.Institution', on_delete=models.SET_NULL, null=True, blank=True
    )
    problem_statement = models.ForeignKey(
        'events.ProblemStatement', on_delete=models.SET_NULL, null=True, blank=True
    )
    mentor = models.ForeignKey(
        'accounts.MentorProfile', on_delete=models.SET_NULL, null=True, blank=True
    )
    leader_details = models.JSONField(default=dict, blank=True)
    members_data = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='team_reviews'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_note = models.TextField(blank=True)
    suspension_note = models.TextField(blank=True)
    created_team = models.OneToOneField(
        'Team', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='from_registration'
    )
    registration_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
    bank_reminder_sent = models.BooleanField(default=False)
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_teamregistration'
        ordering = ['-registered_at']

    def save(self, *args, **kwargs):
        if not self.registration_token:
            import uuid
            self.registration_token = uuid.uuid4().hex[:24]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.team_name} — {self.hackathon.name} [{self.status}]"

    def get_member_count(self):
        return len(self.members_data) + 1  # +1 for leader

    def get_members_display(self):
        """Returns list of member dicts for template rendering."""
        return self.members_data or []


class TeamEvaluationAssignment(models.Model):
    """Assignment of juries and experts to a team for evaluation in a specific round."""
    team = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='evaluation_assignments')
    round_number = models.IntegerField(default=1)
    
    # 3 Juries
    jury_1 = models.ForeignKey('accounts.JuryProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments_as_jury1')
    jury_2 = models.ForeignKey('accounts.JuryProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments_as_jury2')
    jury_3 = models.ForeignKey('accounts.JuryProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments_as_jury3')
    
    # 2 Experts
    expert_1 = models.ForeignKey('accounts.ExpertProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments_as_expert1')
    expert_2 = models.ForeignKey('accounts.ExpertProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments_as_expert2')
    
    assigned_panel = models.ForeignKey(
        'events.JuryTeam', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_team_evaluations'
    )
    status = models.CharField(max_length=50, default='Pending') # Pending or Assigned
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'features_teamevaluationassignment'
        unique_together = ('team', 'round_number')

    def is_mandatory_assigned(self):
        """Checks if at least 1 jury and 1 expert are assigned."""
        return bool(self.jury_1 and self.expert_1)

    def is_fully_assigned(self):
        """Checks if all 3 juries and 2 experts are assigned."""
        return bool(self.jury_1 and self.jury_2 and self.jury_3 and self.expert_1 and self.expert_2)

    def __str__(self):
        return f"Eval for {self.team.team_name} (Round {self.round_number})"


class TeamDocument(models.Model):
    """Documents/files attached to a team registration."""
    DOC_TYPE_CHOICES = [
        ('id_proof',     'ID Proof'),
        ('project',      'Project File'),
        ('presentation', 'Presentation'),
        ('report',       'Report'),
        ('other',        'Other'),
    ]

    registration = models.ForeignKey(
        TeamRegistration, on_delete=models.CASCADE,
        null=True, blank=True, related_name='documents'
    )
    team = models.ForeignKey(
        'Team', on_delete=models.CASCADE,
        null=True, blank=True, related_name='documents'
    )
    uploaded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    doc_type = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES, default='other')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='team_documents/', max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_teamdocument'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title} ({self.doc_type})"


# ─────────────────────────────────────────────────────────────
# VENUE & LOGISTICS
# ─────────────────────────────────────────────────────────────

class Venue(models.Model):
    STATUS_CHOICES = [
        ('Active',    'Active'),
        ('Suspended', 'Suspended'),
    ]

    hackathon        = models.ForeignKey('events.Hackathon', on_delete=models.CASCADE)
    venue_name       = models.CharField(max_length=255)
    address          = models.TextField(null=True, blank=True)   # kept for backward-compat

    # ── New fields ──
    location         = models.CharField(max_length=255, blank=True)
    capacity         = models.PositiveIntegerField(null=True, blank=True)
    landmark         = models.CharField(max_length=255, blank=True)
    contact_details  = models.CharField(max_length=255, blank=True)
    event_date       = models.CharField(max_length=100, blank=True,
                                       help_text="e.g. Mar 20-22, 2026")
    facilities       = models.JSONField(default=list, blank=True,
                                       help_text="List of facility strings")
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_venue'

    def __str__(self):
        return self.venue_name


class LogisticsPlan(models.Model):
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='logistics_plans'
    )
    plan_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    infrastructure_readiness = models.IntegerField(default=0, help_text="Percentage 0-100")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_logisticsplan'

    def __str__(self):
        return f"{self.plan_name} ({self.hackathon.name})"


class VenueAllocation(models.Model):
    venue = models.ForeignKey('Venue', on_delete=models.CASCADE, related_name='allocations')
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='venue_allocations'
    )
    confirmation_letter = models.FileField(upload_to='venue/confirmations/', null=True, blank=True)
    allocated_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, default='Pending')

    class Meta:
        db_table = 'accounts_venueallocation'

    def __str__(self):
        return f"{self.venue.venue_name} - {self.hackathon.name}"


class VenueFoodRefreshment(models.Model):
    venue = models.ForeignKey('Venue', on_delete=models.CASCADE, related_name='food_refreshments')
    vendor_name = models.CharField(max_length=255)
    contact_info = models.CharField(max_length=255, blank=True)
    menu_details = models.TextField(blank=True)
    headcount_estimation = models.IntegerField(default=0)
    cost_estimation = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'accounts_venuefoodrefreshment'

    def __str__(self):
        return f"{self.vendor_name} at {self.venue.venue_name}"


class VolunteerAssignment(models.Model):
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='volunteers'
    )
    volunteer_name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=20)
    role_description = models.CharField(max_length=255)
    assigned_venue = models.ForeignKey('Venue', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=50, default='Active')

    class Meta:
        db_table = 'accounts_volunteerassignment'

    def __str__(self):
        return f"{self.volunteer_name} - {self.role_description}"


# ─────────────────────────────────────────────────────────────
# CONTENT MANAGEMENT
# ─────────────────────────────────────────────────────────────

class Podcast(models.Model):
    """Video/audio resource linked to a hackathon and optionally a problem statement."""
    PUBLICATION_SCOPE_CHOICES = [
        ('draft', 'Draft'),
        ('website', 'Website'),
        ('internal', 'Internal Community'),
    ]

    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='podcasts'
    )
    problem_statement = models.ForeignKey(
        'events.ProblemStatement', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='podcasts'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    video_url = models.URLField(blank=True)
    video_file = models.FileField(upload_to='podcasts/', null=True, blank=True)
    thumbnail = models.ImageField(upload_to='podcast_thumbs/', null=True, blank=True)
    landing_sections = models.JSONField(default=list, blank=True)
    is_published = models.BooleanField(default=False)
    publication_scope = models.CharField(max_length=20, choices=PUBLICATION_SCOPE_CHOICES, default='draft')
    podcast_type = models.CharField(
        max_length=50,
        choices=[('podcast', 'Podcast'), ('expert_talk', 'Expert Talk')],
        default='podcast'
    )
    duration = models.CharField(max_length=100, blank=True, default='Featured')
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_podcast'

    def __str__(self):
        return self.title


class Documentation(models.Model):
    """Supplementary documents / resources for a problem statement or hackathon."""
    DOC_TYPE_CHOICES = [
        ('rulebook',  'Rulebook'),
        ('dataset',   'Dataset'),
        ('api_doc',   'API Documentation'),
        ('reference', 'Reference Material'),
        ('guideline', 'Guideline'),
        ('other',     'Other'),
    ]

    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='documentation'
    )
    problem_statement = models.ForeignKey(
        'events.ProblemStatement', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='documentation'
    )
    title = models.CharField(max_length=255)
    doc_type = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES, default='other')
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='documentation/', null=True, blank=True)
    external_url = models.URLField(blank=True)
    landing_sections = models.JSONField(default=list, blank=True)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_documentation'

    def __str__(self):
        return self.title


class SocialFeedEntry(models.Model):
    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('facebook', 'Facebook'),
        ('youtube', 'YouTube'),
        ('twitter', 'Twitter / X'),
        ('linkedin', 'LinkedIn'),
        ('website', 'Website'),
        ('other', 'Other'),
    ]

    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='social_feeds'
    )
    title = models.CharField(max_length=255)
    platform = models.CharField(max_length=30, choices=PLATFORM_CHOICES, default='instagram')
    published_date = models.DateField()
    external_url = models.URLField()
    is_published = models.BooleanField(default=True)
    is_suspended = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'features_socialfeedentry'
        ordering = ['-published_date', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_platform_display()})"


class FAQItem(models.Model):
    """Dynamic FAQ entries managed per hackathon."""
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='faq_items'
    )
    question = models.CharField(max_length=500)
    answer = models.TextField()
    display_order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first")
    is_published = models.BooleanField(default=True)
    is_suspended = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'features_faqitem'
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return self.question[:80]


# ─────────────────────────────────────────────────────────────
# FINANCIAL MANAGEMENT
# ─────────────────────────────────────────────────────────────

class EventBudget(models.Model):
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='budgets'
    )
    total_budget = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    allocated_budget = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_eventbudget'

    def __str__(self):
        return f"Budget for {self.hackathon.name}"


class SponsorshipFund(models.Model):
    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='sponsorships'
    )
    sponsor_name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, default='')
    logo = models.ImageField(upload_to='sponsor_logos/', null=True, blank=True)
    amount_pledged = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    amount_received = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=50, default='Pending')
    date_received = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'accounts_sponsorshipfund'

    def __str__(self):
        return f"{self.sponsor_name} - {self.hackathon.name}"


class FinancialTransaction(models.Model):
    CATEGORY_CHOICES = [
        ('Team & Jury travel', 'Team & Jury travel Expenses'),
        ('Officials Travel',   'Officials Travel expenses'),
        ('Accommodation',      'Accommodation Expenses'),
        ('Printing & Stationary', 'Printing & Stationary Expenses'),
        ('Trophy and Awards',  'Trophy and Awards Expenses'),
        ('Food and refreshment', 'Food and refreshment'),
        ('Honorarium',         'Honorarium Expenses'),
        ('Other',              'Other Expenses'),
    ]

    hackathon = models.ForeignKey(
        'events.Hackathon', on_delete=models.CASCADE, related_name='transactions'
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=[('Income', 'Income'), ('Expense', 'Expense')],
        default='Expense'
    )
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_date = models.DateField()
    description = models.TextField(blank=True)
    receipt_file = models.FileField(upload_to='finance/receipts/', null=True, blank=True)
    processed_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = 'accounts_financialtransaction'

    def __str__(self):
        return f"{self.transaction_type} - {self.category} - {self.amount}"
