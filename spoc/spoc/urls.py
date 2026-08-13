"""spoc/urls.py"""
from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/',          views.spoc_login,        name='spoc_login'),
    path('login/otp/',      views.spoc_verify_otp,   name='spoc_verify_otp'),
    path('logout/',         views.spoc_logout,       name='spoc_logout'),

    # Dashboard
    path('',                views.spoc_dashboard,    name='spoc_dashboard'),
    path('dashboard/',      views.spoc_dashboard,    name='spoc_dashboard'),

    # Teams
    path('teams/',                          views.spoc_teams,           name='spoc_teams'),
    path('teams/<str:token>/',              views.spoc_team_detail,     name='spoc_team_detail'),
    path('teams/<str:token>/approve/',      views.spoc_approve_team,    name='spoc_approve_team'),
    path('teams/<str:token>/reject/',       views.spoc_reject_team,     name='spoc_reject_team'),
    path('teams/<str:token>/download-template/', views.spoc_download_approval_template, name='spoc_download_approval_template'),
    path('teams/<str:token>/final-letter/', views.spoc_submit_final_letter, name='spoc_submit_final_letter'),

    # Modifications
    path('modifications/',                          views.spoc_modifications,           name='spoc_modifications'),
    path('modifications/<int:mod_id>/approve/',     views.spoc_approve_modification,    name='spoc_approve_modification'),
    path('modifications/<int:mod_id>/reject/',      views.spoc_reject_modification,     name='spoc_reject_modification'),

    # Results
    path('results/',        views.spoc_results,      name='spoc_results'),

    # Messages
    path('messages/',                       views.spoc_messages,        name='spoc_messages'),
    path('messages/<int:user_id>/',         views.spoc_conversation,    name='spoc_conversation'),
    path('messages/send/',                  views.spoc_send_message,    name='spoc_send_message'),
    path('messages/reply-team/<int:message_id>/', views.spoc_reply_team_message, name='spoc_reply_team_message'),

    # Announcements & Activity
    path('announcements/',  views.spoc_announcements, name='spoc_announcements'),
    path('activity/',       views.spoc_activity_log,  name='spoc_activity_log'),

    # Profile
    path('profile/',        views.spoc_profile,      name='spoc_profile'),

    # Mentor invitations (SPOC verifies mentors)
    path('mentors/',                         views.spoc_mentor_invitations, name='spoc_mentor_invitations'),
    path('mentors/<int:invite_id>/approve/', views.spoc_approve_mentor,    name='spoc_approve_mentor'),
    path('mentors/<int:invite_id>/reject/',  views.spoc_reject_mentor,     name='spoc_reject_mentor'),

    # Notifications
    path('notifications/', views.spoc_notifications, name='spoc_notifications'),
    path('notifications/read/', views.spoc_mark_notifications_read, name='spoc_mark_notifications_read'),
]
