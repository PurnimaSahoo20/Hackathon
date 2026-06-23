"""
jury/models.py

Stores:
  - TeamEvaluation: marks submitted by a jury/expert member
  - EvaluatorProfile: extra profile, testimonial, and payout details
  - JuryMessage: lightweight communication records for evaluator portal
"""
from django.db import models


class TeamEvaluation(models.Model):
    """
    Stores the score given by one evaluator (jury or expert) to one team
    for one marking parameter in one round.
    """
    team = models.ForeignKey(
        'features.Team',
        on_delete=models.CASCADE,
        related_name='evaluations'
    )
    round_number = models.IntegerField(default=1)
    evaluator = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='submitted_evaluations'
    )
    parameter = models.ForeignKey(
        'events.RoundMarkingParameter',
        on_delete=models.CASCADE,
        related_name='evaluations'
    )
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    remarks = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jury_teamevaluation'
        unique_together = ('team', 'round_number', 'evaluator', 'parameter')
        ordering = ['team', 'round_number', 'parameter']

    def __str__(self):
        return (
            f"{self.evaluator.username} -> {self.team.team_name} "
            f"R{self.round_number} [{self.parameter.name}]: {self.score}"
        )


class EvaluatorProfile(models.Model):
    """Extra profile data used by jury and expert dashboards."""
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='evaluator_profile'
    )
    organization = models.CharField(max_length=255, blank=True)
    designation = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)
    testimonial_video = models.FileField(
        upload_to='jury/testimonials/',
        null=True,
        blank=True,
    )
    bank_account_holder = models.CharField(max_length=255, blank=True)
    bank_name = models.CharField(max_length=255, blank=True)
    branch_name = models.CharField(max_length=255, blank=True)
    account_number = models.CharField(max_length=64, blank=True)
    ifsc_code = models.CharField(max_length=32, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    cancelled_cheque = models.FileField(
        upload_to='jury/bank_docs/',
        null=True,
        blank=True,
    )
    payment_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'jury_evaluatorprofile'
        ordering = ['user__first_name', 'user__username']

    def __str__(self):
        return f"Evaluator profile for {self.user.username}"


class EvaluatorTravelDetail(models.Model):
    """Travel details submitted by jury/expert members for reimbursement visibility."""
    TRAVEL_MODE_CHOICES = [
        ('train', 'Train'),
        ('bus', 'Bus'),
        ('flight', 'Flight'),
        ('car', 'Car'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='evaluator_travel_details',
    )
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    journey_date = models.DateField()
    travel_mode = models.CharField(max_length=20, choices=TRAVEL_MODE_CHOICES, default='train')
    traveler_name = models.CharField(max_length=255, blank=True)
    ticket_number = models.CharField(max_length=100, blank=True)
    ticket_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    ticket_file = models.FileField(upload_to='jury/travel/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'jury_evaluatortraveldetail'
        ordering = ['-journey_date', '-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.origin} -> {self.destination}"


class JuryMessage(models.Model):
    """Direct messages between evaluators and their allowed contacts."""
    sender = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='jury_sent_messages',
    )
    recipient = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='jury_received_messages',
    )
    team = models.ForeignKey(
        'features.Team',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jury_messages',
    )
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f"{self.sender} -> {self.recipient}: {self.body[:40]}"
