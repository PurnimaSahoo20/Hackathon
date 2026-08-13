"""
FILE: accounts/urls.py  — REPLACE entirely
"""
from django.urls import path
from django.urls import reverse_lazy
from . import views
from .password_reset import HackathonPasswordResetView
from django.contrib.auth import views as auth_views

from features import views as feature_views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('logout/', views.logout_view, name='logout'),
    path(
        'password-reset/',
        HackathonPasswordResetView.as_view(
            template_name='accounts/password_reset_form.html',
            email_template_name='accounts/password_reset_email.html',
            subject_template_name='accounts/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    path('dashboard/', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('executive-dashboard/', views.executive_dashboard, name='executive_dashboard'),
    path('executive/profile/', views.executive_profile, name='executive_profile'),
    path('executive/profile/update/', views.update_executive_profile, name='update_executive_profile'),
    path('executive/users/', views.executive_user_status, name='executive_user_status'),
    path('executive/reminder/<int:user_id>/', views.executive_send_reminder, name='executive_send_reminder'),
    path('executive/inbox/', views.executive_inbox, name='executive_inbox'),
    path('executive/compose/', views.executive_compose, name='executive_compose'),
    path('executive/messages/<int:msg_id>/', views.executive_message_detail, name='executive_message_detail'),
    path('admin/inbox/', views.admin_inbox, name='admin_inbox'),
    path('admin/compose/', views.admin_compose, name='admin_compose'),
    path('profile/', views.superadmin_profile, name='superadmin_profile'),
    path('profile/update/', views.update_superadmin_profile, name='update_superadmin_profile'),
    path('admin-profile/', views.admin_profile, name='admin_profile'),
    path('admin-profile/update/', views.update_admin_profile, name='update_admin_profile'),
    path('executive/resend-credentials/<int:exec_user_id>/', views.resend_executive_credentials, name='resend_executive_credentials'),

    # User management
    path('create-user/', views.create_user, name='create_user'),
    path('inline-edit-user/<int:user_id>/', views.inline_edit_user, name='inline_edit_user'),
    path('toggle-user-status/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('view-user/<int:user_id>/', views.view_user, name='view_user'),
    path('edit-user/<int:user_id>/', views.edit_user, name='edit_user'),
    path('delete-user/<int:user_id>/', views.delete_user, name='delete_user'),

    # Public Registration (Standalone)
    path('spoc-register/<str:token>/', feature_views.spoc_register_form, name='spoc_register_form'),
    path('spoc_register/<str:token>/', feature_views.spoc_register_form),
]
