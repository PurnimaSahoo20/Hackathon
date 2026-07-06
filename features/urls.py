"""
features/urls.py

Alias URL patterns that mirror /accounts/ routes for feature-related views.
All URL names remain identical so existing template {% url %} tags work.
"""
from django.urls import path
from . import views as feature_views

urlpatterns = [
    # ── FEATURE 1: SPOC ──
    path('spoc/', feature_views.spoc_college_management, name='spoc_college_management'),
    path('spoc/invite/', feature_views.send_spoc_invite, name='send_spoc_invite'),
    path('spoc/invite/bulk/', feature_views.send_bulk_spoc_invites, name='send_bulk_spoc_invites'),
    path('spoc/application/<int:invite_id>/', feature_views.view_spoc_invitation, name='view_spoc_invitation'),
    path('spoc/application/<int:invite_id>/edit/', feature_views.edit_spoc_invitation, name='edit_spoc_invitation'),
    path('spoc/approve/<int:invite_id>/', feature_views.approve_spoc_invitation, name='approve_spoc_invitation'),
    path('spoc/reject/<int:invite_id>/', feature_views.reject_spoc_invitation, name='reject_spoc_invitation'),
    path('spoc/suspend-application/<int:invite_id>/', feature_views.suspend_spoc_invitation, name='suspend_spoc_invitation'),
    path('spoc/view/<int:spoc_id>/', feature_views.view_spoc, name='view_spoc'),
    path('spoc/edit/<int:spoc_id>/', feature_views.edit_spoc, name='edit_spoc'),
    path('spoc/suspend/<int:spoc_id>/', feature_views.suspend_spoc, name='suspend_spoc'),

    # ── FEATURE 2: TEAM MONITORING ──
    path('teams/', feature_views.team_event_monitoring, name='team_event_monitoring'),
    path('teams/create/', feature_views.create_team, name='create_team'),
    path('teams/approve/<int:reg_id>/', feature_views.approve_team_registration, name='approve_team_registration'),
    path('teams/admin-approve/<int:team_id>/', feature_views.admin_approve_live_team, name='admin_approve_live_team'),
    path('teams/reject/<int:reg_id>/', feature_views.reject_team_registration, name='reject_team_registration'),
    path('teams/edit/<int:team_id>/', feature_views.edit_team, name='edit_team'),
    path('teams/suspend/<int:team_id>/', feature_views.suspend_team, name='suspend_team'),
    path('teams/update-status/<int:team_id>/', feature_views.update_team_status, name='update_team_status'),
    path('teams/upload-doc/<int:team_id>/', feature_views.upload_team_document, name='upload_team_document'),
    path('teams/delete-doc/<int:doc_id>/', feature_views.delete_team_document, name='delete_team_document'),

    # ── FEATURE 3: CONTENT MANAGEMENT ──
    path('content/', feature_views.content_management, name='content_management'),
    path('content/podcast/save/', feature_views.create_podcast, name='create_podcast'),
    path('content/podcast/delete/<int:podcast_id>/', feature_views.delete_podcast, name='delete_podcast'),
    path('content/podcast/suspend/<int:podcast_id>/', feature_views.suspend_podcast, name='suspend_podcast'),
    path('content/doc/save/', feature_views.create_documentation, name='create_documentation'),
    path('content/doc/delete/<int:doc_id>/', feature_views.delete_documentation, name='delete_documentation'),
    path('content/doc/suspend/<int:doc_id>/', feature_views.suspend_documentation, name='suspend_documentation'),
    path('content/ps/toggle/<int:ps_id>/', feature_views.toggle_ps_publish, name='toggle_ps_publish'),

    # ── FEATURE 4: VENUE & LOGISTICS ──
    path('venue/', feature_views.venue_logistics_management, name='venue_logistics_management'),
    path('venue/save/', feature_views.save_venue, name='save_venue'),
    path('venue/view/<int:venue_id>/', feature_views.view_venue, name='view_venue'),
    path('venue/suspend/<int:venue_id>/', feature_views.suspend_venue, name='suspend_venue'),
    path('venue/allocation/save/', feature_views.save_venue_allocation, name='save_venue_allocation'),
    path('venue/logistics/save/', feature_views.save_logistics, name='save_logistics'),
    path('venue/food/save/', feature_views.save_food_refreshment, name='save_food_refreshment'),
    path('venue/volunteers/save/', feature_views.save_volunteer, name='save_volunteer'),

    # ── FEATURE 5: FINANCIAL MANAGEMENT ──
    path('finance/', feature_views.finance_management, name='finance_management'),
    path('finance/budget/save/', feature_views.save_budget, name='save_budget'),
    path('finance/sponsorships/save/', feature_views.save_sponsorship, name='save_sponsorship'),
    path('finance/sponsorships/<int:sponsor_id>/delete/', feature_views.delete_sponsorship, name='delete_sponsorship'),
    path('finance/transactions/save/', feature_views.save_transaction, name='save_transaction'),
    path('support/', feature_views.support_operations_management, name='support_operations_management'),
    path('support/messages/<int:message_id>/update/', feature_views.update_support_message, name='update_support_message'),
    path('jury/', feature_views.jury_management, name='jury_management'),
    path('jury/invite-evaluator/', feature_views.send_evaluator_invite, name='send_evaluator_invite'),
    path('jury/invite-evaluator/bulk/', feature_views.send_bulk_evaluator_invites, name='send_bulk_evaluator_invites'),
    # ── Jury Onboarding (invitation flow) ──
    path('jury/invite/', feature_views.send_jury_invite, name='send_jury_invite'),
    path('jury/invite/bulk/', feature_views.send_bulk_jury_invites, name='send_bulk_jury_invites'),
    path('jury/register/<str:token>/', feature_views.jury_register_form, name='jury_register_form'),
    path('jury/invitation/<int:invite_id>/', feature_views.view_jury_invitation, name='view_jury_invitation'),
    path('jury/invitation/<int:invite_id>/edit/', feature_views.edit_jury_invitation, name='edit_jury_invitation'),
    path('jury/invitation/<int:invite_id>/approve/', feature_views.approve_jury_invitation, name='approve_jury_invitation'),
    path('jury/invitation/<int:invite_id>/reject/', feature_views.reject_jury_invitation, name='reject_jury_invitation'),
    path('jury/invitation/<int:invite_id>/suspend/', feature_views.suspend_jury_invitation, name='suspend_jury_invitation'),
    # ── Jury Member Profile management ──
    path('jury/member/<int:jury_id>/', feature_views.view_jury_member, name='view_jury_member'),
    path('jury/member/<int:jury_id>/edit/', feature_views.edit_jury_member, name='edit_jury_member'),
    path('jury/member/<int:jury_id>/send-testimonial/', feature_views.send_jury_testimonial_to_media, name='send_jury_testimonial_to_media'),
    path('jury/member/<int:jury_id>/toggle-status/', feature_views.toggle_jury_member_status, name='toggle_jury_member_status'),
    
# ── Expert Onboarding (invitation flow) ──
# ── Expert Onboarding (invitation flow) ──
    path('expert/invite/', feature_views.send_expert_invite, name='send_expert_invite'),
    path('expert/invite/bulk/', feature_views.send_bulk_expert_invites, name='send_bulk_expert_invites'),
    path('expert/register/<str:token>/', feature_views.expert_register_form, name='expert_register_form'),
    path('expert/invitation/<int:invite_id>/', feature_views.view_expert_invitation, name='view_expert_invitation'),
    path('expert/invitation/<int:invite_id>/edit/', feature_views.edit_expert_invitation, name='edit_expert_invitation'),
    path('expert/invitation/<int:invite_id>/approve/', feature_views.approve_expert_invitation, name='approve_expert_invitation'),
    path('expert/invitation/<int:invite_id>/reject/', feature_views.reject_expert_invitation, name='reject_expert_invitation'),
    path('expert/invitation/<int:invite_id>/suspend/', feature_views.suspend_expert_invitation, name='suspend_expert_invitation'),
    # ── Expert Member Profile management ──
    path('expert/member/<int:expert_id>/', feature_views.view_expert_member, name='view_expert_member'),
    path('expert/member/<int:expert_id>/edit/', feature_views.edit_expert_member, name='edit_expert_member'),
    path('expert/member/<int:expert_id>/send-testimonial/', feature_views.send_expert_testimonial_to_media, name='send_expert_testimonial_to_media'),
    path('expert/member/<int:expert_id>/toggle-status/', feature_views.toggle_expert_member_status, name='toggle_expert_member_status'),
    
# ── Evaluation parameters ──
    path('jury/save-parameter/', feature_views.save_marking_parameter, name='save_marking_parameter'),
    path('jury/parameters/<int:param_id>/delete/', feature_views.delete_marking_parameter, name='delete_marking_parameter'),
    path('jury/assign-evaluation/', feature_views.save_team_evaluation_assignment, name='save_team_evaluation_assignment'),
    path('media-comms/', feature_views.media_communications_management, name='media_communications_management'),
    path('media-comms/creatives/save/', feature_views.save_creative_asset, name='save_creative_asset'),
    path('media-comms/news/save/', feature_views.save_news_press_item, name='save_news_press_item'),
    path('media-comms/feeds/save/', feature_views.save_social_feed_item, name='save_social_feed_item'),
    path('media-comms/creatives/<int:creative_id>/toggle-status/', feature_views.toggle_creative_asset_status, name='toggle_creative_asset_status'),
    path('media-comms/creatives/<int:creative_id>/delete/', feature_views.delete_creative_asset, name='delete_creative_asset'),
    path('results-reporting/', feature_views.results_reporting_management, name='results_reporting_management'),

    # ── MENTOR ADMIN (Super Admin approves mentor invitations) ──
    path('mentors/', feature_views.mentor_invitations_admin, name='mentor_invitations_admin'),
    path('mentors/<int:invite_id>/approve/', feature_views.mentor_admin_approve, name='mentor_admin_approve'),
    path('mentors/<int:invite_id>/reject/',  feature_views.mentor_admin_reject,  name='mentor_admin_reject'),
]
