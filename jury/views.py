"""
jury/views.py

Dashboard views for jury and expert evaluators.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.passwords import PORTAL_PASSWORD_HELP_TEXT, validate_portal_password
from events.models import CreativeMaterial, Hackathon, ProblemStatement, RoundMarkingParameter
from features.models import Documentation, Podcast, Team, TeamDocument, TeamEvaluationAssignment

from .models import EvaluatorProfile, EvaluatorTravelDetail, JuryMessage, TeamEvaluation

logger = logging.getLogger(__name__)


def _get_evaluator_role(user):
    """Returns 'jury', 'expert', or None."""
    if hasattr(user, 'jury_profile'):
        return 'jury'
    if hasattr(user, 'expert_profile'):
        return 'expert'
    return None


def _get_role_label(role):
    return 'Jury' if role == 'jury' else 'Expert'


def _get_contact_role_label(user):
    if hasattr(user, 'superadmin_profile'):
        return 'Super Admin'
    if hasattr(user, 'admin_profile'):
        return 'Admin'
    if hasattr(user, 'executive_profile'):
        return 'Executive'
    return user.role.name if user.role else 'Contact'


def _get_role_profile(user, role):
    return user.jury_profile if role == 'jury' else user.expert_profile


def _get_assigned_teams(user, role):
    """
    Fetch all TeamEvaluationAssignment rows where this user appears
    as any jury or expert slot, depending on role.
    """
    if role == 'jury':
        jury = user.jury_profile
        return TeamEvaluationAssignment.objects.filter(
            Q(jury_1=jury) | Q(jury_2=jury) | Q(jury_3=jury)
        ).select_related('team', 'team__hackathon', 'team__institution', 'team__team_leader')

    expert = user.expert_profile
    return TeamEvaluationAssignment.objects.filter(
        Q(expert_1=expert) | Q(expert_2=expert)
    ).select_related('team', 'team__hackathon', 'team__institution', 'team__team_leader')


def _count_evaluations(user, team, round_number, parameters):
    return TeamEvaluation.objects.filter(
        evaluator=user,
        team=team,
        round_number=round_number,
        parameter__in=parameters,
    ).count()


def _build_team_cards(user, role):
    assignments = _get_assigned_teams(user, role)
    team_cards = []
    total_evaluated = 0
    total_pending = 0

    for assignment in assignments:
        team = assignment.team
        hackathon = team.hackathon
        active_round = hackathon.get_active_round()
        round_number = active_round['number'] if active_round else assignment.round_number

        parameters = RoundMarkingParameter.objects.filter(
            hackathon=hackathon,
            round_number=round_number,
        )
        total_params = parameters.count()
        scored_params = _count_evaluations(user, team, round_number, parameters)
        is_complete = total_params > 0 and scored_params >= total_params

        if is_complete:
            total_evaluated += 1
        else:
            total_pending += 1

        doc_count = TeamDocument.objects.filter(team=team).count()
        team_cards.append({
            'assignment': assignment,
            'team': team,
            'team_name': team.team_name,
            'hackathon_name': hackathon.name,
            'round_number': round_number,
            'round_name': active_round['name'] if active_round else f"Round {round_number}",
            'total_params': total_params,
            'scored_params': scored_params,
            'is_complete': is_complete,
            'doc_count': doc_count,
            'progress_pct': int((scored_params / total_params) * 100) if total_params else 0,
        })

    team_cards.sort(key=lambda x: (x['is_complete'], x['team_name'].lower()))
    return team_cards, total_evaluated, total_pending


def _get_visible_hackathons(user, role):
    assignments = _get_assigned_teams(user, role)
    hackathon_ids = list(assignments.values_list('team__hackathon_id', flat=True).distinct())

    if hackathon_ids:
        return Hackathon.objects.filter(id__in=hackathon_ids).order_by('name')

    live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    if live_hackathon:
        return Hackathon.objects.filter(id=live_hackathon.id)
    return Hackathon.objects.none()


def _allowed_contact_map(user, role):
    """
    Allowed communication:
      - super admins
      - admins
      - executives
    """
    contact_map = {}

    admin_users = User.objects.filter(
        Q(is_superuser=True) |
        Q(superadmin_profile__isnull=False) |
        Q(admin_profile__isnull=False) |
        Q(executive_profile__isnull=False)
    ).exclude(id=user.id).distinct()
    for admin_user in admin_users:
        contact_type = 'super_admin' if hasattr(admin_user, 'superadmin_profile') else (
            'admin' if hasattr(admin_user, 'admin_profile') else 'executive'
        )
        contact_map.setdefault(admin_user.id, {
            'user': admin_user,
            'teams': [],
            'contact_type': contact_type,
            'role_label': _get_contact_role_label(admin_user),
        })

    return contact_map


def _build_conversation_list(user, role):
    contact_map = _allowed_contact_map(user, role)
    convo_ids = set(contact_map.keys())

    conversations = []
    for user_id in convo_ids:
        info = contact_map.get(user_id)
        other_user = info['user'] if info else User.objects.filter(id=user_id).first()
        if not other_user:
            continue
        last_message = JuryMessage.objects.filter(
            Q(sender=user, recipient=other_user) | Q(sender=other_user, recipient=user)
        ).order_by('-sent_at').first()
        unread_count = JuryMessage.objects.filter(
            sender=other_user,
            recipient=user,
            is_read=False,
        ).count()
        conversations.append({
            'user': other_user,
            'teams': (info or {}).get('teams', []),
            'contact_type': (info or {}).get('contact_type', 'other'),
            'role_label': (info or {}).get('role_label', _get_contact_role_label(other_user)),
            'last_message': last_message,
            'unread_count': unread_count,
        })

    conversations.sort(
        key=lambda item: item['last_message'].sent_at if item['last_message'] else user.date_joined,
        reverse=True
    )
    return conversations, contact_map


@login_required(login_url='/accounts/')
@never_cache
def jury_dashboard(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied. This area is for Jury and Expert members only.')
        return redirect('login')

    team_cards, total_evaluated, total_pending = _build_team_cards(request.user, role)
    conversations, _ = _build_conversation_list(request.user, role)
    evaluator_profile, _ = EvaluatorProfile.objects.get_or_create(user=request.user)

    live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    news_items = []
    if live_hackathon:
        news_prefixes = (
            ('[News]', 'news'),
            ('[Announcement]', 'announcement'),
        )
        documentation_links = Documentation.objects.filter(
            hackathon=live_hackathon,
            is_published=True,
        ).order_by('-created_at')
        for item in documentation_links:
            landing_sections = []
            if item.landing_sections:
                if isinstance(item.landing_sections, str):
                    landing_sections = [item.landing_sections]
                else:
                    landing_sections = list(item.landing_sections)
            
            raw_title = (item.title or '').strip()
            is_match = 'latest-news' in landing_sections or any(raw_title.startswith(prefix) for prefix in ('[News]', '[Announcement]'))
            if not is_match:
                continue

            news_type = None
            title = raw_title
            for prefix, mapped_type in news_prefixes:
                if raw_title.startswith(prefix):
                    news_type = mapped_type
                    title = raw_title[len(prefix):].strip(" |:-")
                    break
            if not news_type:
                news_type = 'news'
            
            summary = (item.description or '').strip()
            news_items.append({
                'item': item,
                'title': title or raw_title or item.title,
                'summary': summary,
                'link': item.external_url or (item.file.url if item.file else '#'),
                'type': news_type,
                'type_label': news_type.title(),
                'search_text': ' '.join([
                    raw_title,
                    summary,
                    news_type,
                    item.created_at.strftime('%d %b %Y %I:%M %p') if item.created_at else '',
                ]).lower(),
            })
            if len(news_items) >= 5:
                break

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'dashboard_title': f'{_get_role_label(role)} Dashboard',
        'team_cards': team_cards[:3],
        'total_assigned': len(team_cards),
        'total_evaluated': total_evaluated,
        'total_pending': total_pending,
        'live_hackathon': live_hackathon,
        'latest_conversations': conversations[:4],
        'evaluator_profile': evaluator_profile,
        'active_nav': 'jury_dashboard',
        'news_items': news_items,
    }
    return render(request, 'jury/dashboard.html', context)


@login_required(login_url='/accounts/')
@never_cache
def jury_announcements(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied. This area is for Jury and Expert members only.')
        return redirect('login')

    live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    news_items = []
    if live_hackathon:
        news_prefixes = (
            ('[News]', 'news'),
            ('[Announcement]', 'announcement'),
        )
        documentation_links = Documentation.objects.filter(
            hackathon=live_hackathon,
            is_published=True,
        ).order_by('-created_at')
        for item in documentation_links:
            landing_sections = []
            if item.landing_sections:
                if isinstance(item.landing_sections, str):
                    landing_sections = [item.landing_sections]
                else:
                    landing_sections = list(item.landing_sections)
            
            raw_title = (item.title or '').strip()
            is_match = 'latest-news' in landing_sections or any(raw_title.startswith(prefix) for prefix in ('[News]', '[Announcement]'))
            if not is_match:
                continue

            news_type = None
            title = raw_title
            for prefix, mapped_type in news_prefixes:
                if raw_title.startswith(prefix):
                    news_type = mapped_type
                    title = raw_title[len(prefix):].strip(" |:-")
                    break
            if not news_type:
                news_type = 'news'
            
            summary = (item.description or '').strip()
            news_items.append({
                'item': item,
                'title': title or raw_title or item.title,
                'summary': summary,
                'link': item.external_url or (item.file.url if item.file else '#'),
                'type': news_type,
                'type_label': news_type.title(),
                'search_text': ' '.join([
                    raw_title,
                    summary,
                    news_type,
                    item.created_at.strftime('%d %b %Y %I:%M %p') if item.created_at else '',
                ]).lower(),
            })

    rounds = live_hackathon.get_rounds() if live_hackathon else []

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'dashboard_title': f'{_get_role_label(role)} Announcements',
        'live_hackathon': live_hackathon,
        'news_items': news_items,
        'rounds': rounds,
        'active_nav': 'jury_announcements',
    }
    return render(request, 'jury/announcements.html', context)


@login_required(login_url='/accounts/')
@never_cache
def jury_team_evaluations(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied. This area is for Jury and Expert members only.')
        return redirect('login')

    team_cards, total_evaluated, total_pending = _build_team_cards(request.user, role)
    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'dashboard_title': f'{_get_role_label(role)} Team Evaluation',
        'team_cards': team_cards,
        'total_assigned': len(team_cards),
        'total_evaluated': total_evaluated,
        'total_pending': total_pending,
        'live_hackathon': Hackathon.objects.filter(status='Live').order_by('-updated_at').first(),
        'active_nav': 'jury_evaluations',
    }
    return render(request, 'jury/team_evaluations.html', context)


@login_required(login_url='/accounts/')
@never_cache
def jury_team_detail(request, team_id):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    team = get_object_or_404(Team, id=team_id)

    if role == 'jury':
        jury = request.user.jury_profile
        assignment = TeamEvaluationAssignment.objects.filter(team=team).filter(
            Q(jury_1=jury) | Q(jury_2=jury) | Q(jury_3=jury)
        ).first()
    else:
        expert = request.user.expert_profile
        assignment = TeamEvaluationAssignment.objects.filter(team=team).filter(
            Q(expert_1=expert) | Q(expert_2=expert)
        ).first()

    if not assignment:
        messages.error(request, 'You are not assigned to evaluate this team.')
        return redirect('jury_team_evaluations')

    hackathon = team.hackathon
    active_round = hackathon.get_active_round()
    round_number = active_round['number'] if active_round else assignment.round_number
    round_name = active_round['name'] if active_round else f"Round {round_number}"

    parameters = RoundMarkingParameter.objects.filter(
        hackathon=hackathon,
        round_number=round_number,
    ).order_by('id')

    existing_evals = TeamEvaluation.objects.filter(
        evaluator=request.user,
        team=team,
        round_number=round_number,
    ).select_related('parameter')
    existing_map = {ev.parameter_id: ev for ev in existing_evals}

    param_data = []
    for param in parameters:
        ev = existing_map.get(param.id)
        param_data.append({
            'param': param,
            'score': ev.score if ev else '',
            'remarks': ev.remarks if ev else '',
        })

    documents = TeamDocument.objects.filter(team=team).order_by('-uploaded_at')
    problem_statement = team.problem_statement
    problem_podcasts = Podcast.objects.filter(
        hackathon=hackathon,
        problem_statement=problem_statement,
        is_published=True,
        publication_scope='internal',
    ).order_by('-created_at') if problem_statement else Podcast.objects.none()
    problem_documentation = Documentation.objects.filter(
        hackathon=hackathon,
        problem_statement=problem_statement,
        is_published=True,
    ).order_by('-created_at') if problem_statement else Documentation.objects.none()
    all_scored = len(param_data) > 0 and all(p['score'] != '' for p in param_data)

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'team': team,
        'team_name': team.team_name,
        'show_institution': role != 'jury',
        'hackathon': hackathon,
        'assignment': assignment,
        'round_number': round_number,
        'round_name': round_name,
        'param_data': param_data,
        'documents': documents,
        'problem_statement': problem_statement,
        'problem_podcasts': problem_podcasts,
        'problem_documentation': problem_documentation,
        'all_scored': all_scored,
        'active_nav': 'jury_evaluations',
        'live_hackathon': Hackathon.objects.filter(status='Live').order_by('-updated_at').first(),
    }
    return render(request, 'jury/team_detail.html', context)


@login_required(login_url='/accounts/')
@never_cache
def jury_problem_statements(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    hackathons = _get_visible_hackathons(request.user, role)
    problem_statements = ProblemStatement.objects.filter(
        hackathon__in=hackathons,
        is_published=True,
        is_suspended=False,
    ).select_related('hackathon').order_by('hackathon__name', 'title')

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'problem_statements': problem_statements,
        'active_nav': 'jury_problem_statements',
    }
    return render(request, 'jury/problem_statements.html', context)


@login_required(login_url='/accounts/')
@never_cache
def jury_media_resources(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    hackathons = _get_visible_hackathons(request.user, role)
    podcasts = Podcast.objects.filter(
        hackathon__in=hackathons,
        is_published=True,
        publication_scope='internal',
    ).select_related('hackathon', 'problem_statement').order_by('-created_at')
    documentaries = Documentation.objects.filter(
        hackathon__in=hackathons,
        is_published=True,
    ).select_related('hackathon', 'problem_statement').order_by('-created_at')
    creatives = CreativeMaterial.objects.filter(
        hackathon__in=hackathons,
        is_published=True,
        is_suspended=False,
    ).select_related('hackathon').order_by('-uploaded_at')

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'podcasts': podcasts,
        'documentaries': documentaries,
        'creatives': creatives,
        'active_nav': 'jury_media_resources',
    }
    return render(request, 'jury/media_resources.html', context)


@login_required(login_url='/accounts/')
@require_POST
def jury_submit_marks(request, team_id):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    team = get_object_or_404(Team, id=team_id)

    if role == 'jury':
        jury = request.user.jury_profile
        assigned = TeamEvaluationAssignment.objects.filter(team=team).filter(
            Q(jury_1=jury) | Q(jury_2=jury) | Q(jury_3=jury)
        ).exists()
    else:
        expert = request.user.expert_profile
        assigned = TeamEvaluationAssignment.objects.filter(team=team).filter(
            Q(expert_1=expert) | Q(expert_2=expert)
        ).exists()

    if not assigned:
        messages.error(request, 'You are not assigned to evaluate this team.')
        return redirect('jury_team_evaluations')

    hackathon = team.hackathon
    active_round = hackathon.get_active_round()
    round_number = int(request.POST.get('round_number', 1))
    if active_round:
        round_number = active_round['number']

    parameters = RoundMarkingParameter.objects.filter(
        hackathon=hackathon,
        round_number=round_number,
    )

    saved_count = 0
    errors = []
    for param in parameters:
        score_raw = request.POST.get(f'score_{param.id}', '').strip()
        remarks = request.POST.get(f'remarks_{param.id}', '').strip()

        if not score_raw:
            continue

        try:
            score = float(score_raw)
            if score < 0:
                raise ValueError("Score cannot be negative.")
            if score > 100:
                raise ValueError("Score cannot be greater than 100.")
        except ValueError as exc:
            errors.append(f"'{param.name}': {exc}")
            continue

        TeamEvaluation.objects.update_or_create(
            team=team,
            round_number=round_number,
            evaluator=request.user,
            parameter=param,
            defaults={'score': score, 'remarks': remarks},
        )
        saved_count += 1

    if errors:
        messages.warning(request, f"Some scores were skipped: {'; '.join(errors)}")
    if saved_count > 0:
        messages.success(
            request,
            f"Marks saved successfully for {team.team_name} "
            f"({saved_count} parameter{'s' if saved_count != 1 else ''} scored)."
        )
    else:
        messages.info(request, "No scores were submitted. Please enter at least one score.")

    return redirect('jury_team_detail', team_id=team_id)


@login_required(login_url='/accounts/')
@never_cache
def jury_messages(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    conversations, contact_map = _build_conversation_list(request.user, role)
    available_contacts = sorted(
        contact_map.values(),
        key=lambda item: (
            0 if item['contact_type'] == 'super_admin' else 1 if item['contact_type'] == 'admin' else 2,
            (item['user'].get_full_name() or item['user'].username).lower(),
        )
    )

    selected_contact = None
    selected_thread = JuryMessage.objects.none()
    selected_user_id = request.GET.get('contact', '').strip()
    selected_contact_type = request.GET.get('contact_type', '').strip()

    if request.method == 'POST':
        selected_contact_type = request.POST.get('contact_type', '').strip()
        selected_user_id = request.POST.get('contact_user_id', '').strip()
        body = request.POST.get('body', '').strip()

        if not selected_user_id or not selected_user_id.isdigit():
            messages.error(request, 'Please select an admin contact.')
            return redirect('jury_messages')

        selected_contact = contact_map.get(int(selected_user_id))
        if not selected_contact:
            messages.error(request, 'You are not allowed to message this user.')
            return redirect('jury_messages')

        if not body:
            messages.error(request, 'Message cannot be empty.')
            return redirect(f"{request.path}?contact={selected_user_id}&contact_type={selected_contact_type}")

        JuryMessage.objects.create(
            sender=request.user,
            recipient=selected_contact['user'],
            body=body,
        )
        messages.success(request, 'Message sent.')
        return redirect(f"{request.path}?contact={selected_user_id}&contact_type={selected_contact_type}")

    filtered_contacts = available_contacts
    if selected_contact_type:
        filtered_contacts = [item for item in available_contacts if item['contact_type'] == selected_contact_type]

    if selected_user_id and selected_user_id.isdigit():
        selected_contact = contact_map.get(int(selected_user_id))
    if not selected_contact and filtered_contacts:
        selected_contact = filtered_contacts[0]
    if not selected_contact and available_contacts:
        selected_contact = available_contacts[0]

    if selected_contact:
        selected_thread = JuryMessage.objects.filter(
            sender__in=[request.user, selected_contact['user']],
            recipient__in=[request.user, selected_contact['user']],
        ).order_by('sent_at')
        JuryMessage.objects.filter(
            sender=selected_contact['user'],
            recipient=request.user,
            is_read=False,
        ).update(is_read=True)
        selected_user_id = str(selected_contact['user'].id)
        selected_contact_type = selected_contact['contact_type']

    contact_type_choices = [
        {'value': 'super_admin', 'label': 'Super Admin'},
        {'value': 'admin', 'label': 'Admin'},
        {'value': 'executive', 'label': 'Executive'},
    ]
    available_contact_types = [
        item for item in contact_type_choices
        if any(contact['contact_type'] == item['value'] for contact in available_contacts)
    ]

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'conversations': conversations,
        'available_contacts': available_contacts,
        'filtered_contacts': filtered_contacts,
        'available_contact_types': available_contact_types,
        'selected_contact': selected_contact,
        'selected_thread': selected_thread,
        'selected_contact_user_id': selected_user_id,
        'selected_contact_type': selected_contact_type,
        'active_nav': 'jury_messages',
    }
    return render(request, 'jury/messages.html', context)


@login_required(login_url='/accounts/')
@never_cache
def jury_conversation(request, user_id):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    _, contact_map = _build_conversation_list(request.user, role)
    other_user = get_object_or_404(User, id=user_id)
    if user_id not in contact_map:
        messages.error(request, 'You are not allowed to message this user.')
        return redirect('jury_messages')

    allowed_contact = contact_map[user_id]
    thread = JuryMessage.objects.filter(
        sender__in=[request.user, other_user],
        recipient__in=[request.user, other_user],
    ).select_related('team').order_by('sent_at')
    JuryMessage.objects.filter(
        sender=other_user,
        recipient=request.user,
        is_read=False,
    ).update(is_read=True)

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        team_id = request.POST.get('team_id', '').strip()
        if not body:
            messages.error(request, 'Message cannot be empty.')
            return redirect('jury_conversation', user_id=user_id)

        selected_team = None
        if team_id:
            selected_team = next((team for team in allowed_contact['teams'] if str(team.id) == team_id), None)
        elif allowed_contact['teams']:
            selected_team = allowed_contact['teams'][0]

        JuryMessage.objects.create(
            sender=request.user,
            recipient=other_user,
            team=selected_team,
            body=body,
        )
        messages.success(request, 'Message sent.')
        return redirect('jury_conversation', user_id=user_id)

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'other_user': other_user,
        'thread': thread,
        'contact_info': allowed_contact,
        'contact_role_label': allowed_contact.get('role_label', _get_contact_role_label(other_user)),
        'active_nav': 'jury_messages',
    }
    return render(request, 'jury/conversation.html', context)


@login_required(login_url='/accounts/')
@never_cache
def jury_profile(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    user = request.user
    role_profile = _get_role_profile(user, role)
    evaluator_profile, _ = EvaluatorProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile')

        if form_type == 'password':
            current_password = request.POST.get('current_password', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()

            if not current_password or not new_password or not confirm_password:
                messages.error(request, 'All password fields are required.')
            elif not user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New password and confirm password do not match.')
            else:
                try:
                    validate_portal_password(new_password, user)
                    user.set_password(new_password)
                    user.save(update_fields=['password'])
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Password changed successfully.')
                except Exception as exc:
                    for error in (getattr(exc, 'messages', None) or [str(exc)]):
                        messages.error(request, error)

        elif form_type == 'bank':
            evaluator_profile.bank_account_holder = request.POST.get('bank_account_holder', '').strip()
            evaluator_profile.bank_name = request.POST.get('bank_name', '').strip()
            evaluator_profile.branch_name = request.POST.get('branch_name', '').strip()
            evaluator_profile.account_number = request.POST.get('account_number', '').strip()
            evaluator_profile.ifsc_code = request.POST.get('ifsc_code', '').strip().upper()
            evaluator_profile.upi_id = request.POST.get('upi_id', '').strip()
            evaluator_profile.payment_notes = request.POST.get('payment_notes', '').strip()
            if request.FILES.get('cancelled_cheque'):
                evaluator_profile.cancelled_cheque = request.FILES['cancelled_cheque']
            evaluator_profile.save()
            messages.success(request, 'Bank details saved. Super admin can now review them for future payouts.')

        else:
            user.first_name = request.POST.get('first_name', user.first_name).strip()
            user.last_name = request.POST.get('last_name', user.last_name).strip()
            user.phone_number = request.POST.get('phone_number', user.phone_number or '').strip()
            if request.FILES.get('profile_image'):
                user.profile_image = request.FILES['profile_image']
            user.save()

            role_profile.domain = request.POST.get('domain', role_profile.domain or '').strip()
            role_profile.save()

            evaluator_profile.organization = request.POST.get('organization', '').strip()
            evaluator_profile.designation = request.POST.get('designation', '').strip()
            evaluator_profile.bio = request.POST.get('bio', '').strip()
            if request.FILES.get('testimonial_video'):
                evaluator_profile.testimonial_video = request.FILES['testimonial_video']
            evaluator_profile.save()
            messages.success(request, 'Profile updated.')

        return redirect('jury_profile')

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'role_profile': role_profile,
        'evaluator_profile': evaluator_profile,
        'password_help_text': PORTAL_PASSWORD_HELP_TEXT,
        'active_nav': 'jury_profile',
    }
    return render(request, 'jury/profile.html', context)


@login_required(login_url='/accounts/')
@require_POST
def jury_add_travel(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    origin = request.POST.get('origin', '').strip()
    destination = request.POST.get('destination', '').strip()
    journey_date = request.POST.get('journey_date', '').strip()
    travel_mode = request.POST.get('travel_mode', 'train').strip() or 'train'

    if not origin or not destination or not journey_date:
        messages.error(request, 'Please fill origin, destination, and journey date.')
        return redirect('jury_travel')

    ticket_amount_raw = request.POST.get('ticket_amount', '').strip()
    ticket_amount = None
    if ticket_amount_raw:
        try:
            ticket_amount = Decimal(ticket_amount_raw)
        except InvalidOperation:
            messages.error(request, 'Please enter a valid ticket amount.')
            return redirect('jury_travel')

    EvaluatorTravelDetail.objects.create(
        user=request.user,
        origin=origin,
        destination=destination,
        journey_date=journey_date,
        travel_mode=travel_mode,
        traveler_name=request.POST.get('traveler_name', '').strip(),
        ticket_number=request.POST.get('ticket_number', '').strip(),
        ticket_amount=ticket_amount,
        notes=request.POST.get('notes', '').strip(),
        ticket_file=request.FILES.get('ticket_file'),
    )
    messages.success(request, 'Travel details added successfully.')
    return redirect('jury_travel')


@login_required(login_url='/accounts/')
@never_cache
def jury_travel(request):
    role = _get_evaluator_role(request.user)
    if not role:
        messages.error(request, 'Access denied.')
        return redirect('login')

    context = {
        'role': role,
        'role_label': _get_role_label(role),
        'travel_details': EvaluatorTravelDetail.objects.filter(user=request.user),
        'active_nav': 'jury_travel',
        'live_hackathon': Hackathon.objects.filter(status='Live').order_by('-updated_at').first(),
    }
    return render(request, 'jury/travel.html', context)
