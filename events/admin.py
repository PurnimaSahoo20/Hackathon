from django.contrib import admin
from .models import Hackathon, ProblemStatement, CreativeMaterial


@admin.register(Hackathon)
class HackathonAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization_name', 'status', 'registration_open',
                    'registration_close', 'number_of_rounds', 'min_team_size',
                    'max_team_size', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'organization_name')
    ordering = ('-created_at',)
    list_per_page = 15
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'organization_name', 'organization_logo', 'created_by', 'status')
        }),
        ('Approval', {'fields': ('approval_date', 'approval_letter')}),
        ('Timeline', {
            'fields': ('poster_launching_date', 'website_launching_date',
                       'registration_open', 'registration_close')
        }),
        ('Rounds', {'fields': (
            'number_of_rounds',
            'round_1_name', 'round_1_start_date', 'round_1_end_date', 'round_1_is_enabled',
            'round_2_name', 'round_2_start_date', 'round_2_end_date', 'round_2_is_enabled',
            'round_3_name', 'round_3_start_date', 'round_3_end_date', 'round_3_is_enabled',
            'round_4_name', 'round_4_start_date', 'round_4_end_date', 'round_4_is_enabled',
            'round_5_name', 'round_5_start_date', 'round_5_end_date', 'round_5_is_enabled',
        )}),
        ('Team Settings', {
            'fields': ('min_team_size', 'max_team_size', 'total_team_members', 'number_of_mentors')
        }),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(ProblemStatement)
class ProblemStatementAdmin(admin.ModelAdmin):
    list_display = ('title', 'hackathon', 'domain', 'is_published', 'created_at')
    list_filter = ('hackathon', 'domain', 'is_published')
    search_fields = ('title', 'domain', 'hackathon__name')
    ordering = ('-created_at',)
    list_per_page = 20
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CreativeMaterial)
class CreativeMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'hackathon', 'is_published', 'is_suspended', 'uploaded_at')
    list_filter = ('hackathon', 'is_published', 'is_suspended')
    search_fields = ('title', 'hackathon__name')
    ordering = ('-uploaded_at',)
    list_per_page = 20
