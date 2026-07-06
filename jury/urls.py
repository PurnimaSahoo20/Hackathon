"""
jury/urls.py

URL patterns for the Jury & Expert evaluator portal.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('', views.jury_dashboard, name='jury_dashboard'),
    path('evaluations/', views.jury_team_evaluations, name='jury_team_evaluations'),
    path('problem-statements/', views.jury_problem_statements, name='jury_problem_statements'),
    path('media-resources/', views.jury_media_resources, name='jury_media_resources'),
    path('travel/', views.jury_travel, name='jury_travel'),
    path('travel/add/', views.jury_add_travel, name='jury_add_travel'),
    path('communication/', views.jury_messages, name='jury_messages'),
    path('communication/<int:user_id>/', views.jury_conversation, name='jury_conversation'),
    path('profile/', views.jury_profile, name='jury_profile'),
    path('announcements/', views.jury_announcements, name='jury_announcements'),
    path('team/<int:team_id>/', views.jury_team_detail, name='jury_team_detail'),
    path('team/<int:team_id>/submit-marks/', views.jury_submit_marks, name='jury_submit_marks'),
]
