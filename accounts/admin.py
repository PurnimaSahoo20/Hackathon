"""
accounts/admin.py

Registers only models that belong to the accounts app:
  Role, User, AdminPermission, SuperadminProfile, AdminProfile,
  SpocProfile, MentorProfile, JuryProfile, ExecutiveProfile,
  TeamleadProfile, OTPVerification, AuditLog, SpocInvitation, Institution,
  InstitutionExtended, SpocInstitutionMap

Models moved to events/admin.py:    Hackathon, ProblemStatement, CreativeMaterial
Models moved to features/admin.py:  Team, Venue, Podcast, Documentation,
                                    EventBudget, SponsorshipFund, FinancialTransaction
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    Role, User, AdminPermission, SuperadminProfile, AdminProfile,
    SpocProfile, MentorProfile, JuryProfile, ExecutiveProfile,
    TeamleadProfile, OTPVerification, SpocInvitation,
    Institution, InstitutionExtended, SpocInstitutionMap, AuditLog,
)


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'created_at', 'is_verified')
    list_filter = ('is_verified', 'created_at')
    search_fields = ('user__username', 'user__email', 'code')
    ordering = ('-created_at',)
    list_per_page = 20


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'updated_at')
    search_fields = ('name',)
    ordering = ('name',)
    list_per_page = 20


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'role', 'is_active', 'is_staff', 'is_verified', 'date_joined'
    )
    list_filter = ('role', 'is_active', 'is_staff', 'is_verified', 'gender')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone_number')
    ordering = ('-date_joined',)
    list_per_page = 25
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Extended Profile', {
            'fields': (
                'role', 'phone_number', 'gender', 'date_of_birth',
                'profile_image', 'id_proof', 'is_verified', 'is_2fa_enabled'
            )
        }),
    )


@admin.register(AdminPermission)
class AdminPermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'codename', 'description')
    search_fields = ('name', 'codename')
    ordering = ('name',)
    list_per_page = 20


@admin.register(SuperadminProfile)
class SuperadminProfileAdmin(admin.ModelAdmin):
    list_display = ('user',)
    search_fields = ('user__username', 'user__email')
    list_per_page = 20


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email', 'get_permissions_count')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name')
    filter_horizontal = ('permissions',)
    list_per_page = 20

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'

    def get_permissions_count(self, obj):
        return obj.permissions.count()
    get_permissions_count.short_description = '# Permissions'


@admin.register(ExecutiveProfile)
class ExecutiveProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email', 'assigned_admin')
    list_filter = ('assigned_admin',)
    search_fields = ('user__username', 'user__email', 'assigned_admin__user__username')
    list_per_page = 20

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(SpocProfile)
class SpocProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email', 'institution_name', 'approved_by')
    list_filter = ('approved_by',)
    search_fields = ('user__username', 'user__email', 'institution_name')
    list_per_page = 20

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(MentorProfile)
class MentorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email', 'expertise')
    search_fields = ('user__username', 'user__email', 'expertise')
    list_per_page = 20

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(JuryProfile)
class JuryProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email', 'domain')
    list_filter = ('domain',)
    search_fields = ('user__username', 'user__email', 'domain')
    list_per_page = 20

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(TeamleadProfile)
class TeamleadProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email')
    search_fields = ('user__username', 'user__email')
    list_per_page = 20

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(SpocInvitation)
class SpocInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'status', 'institution_name', 'city', 'state', 'invited_by', 'invited_at')
    list_filter = ('status',)
    search_fields = ('email', 'institution_name', 'city', 'state')
    ordering = ('-invited_at',)
    list_per_page = 20


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'approved_by')
    list_filter = ('approved_by',)
    search_fields = ('name', 'location')
    ordering = ('name',)
    list_per_page = 25


@admin.register(InstitutionExtended)
class InstitutionExtendedAdmin(admin.ModelAdmin):
    list_display = ('institution', 'email', 'institution_head_name', 'contact_no')
    search_fields = ('institution__name', 'email')
    list_per_page = 20


@admin.register(SpocInstitutionMap)
class SpocInstitutionMapAdmin(admin.ModelAdmin):
    list_display = ('spoc', 'institution')
    list_filter = ('institution',)
    search_fields = ('spoc__user__username', 'institution__name')
    list_per_page = 25


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'actor_username', 'action',
        'app_label', 'model_name', 'object_pk', 'request_method'
    )
    list_filter = ('action', 'app_label', 'model_name', 'created_at')
    search_fields = (
        'actor_username', 'actor_email', 'object_pk',
        'object_repr', 'request_path', 'ip_address'
    )
    readonly_fields = (
        'actor', 'actor_username', 'actor_email', 'action',
        'app_label', 'model_name', 'object_pk', 'object_repr',
        'changes', 'snapshot', 'request_method', 'request_path',
        'ip_address', 'user_agent', 'created_at',
    )
    ordering = ('-created_at',)
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
