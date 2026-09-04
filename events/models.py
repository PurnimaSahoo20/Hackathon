"""
events/models.py

Contains: Hackathon, HackathonDomain, ProblemStatement, CreativeMaterial

IMPORTANT: db_table is set to preserve existing database table names
(originally created by the accounts app) so NO data migration is needed.
All ForeignKey references to User/SuperadminProfile use string app_label.
"""
from django.db import models
from django.utils.text import slugify
from django.utils import timezone


LANDING_SECTION_CHOICES = [
    ('latest-news', 'Latest News'),
    ('podcasts', 'Podcasts'),
    ('gallery', 'Gallery'),
    ('testimonials', 'Testimonials'),
    ('voice-of-inspiration', 'Voice of Inspiration'),
    ('tracks', 'Track Cards'),
    ('hero-banner', 'Hero Banner'),
]

LANDING_SECTION_LABELS = {value: label for value, label in LANDING_SECTION_CHOICES}


class Hackathon(models.Model):
    name = models.CharField(max_length=255)
    organization_name = models.CharField(max_length=255)
    organization_logo = models.ImageField(upload_to='hackathon_logos/', null=True, blank=True)
    created_by = models.ForeignKey(
        'accounts.SuperadminProfile', on_delete=models.CASCADE, null=True, blank=True
    )

    approval_date = models.DateField(null=True, blank=True)
    approval_letter = models.FileField(upload_to='approvals/', null=True, blank=True)

    poster_launching_date = models.DateField(null=True, blank=True)
    website_launching_date = models.DateField(null=True, blank=True)

    registration_open = models.DateField(null=True, blank=True)
    registration_close = models.DateField(null=True, blank=True)

    ROUND_TYPE_CHOICES = [('Online', 'Online'), ('Offline', 'Offline')]

    round_1_name = models.CharField(max_length=255, default='Round 1')
    round_1_start_date = models.DateField(null=True, blank=True)
    round_1_end_date = models.DateField(null=True, blank=True)
    round_1_is_enabled = models.BooleanField(default=True)
    round_1_type = models.CharField(max_length=50, choices=ROUND_TYPE_CHOICES, default='Online')
    round_1_venue = models.CharField(max_length=255, null=True, blank=True)

    round_2_name = models.CharField(max_length=255, default='Round 2')
    round_2_start_date = models.DateField(null=True, blank=True)
    round_2_end_date = models.DateField(null=True, blank=True)
    round_2_is_enabled = models.BooleanField(default=True)
    round_2_type = models.CharField(max_length=50, choices=ROUND_TYPE_CHOICES, default='Online')
    round_2_venue = models.CharField(max_length=255, null=True, blank=True)

    round_3_name = models.CharField(max_length=255, default='Round 3')
    round_3_start_date = models.DateField(null=True, blank=True)
    round_3_end_date = models.DateField(null=True, blank=True)
    round_3_is_enabled = models.BooleanField(default=True)
    round_3_type = models.CharField(max_length=50, choices=ROUND_TYPE_CHOICES, default='Online')
    round_3_venue = models.CharField(max_length=255, null=True, blank=True)

    round_4_name = models.CharField(max_length=255, default='Round 4')
    round_4_start_date = models.DateField(null=True, blank=True)
    round_4_end_date = models.DateField(null=True, blank=True)
    round_4_is_enabled = models.BooleanField(default=True)
    round_4_type = models.CharField(max_length=50, choices=ROUND_TYPE_CHOICES, default='Online')
    round_4_venue = models.CharField(max_length=255, null=True, blank=True)

    round_5_name = models.CharField(max_length=255, default='Round 5')
    round_5_start_date = models.DateField(null=True, blank=True)
    round_5_end_date = models.DateField(null=True, blank=True)
    round_5_is_enabled = models.BooleanField(default=True)
    round_5_type = models.CharField(max_length=50, choices=ROUND_TYPE_CHOICES, default='Online')
    round_5_venue = models.CharField(max_length=255, null=True, blank=True)

    # Round Total Marks (for parameter sum validation)
    round_1_total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100.00)
    round_2_total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100.00)
    round_3_total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100.00)
    round_4_total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100.00)
    round_5_total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100.00)

    min_team_size = models.IntegerField(default=1)
    max_team_size = models.IntegerField(default=4)
    number_of_mentors = models.IntegerField(default=0)
    total_team_members = models.IntegerField(default=4)

    number_of_rounds = models.IntegerField(default=1)

    # Branding & Media
    event_logo = models.ImageField(upload_to='hackathon_logos/', null=True, blank=True,
                                   help_text='Event logo displayed on the right side of the landing page navbar.')
    platform_logo = models.ImageField(upload_to='hackathon_logos/', null=True, blank=True,
                                      help_text='HackNexus/platform logo displayed on the left side of the landing page navbar.')
    hero_banner = models.ImageField(upload_to='hackathon_banners/', null=True, blank=True,
                                    help_text='Background banner image for the hero section on the landing page.')

    status = models.CharField(max_length=50, default='Draft')

    # ── Jury Round Control ──
    current_jury_round = models.IntegerField(
        default=1,
        help_text="The round for which jury panels can currently be created. Advances when admin promotes teams."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Preserve the original table name to avoid data migration
        db_table = 'accounts_hackathon'

    def __str__(self):
        return self.name

    def get_rounds(self):
        rounds = []
        for number in range(1, min(self.number_of_rounds or 1, 5) + 1):
            rounds.append({
                'number': number,
                'name': getattr(self, f'round_{number}_name'),
                'start_date': getattr(self, f'round_{number}_start_date'),
                'end_date': getattr(self, f'round_{number}_end_date'),
                'is_enabled': getattr(self, f'round_{number}_is_enabled'),
                'type': getattr(self, f'round_{number}_type', 'Online'),
                'venue': getattr(self, f'round_{number}_venue', None),
            })
        return rounds

    def get_active_round(self, date=None):
        current_date = date or timezone.localdate()
        for round_data in self.get_rounds():
            if (
                round_data['is_enabled'] and
                round_data['start_date'] and
                round_data['end_date'] and
                round_data['start_date'] <= current_date <= round_data['end_date']
            ):
                return round_data
        return None

    @property
    def active_round(self):
        return self.get_active_round()


class ProblemStatement(models.Model):
    hackathon = models.ForeignKey(Hackathon, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    landing_sections = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    pdf_file = models.FileField(upload_to='problem_statements/pdfs/', null=True, blank=True)

    class Meta:
        db_table = 'accounts_problemstatement'

    def __str__(self):
        return self.title


class CreativeMaterial(models.Model):
    hackathon = models.ForeignKey(Hackathon, on_delete=models.CASCADE, related_name='creatives')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='creatives/')
    material_type = models.CharField(max_length=50, db_column='material_type', default='creative')
    speaker_name = models.CharField(max_length=255, blank=True, default='')
    designation = models.CharField(max_length=255, blank=True, default='')
    institute_name = models.CharField(max_length=255, blank=True, default='')
    quote_text = models.TextField(blank=True, default='')
    profile_image = models.ImageField(upload_to='creatives/profile_pics/', null=True, blank=True)
    is_published = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    landing_sections = models.JSONField(default=list, blank=True)
    display_priority = models.PositiveIntegerField(default=0, help_text="Priority order 1-10 for Voice of Inspiration. 0 means no priority.")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_creativematerial'

    def __str__(self):
        return self.title

    @property
    def is_video(self):
        name = getattr(self.file, 'name', '').lower()
        return name.endswith(('.mp4', '.webm', '.ogg', '.mov', '.m4v'))



class RoundMarkingParameter(models.Model):
    hackathon = models.ForeignKey(Hackathon, on_delete=models.CASCADE, related_name='marking_parameters')
    round_number = models.IntegerField()
    name = models.CharField(max_length=255)
    is_others = models.BooleanField(default=False)
    cutoff_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="The cutoff score required for this parameter")
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100.00, help_text="The maximum marks (total marks) allowed for this parameter")

    class Meta:
        db_table = 'events_roundmarkingparameter'

    def __str__(self):
        return f"{self.hackathon.name} - R{self.round_number} - {self.name}"


class MarkingSubParameter(models.Model):
    """Optional sub-parameters that break down a marking parameter into finer criteria."""
    parent_parameter = models.ForeignKey(
        RoundMarkingParameter, on_delete=models.CASCADE, related_name='sub_parameters'
    )
    name = models.CharField(max_length=255)
    cutoff_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="The score for this sub-parameter")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'events_markingsubparameter'
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"{self.parent_parameter.name} → {self.name}"


class HackathonDomain(models.Model):
    """Dynamic PS domains configured per hackathon event."""
    hackathon = models.ForeignKey(Hackathon, on_delete=models.CASCADE, related_name='domains')
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    icon = models.CharField(max_length=10, default='🧩')
    color = models.CharField(max_length=20, default='#eef2ff')
    subtitle = models.CharField(max_length=500, blank=True, default='')
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'events_hackathondomain'
        ordering = ['display_order', 'name']

    def __str__(self):
        return f"{self.hackathon.name} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class HeroBannerImage(models.Model):
    """Multiple hero banner images per hackathon for carousel rotation."""
    hackathon = models.ForeignKey(Hackathon, on_delete=models.CASCADE, related_name='hero_banners')
    image = models.ImageField(upload_to='hackathon_banners/')
    display_order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'events_herobannerimage'
        ordering = ['display_order', 'uploaded_at']

    def __str__(self):
        return f"{self.hackathon.name} - Banner #{self.display_order}"


class RoundJuryConfig(models.Model):
    """Per-round jury/expert team composition blueprint.

    Defines how many jury members and experts each evaluation team
    should have for a specific round.  The actual team instances
    (with names) are stored in JuryTeam.
    """
    hackathon = models.ForeignKey(Hackathon, on_delete=models.CASCADE, related_name='jury_configs')
    round_number = models.IntegerField()
    num_jury_per_team = models.IntegerField(
        default=1, help_text='Number of jury members in each evaluation team'
    )
    num_experts_per_team = models.IntegerField(
        default=1, help_text='Number of experts in each evaluation team'
    )

    # ── Lock control ──
    is_locked = models.BooleanField(
        default=False,
        help_text="When True, no new panels can be created and assignments are frozen for this round."
    )
    is_team_locked = models.BooleanField(
        default=False,
        help_text="When True, team assignments are locked for this round."
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='locked_jury_configs'
    )
    alter_assignment = models.BooleanField(
        default=False,
        help_text="When True, the round robin assignment order of teams to panels is altered."
    )
    alter_offset = models.IntegerField(
        default=0,
        help_text="The rotational offset used to alter the round robin team panel assignment order."
    )
    has_assigned_teams = models.BooleanField(
        default=False,
        help_text="When True, team panel assignments have been initiated and saved for the round."
    )

    class Meta:
        db_table = 'events_roundjuryconfig'
        unique_together = ('hackathon', 'round_number')

    def __str__(self):
        return (
            f"{self.hackathon.name} - R{self.round_number}: "
            f"{self.num_jury_per_team} jury + {self.num_experts_per_team} experts per team"
        )


class JuryTeam(models.Model):
    """A named evaluation team for a specific round.

    Each team will later be assigned jury/expert users and mapped to
    problem statements (handled separately from the event form).
    """
    hackathon = models.ForeignKey(Hackathon, on_delete=models.CASCADE, related_name='jury_teams')
    round_number = models.IntegerField()
    name = models.CharField(max_length=255, help_text='Team label, e.g. Panel A')
    display_order = models.PositiveIntegerField(default=0)
    problem_statement = models.ForeignKey('events.ProblemStatement', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_jury_teams')
    juries = models.ManyToManyField('accounts.JuryProfile', blank=True, related_name='assigned_jury_teams')
    experts = models.ManyToManyField('accounts.ExpertProfile', blank=True, related_name='assigned_jury_teams')

    class Meta:
        db_table = 'events_juryteam'
        ordering = ['round_number', 'display_order', 'name']

    def __str__(self):
        return f"{self.hackathon.name} - R{self.round_number} - {self.name}"

