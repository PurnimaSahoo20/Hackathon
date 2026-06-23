"""
events/models.py

Contains: Hackathon, ProblemStatement, CreativeMaterial

IMPORTANT: db_table is set to preserve existing database table names
(originally created by the accounts app) so NO data migration is needed.
All ForeignKey references to User/SuperadminProfile use string app_label.
"""
from django.db import models
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

    round_1_name = models.CharField(max_length=255, default='Round 1')
    round_1_start_date = models.DateField(null=True, blank=True)
    round_1_end_date = models.DateField(null=True, blank=True)
    round_1_is_enabled = models.BooleanField(default=True)
    round_2_name = models.CharField(max_length=255, default='Round 2')
    round_2_start_date = models.DateField(null=True, blank=True)
    round_2_end_date = models.DateField(null=True, blank=True)
    round_2_is_enabled = models.BooleanField(default=True)
    round_3_name = models.CharField(max_length=255, default='Round 3')
    round_3_start_date = models.DateField(null=True, blank=True)
    round_3_end_date = models.DateField(null=True, blank=True)
    round_3_is_enabled = models.BooleanField(default=True)
    round_4_name = models.CharField(max_length=255, default='Round 4')
    round_4_start_date = models.DateField(null=True, blank=True)
    round_4_end_date = models.DateField(null=True, blank=True)
    round_4_is_enabled = models.BooleanField(default=True)
    round_5_name = models.CharField(max_length=255, default='Round 5')
    round_5_start_date = models.DateField(null=True, blank=True)
    round_5_end_date = models.DateField(null=True, blank=True)
    round_5_is_enabled = models.BooleanField(default=True)

    min_team_size = models.IntegerField(default=1)
    max_team_size = models.IntegerField(default=4)
    number_of_mentors = models.IntegerField(default=0)
    total_team_members = models.IntegerField(default=4)

    number_of_rounds = models.IntegerField(default=1)

    status = models.CharField(max_length=50, default='Draft')

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

    class Meta:
        db_table = 'events_roundmarkingparameter'

    def __str__(self):
        return f"{self.hackathon.name} - R{self.round_number} - {self.name}"
