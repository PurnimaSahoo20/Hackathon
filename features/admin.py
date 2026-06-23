from django.contrib import admin
from .models import (
    Team, TeamMember, TeamStatusLog, TeamMentor,
    TeamRegistration, TeamDocument,
    Venue, LogisticsPlan, VenueAllocation, VenueFoodRefreshment, VolunteerAssignment,
    Podcast, Documentation,
    EventBudget, SponsorshipFund, FinancialTransaction,
)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('team_name', 'hackathon', 'institution', 'team_leader', 'declared_member_count', 'problem_statement', 'status')
    list_filter = ('hackathon', 'status', 'institution')
    search_fields = ('team_name', 'team_leader__username', 'hackathon__name')
    ordering = ('team_name',)
    list_per_page = 25


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'team', 'role_in_team', 'has_aadhaar_proof', 'has_college_id_proof', 'joined_at')
    list_filter = ('team__hackathon',)
    search_fields = ('user__username', 'team__team_name')
    list_per_page = 25

    def has_aadhaar_proof(self, obj):
        return bool(obj.aadhaar_proof)
    has_aadhaar_proof.boolean = True

    def has_college_id_proof(self, obj):
        return bool(obj.college_id_proof)
    has_college_id_proof.boolean = True


@admin.register(TeamRegistration)
class TeamRegistrationAdmin(admin.ModelAdmin):
    list_display = ('team_name', 'hackathon', 'team_leader', 'status', 'registered_at')
    list_filter = ('status', 'hackathon')
    search_fields = ('team_name', 'team_leader__username')
    ordering = ('-registered_at',)
    list_per_page = 25


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('venue_name', 'hackathon', 'address')
    list_filter = ('hackathon',)
    search_fields = ('venue_name', 'hackathon__name', 'address')
    ordering = ('venue_name',)
    list_per_page = 20


@admin.register(Podcast)
class PodcastAdmin(admin.ModelAdmin):
    list_display = ('title', 'hackathon', 'is_published', 'created_at')
    list_filter = ('hackathon', 'is_published')
    search_fields = ('title', 'hackathon__name')
    ordering = ('-created_at',)
    list_per_page = 20


@admin.register(Documentation)
class DocumentationAdmin(admin.ModelAdmin):
    list_display = ('title', 'hackathon', 'doc_type', 'is_published', 'created_at')
    list_filter = ('hackathon', 'doc_type', 'is_published')
    search_fields = ('title', 'hackathon__name')
    ordering = ('-created_at',)
    list_per_page = 20


@admin.register(EventBudget)
class EventBudgetAdmin(admin.ModelAdmin):
    list_display = ('hackathon', 'total_budget', 'allocated_budget', 'created_at')
    list_filter = ('hackathon',)
    list_per_page = 20


@admin.register(SponsorshipFund)
class SponsorshipFundAdmin(admin.ModelAdmin):
    list_display = ('sponsor_name', 'hackathon', 'amount_pledged', 'amount_received', 'status')
    list_filter = ('hackathon', 'status')
    search_fields = ('sponsor_name',)
    list_per_page = 20


@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):
    list_display = ('hackathon', 'transaction_type', 'category', 'amount', 'transaction_date')
    list_filter = ('hackathon', 'transaction_type', 'category')
    ordering = ('-transaction_date',)
    list_per_page = 25
