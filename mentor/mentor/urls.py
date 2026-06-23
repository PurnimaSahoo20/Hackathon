"""mentor/urls.py"""
from django.urls import path
from . import views

urlpatterns = [
    # Public accept-invite (no login)
    path('invite/<str:token>/', views.mentor_accept_invite, name='mentor_accept_invite'),

    # Auth
    path('login/',      views.mentor_login,      name='mentor_login'),
    path('login/otp/',  views.mentor_verify_otp, name='mentor_verify_otp'),
    path('logout/',     views.mentor_logout,     name='mentor_logout'),

    # Portal
    path('',              views.mentor_dashboard,    name='mentor_dashboard'),
    path('dashboard/',    views.mentor_dashboard,    name='mentor_dashboard'),
    path('teams/<int:team_id>/', views.mentor_team_detail, name='mentor_team_detail'),
    path('teams/<int:team_id>/ps/', views.mentor_team_problem_statement, name='mentor_team_problem_statement'),
    path('teams/<int:team_id>/resources/', views.mentor_team_resources, name='mentor_team_resources'),
    path('profile/',      views.mentor_profile,      name='mentor_profile'),
    path('messages/',     views.mentor_messages,     name='mentor_messages'),
    path('messages/<int:user_id>/', views.mentor_conversation, name='mentor_conversation'),
]
