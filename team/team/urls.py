"""team/urls.py"""
from django.urls import path
from . import views

urlpatterns = [
    path('',              views.team_landing,       name='team_landing'),
    path('register/',     views.team_register,      name='team_register'),
    path('login/',        views.team_login,          name='team_login'),
    path('login/otp/',    views.team_verify_otp,    name='team_verify_otp'),
    path('logout/',       views.team_logout,         name='team_logout'),
    path('dashboard/',    views.team_dashboard,      name='team_dashboard'),
    path('dashboard/add-travel/', views.team_add_travel, name='team_add_travel'),
    path('dashboard/send-message/', views.team_send_support_message, name='team_send_support_message'),
    path('details/',      views.team_details,        name='team_details'),
    path('communication/', views.team_communication, name='team_communication'),
    path('travel/',       views.team_travel,         name='team_travel'),
    path('content/',      views.team_content,        name='team_content'),
    path('announcements/', views.team_announcements, name='team_announcements'),
    path('results/',      views.team_results,        name='team_results'),
    path('memories/',     views.team_memories,       name='team_memories'),
    path('media/',        views.team_media,          name='team_media'),
    path('details/add-member/', views.team_add_member, name='team_add_member'),
    path('details/edit-member/<int:member_index>/', views.team_edit_member, name='team_edit_member'),
    path('mentor/',       views.team_invite_mentor,  name='team_invite_mentor'),
    path('submission/',   views.team_submission,     name='team_submission'),
    path('notifications/', views.team_notifications, name='team_notifications'),
    path('profile/',      views.team_profile,        name='team_profile'),
    path('resubmit/', views.team_resubmit_registration, name='team_resubmit_registration'),
    path('details/request-modification/', views.team_request_modification, name='team_request_modification'),
    path('details/complete-modification/', views.team_complete_modification, name='team_complete_modification'),
]
