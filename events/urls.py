"""
events/urls.py

Alias URL patterns that mirror /accounts/ routes for event-related views.
All URL names remain identical so existing template {% url %} tags work.
"""
from django.urls import path
from . import views

urlpatterns = [
    # Hackathons
    path('create-hackathon/', views.create_hackathon, name='create_hackathon'),
    path('edit-hackathon/<int:hackathon_id>/', views.edit_hackathon, name='edit_hackathon'),
    path('view-hackathon/<int:hackathon_id>/', views.view_hackathon, name='view_hackathon'),
    path('delete-hackathon/<int:hackathon_id>/', views.delete_hackathon, name='delete_hackathon'),
    path('hackathon/<int:hackathon_id>/round/<int:round_number>/toggle/', views.toggle_round_status, name='toggle_round_status'),
    path('launch-event/<int:hackathon_id>/', views.launch_event, name='launch_event'),

    # Problem Statements
    path('create-problem-statement/', views.create_problem_statement, name='create_problem_statement'),
    path('edit-problem-statement/<int:ps_id>/', views.edit_problem_statement, name='edit_problem_statement'),
    path('delete-problem-statement/<int:ps_id>/', views.delete_problem_statement, name='delete_problem_statement'),
    path('publish-problem-statement/<int:ps_id>/', views.publish_problem_statement, name='publish_problem_statement'),
    path('problem-statements/', views.public_problem_statements, name='public_problem_statements'),

    # Creative Materials
    path('create-creative/', views.create_creative_material, name='create_creative_material'),
    path('delete-creative/<int:creative_id>/', views.delete_creative_material, name='delete_creative_material'),
    path('suspend-creative/<int:creative_id>/', views.suspend_creative_material, name='suspend_creative_material'),
]
