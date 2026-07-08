
import logging
from collections import defaultdict
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.db.models import Count, Q, Sum, Value, IntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.models import User, Role, SuperadminProfile, AdminProfile
from accounts.rendering import render_route
from events.models import (
    Hackathon, HackathonDomain, ProblemStatement, CreativeMaterial,
    RoundMarkingParameter, HeroBannerImage,
    LANDING_SECTION_CHOICES, LANDING_SECTION_LABELS,
)
from features.models import Team, Venue, SponsorshipFund, Podcast

def _superadmin_required(request):
    return (
        request.user.is_authenticated and
        (request.user.is_superuser or
         (request.user.role and request.user.role.name in ('Super Admin', 'Admin')))
    )


def _can_manage_events(request):
    return _superadmin_required(request)


def _round_enabled_from_post(request, round_number):
    return request.POST.get(f'round_{round_number}_is_enabled') == 'on'


def _clean_landing_sections(raw_sections):
    allowed = {value for value, _ in LANDING_SECTION_CHOICES}
    cleaned = []
    for section in raw_sections or []:
        section = (section or '').strip()
        if section in allowed and section not in cleaned:
            cleaned.append(section)
    return cleaned


def _landing_sections_from_value(value):
    if not value:
        return []
    if isinstance(value, str):
        raw_sections = [value]
    else:
        raw_sections = list(value)
    cleaned = []
    for section in raw_sections:
        section = (section or '').strip()
        if section and section not in cleaned:
            cleaned.append(section)
    return cleaned


def _item_matches_landing_section(item, section_name, *, default_match=False, legacy_prefixes=()):
    landing_sections = _landing_sections_from_value(getattr(item, 'landing_sections', []))
    if landing_sections:
        return section_name in landing_sections
    title = (getattr(item, 'title', '') or '')
    return default_match or any(title.startswith(prefix) for prefix in legacy_prefixes)


def _safe_media_url(file_field):
    if not file_field:
        return ''
    try:
        return file_field.url
    except Exception:
        return ''


def _normalise_lookup(value):
    return ' '.join((value or '').split()).strip().lower()


def _safe_file_url(file_field):
    if not file_field:
        return ''
    try:
        return file_field.url
    except Exception:
        return ''


def _build_public_problem_statement_context(active_hackathon):
    problem_queryset = ProblemStatement.objects.filter(
        is_published=True,
        is_suspended=False,
    ).select_related('hackathon').order_by('domain', 'title')
    if active_hackathon:
        scoped_problems = problem_queryset.filter(hackathon=active_hackathon)
        published_problems = scoped_problems if scoped_problems.exists() else problem_queryset
    else:
        published_problems = problem_queryset

    public_podcast_queryset = Podcast.objects.filter(
        is_published=True,
        publication_scope='website',
    ).select_related('hackathon', 'problem_statement').order_by('-created_at')
    if active_hackathon:
        scoped_podcasts = public_podcast_queryset.filter(hackathon=active_hackathon)
        public_podcasts = scoped_podcasts if scoped_podcasts.exists() else public_podcast_queryset
    else:
        public_podcasts = public_podcast_queryset

    podcast_map = defaultdict(list)
    for podcast in public_podcasts:
        problem_id = podcast.problem_statement_id
        if not problem_id:
            continue
        podcast_map[problem_id].append({
            'title': podcast.title,
            'description': podcast.description or '',
            'url': podcast.video_url or _safe_file_url(podcast.video_file),
        })

    # Default color palette for auto-assigned domain colors
    _default_colors = ['#fefce8', '#dbeafe', '#fdf2f8', '#fdf4ff', '#ecfdf5', '#fff7ed', '#f0fdf4', '#fef2f2']
    _default_icons = ['🌾', '🏥', '🐾', '📚', '💻', '🔬', '🌍', '⚡']

    # Try to load dynamic domains from HackathonDomain model
    dynamic_domains = []
    if active_hackathon:
        dynamic_domains = list(HackathonDomain.objects.filter(hackathon=active_hackathon).order_by('display_order', 'name'))

    if dynamic_domains:
        # Build track_specs from dynamic HackathonDomain entries
        domain_mappings = {
            'agriculture': {
                'badge': 'SDG - 12',
                'image': '/media/creatives/hero2.jpg',
            },
            'healthcare': {
                'badge': 'SDG - 3',
                'image': '/media/creatives/hero1-bg.jpg',
            },
            'animal': {
                'badge': 'SDG - 12',
                'image': '/media/creatives/hero4.jpg',
            },
            'vet': {
                'badge': 'SDG - 12',
                'image': '/media/creatives/hero4.jpg',
            },
            'education': {
                'badge': 'SDG - 4',
                'image': '/media/creatives/hero3.jpg',
            },
            'learn': {
                'badge': 'SDG - 4',
                'image': '/media/creatives/hero3.jpg',
            },
        }
        _default_images = [
            '/media/creatives/hero2.jpg',
            '/media/creatives/hero1-bg.jpg',
            '/media/creatives/hero4.jpg',
            '/media/creatives/hero3.jpg'
        ]
        _default_badges = ['SDG - 12', 'SDG - 3', 'SDG - 12', 'SDG - 4']

        track_specs = []
        for idx, domain in enumerate(dynamic_domains):
            name_lower = domain.name.lower()
            matched_badge = None
            matched_image = None
            for key, val in domain_mappings.items():
                if key in name_lower:
                    matched_badge = val['badge']
                    matched_image = val['image']
                    break
            
            badge_val = getattr(domain, 'badge', None) or matched_badge or _default_badges[idx % len(_default_badges)]
            image_val = getattr(domain, 'image', None) or matched_image or _default_images[idx % len(_default_images)]

            track_specs.append({
                'slug': domain.slug or name_lower.replace(' ', '-'),
                'title': domain.name,
                'badge': badge_val,
                'icon': domain.icon or _default_icons[idx % len(_default_icons)],
                'color': domain.color or _default_colors[idx % len(_default_colors)],
                'subtitle': domain.subtitle or f'Problem statements in {domain.name}',
                'image': image_val,
                'keywords': [name_lower],
            })
    else:
        # Fallback: hardcoded track specs
        track_specs = [
            {
                'slug': 'agriculture',
                'title': 'Agriculture',
                'badge': 'SDG - 12',
                'icon': '🌾',
                'color': '#fefce8',
                'subtitle': 'Crops, rural innovation, and farm sustainability',
                'image': '/media/creatives/hero2.jpg',
                'keywords': ['agri', 'agriculture', 'farm', 'crop', 'rural', 'soil', 'harvest', 'livestock'],
            },
            {
                'slug': 'healthcare',
                'title': 'Healthcare',
                'badge': 'SDG - 3',
                'icon': '🏥',
                'color': '#dbeafe',
                'subtitle': 'Medical care, public health, and wellness systems',
                'image': '/media/creatives/hero1-bg.jpg',
                'keywords': ['health', 'healthcare', 'medical', 'med', 'clinic', 'hospital', 'patient'],
            },
            {
                'slug': 'animal-resource',
                'title': 'Animal Resource',
                'badge': 'SDG - 12',
                'icon': '🐾',
                'color': '#fdf2f8',
                'subtitle': 'Livestock, veterinary, and animal systems',
                'image': '/media/creatives/hero4.jpg',
                'keywords': ['animal', 'veterinary', 'livestock', 'dairy', 'poultry', 'cattle', 'pet'],
            },
            {
                'slug': 'education',
                'title': 'Education',
                'badge': 'SDG - 4',
                'icon': '📚',
                'color': '#fdf4ff',
                'subtitle': 'Learning, inclusion, and skill development',
                'image': '/media/creatives/hero3.jpg',
                'keywords': ['education', 'learning', 'school', 'college', 'student', 'teaching', 'ed'],
            },
        ]

    grouped_problem_map = {
        spec['title']: {
            'slug': spec['slug'],
            'title': spec['title'],
            'badge': spec.get('badge', spec['title']),
            'icon': spec['icon'],
            'color': spec['color'],
            'subtitle': spec['subtitle'],
            'image': spec['image'],
            'count': 0,
            'problems': [],
        }
        for spec in track_specs
    }
    grouped_problem_map['Other'] = {
        'slug': 'other',
        'title': 'Other',
        'icon': '🧩',
        'color': '#eef2ff',
        'subtitle': 'Published problem statements that do not match the main showcase tracks',
        'image': '/media/creatives/front-page.jpg',
        'count': 0,
        'problems': [],
    }

    def _matches_track(problem, keywords):
        haystack = ' '.join(filter(None, [problem.domain, problem.title, problem.description])).lower()
        return any(keyword in haystack for keyword in keywords)

    for problem in published_problems:
        matched = False
        domain_text = (problem.domain or '').strip().lower()
        for spec in track_specs:
            # Match by exact domain name first, then by keywords
            if domain_text == spec['title'].lower() or _matches_track(problem, spec['keywords']):
                entry = grouped_problem_map[spec['title']]
                entry['count'] += 1
                entry['problems'].append({
                    'id': f'PS-{problem.id}',
                    'title': problem.title,
                    'slug': f'ps-{problem.id}',
                    'desc': problem.description or 'Detailed problem brief will be available after login.',
                    'domain_label': entry['title'],
                    'pdf_url': _safe_file_url(problem.pdf_file),
                    'podcasts': podcast_map.get(problem.id, []),
                })
                matched = True
                break
        if not matched:
            entry = grouped_problem_map['Other']
            entry['count'] += 1
            entry['problems'].append({
                'id': f'PS-{problem.id}',
                'title': problem.title,
                'slug': f'ps-{problem.id}',
                'desc': problem.description or 'Detailed problem brief will be available after login.',
                'domain_label': entry['title'],
                'pdf_url': _safe_file_url(problem.pdf_file),
                'podcasts': podcast_map.get(problem.id, []),
            })

    track_domains = list(grouped_problem_map.values())
    ps_modal_data = {
        track['slug']: {
            'icon': track['icon'],
            'color': track['color'],
            'title': track['title'],
            'subtitle': track['subtitle'],
            'problems': track['problems'],
        }
        for track in track_domains
    }

    return {
        'published_problems': published_problems,
        'total_problem_statements': published_problems.count(),
        'themes_count': published_problems.exclude(domain__isnull=True).exclude(domain__exact='').values('domain').distinct().count(),
        'track_domains': track_domains,
        'ps_modal_data': ps_modal_data,
        'problem_statement_groups': track_domains,
        'public_podcasts': public_podcasts,
    }



def _resolve_problem_domain_filter(problem_groups, selected_domain):
    selected = _normalise_lookup(selected_domain)
    if not selected or selected == 'all':
        return problem_groups

    filtered_groups = []
    for group in problem_groups:
        group_slug = _normalise_lookup(group.get('slug'))
        group_title = _normalise_lookup(group.get('title'))
        if selected in (group_slug, group_title):
            filtered_groups.append(group)
    return filtered_groups


def create_hackathon(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        organization_name = request.POST.get('organization_name')
        organization_logo = request.FILES.get('organization_logo')
        event_logo = request.FILES.get('event_logo')
        platform_logo = request.FILES.get('platform_logo')
        hero_banner = request.FILES.get('hero_banner')
        approval_date = request.POST.get('approval_date') or None
        approval_letter = request.FILES.get('approval_letter')
        poster_launching_date = request.POST.get('poster_launching_date') or None
        website_launching_date = request.POST.get('website_launching_date') or None
        min_team_size = request.POST.get('min_team_size', 1)
        max_team_size = request.POST.get('max_team_size', 4)
        number_of_mentors = request.POST.get('number_of_mentors', 0)
        total_team_members = request.POST.get('total_team_members') or max_team_size
        number_of_rounds = request.POST.get('number_of_rounds', 1)
        registration_open = request.POST.get('registration_open') or None
        registration_close = request.POST.get('registration_close') or None
        round_1_name = request.POST.get('round_1_name', 'Round 1')
        round_1_start_date = request.POST.get('round_1_start_date') or None
        round_1_end_date = request.POST.get('round_1_end_date') or None
        round_1_is_enabled = _round_enabled_from_post(request, 1)
        round_1_type = request.POST.get('round_1_type', 'Online')
        round_1_venue = request.POST.get('round_1_venue', '') or None
        round_2_name = request.POST.get('round_2_name', 'Round 2')
        round_2_start_date = request.POST.get('round_2_start_date') or None
        round_2_end_date = request.POST.get('round_2_end_date') or None
        round_2_is_enabled = _round_enabled_from_post(request, 2)
        round_2_type = request.POST.get('round_2_type', 'Online')
        round_2_venue = request.POST.get('round_2_venue', '') or None
        round_3_name = request.POST.get('round_3_name', 'Round 3')
        round_3_start_date = request.POST.get('round_3_start_date') or None
        round_3_end_date = request.POST.get('round_3_end_date') or None
        round_3_is_enabled = _round_enabled_from_post(request, 3)
        round_3_type = request.POST.get('round_3_type', 'Online')
        round_3_venue = request.POST.get('round_3_venue', '') or None
        round_4_name = request.POST.get('round_4_name', 'Round 4')
        round_4_start_date = request.POST.get('round_4_start_date') or None
        round_4_end_date = request.POST.get('round_4_end_date') or None
        round_4_is_enabled = _round_enabled_from_post(request, 4)
        round_4_type = request.POST.get('round_4_type', 'Online')
        round_4_venue = request.POST.get('round_4_venue', '') or None
        round_5_name = request.POST.get('round_5_name', 'Round 5')
        round_5_start_date = request.POST.get('round_5_start_date') or None
        round_5_end_date = request.POST.get('round_5_end_date') or None
        round_5_is_enabled = _round_enabled_from_post(request, 5)
        round_5_type = request.POST.get('round_5_type', 'Online')
        round_5_venue = request.POST.get('round_5_venue', '') or None
        status = request.POST.get('status', 'Draft')

        try:
            superadmin, _ = SuperadminProfile.objects.get_or_create(user=request.user)
            hackathon = Hackathon.objects.create(
                name=name, organization_name=organization_name,
                organization_logo=organization_logo, created_by=superadmin,
                event_logo=event_logo, platform_logo=platform_logo,
                hero_banner=hero_banner,
                approval_date=approval_date, approval_letter=approval_letter,
                poster_launching_date=poster_launching_date,
                website_launching_date=website_launching_date,
                min_team_size=min_team_size, max_team_size=max_team_size,
                number_of_mentors=number_of_mentors, total_team_members=total_team_members,
                number_of_rounds=number_of_rounds,
                registration_open=registration_open, registration_close=registration_close,
                round_1_name=round_1_name, round_1_start_date=round_1_start_date,
                round_1_end_date=round_1_end_date, round_1_is_enabled=round_1_is_enabled,
                round_1_type=round_1_type, round_1_venue=round_1_venue,
                round_2_name=round_2_name, round_2_start_date=round_2_start_date,
                round_2_end_date=round_2_end_date, round_2_is_enabled=round_2_is_enabled,
                round_2_type=round_2_type, round_2_venue=round_2_venue,
                round_3_name=round_3_name, round_3_start_date=round_3_start_date,
                round_3_end_date=round_3_end_date, round_3_is_enabled=round_3_is_enabled,
                round_3_type=round_3_type, round_3_venue=round_3_venue,
                round_4_name=round_4_name, round_4_start_date=round_4_start_date,
                round_4_end_date=round_4_end_date, round_4_is_enabled=round_4_is_enabled,
                round_4_type=round_4_type, round_4_venue=round_4_venue,
                round_5_name=round_5_name, round_5_start_date=round_5_start_date,
                round_5_end_date=round_5_end_date, round_5_is_enabled=round_5_is_enabled,
                round_5_type=round_5_type, round_5_venue=round_5_venue,
                status=status
            )
            
            for i in range(1, 6):
                try:
                    num_params = int(request.POST.get(f'round_{i}_num_params', 0))
                except ValueError:
                    num_params = 0
                for j in range(1, num_params + 1):
                    param_name = request.POST.get(f'round_{i}_param_{j}_name')
                    cutoff_val = request.POST.get(f'round_{i}_param_{j}_cutoff') or 0.00
                    if param_name:
                        RoundMarkingParameter.objects.create(
                            hackathon=hackathon, round_number=i, name=param_name, cutoff_score=cutoff_val
                        )
                if request.POST.get(f'round_{i}_has_others') == 'on':
                    RoundMarkingParameter.objects.create(
                        hackathon=hackathon, round_number=i, name="Others", is_others=True
                    )

            # Save dynamic PS domains
            try:
                num_domains = int(request.POST.get('num_domains', 0))
            except ValueError:
                num_domains = 0
            for d in range(1, num_domains + 1):
                domain_name = (request.POST.get(f'domain_{d}_name') or '').strip()
                if domain_name:
                    HackathonDomain.objects.create(
                        hackathon=hackathon,
                        name=domain_name,
                        display_order=d,
                    )

            # Save multiple hero banner images
            hero_banner_files = request.FILES.getlist('hero_banners')
            for idx, banner_file in enumerate(hero_banner_files):
                HeroBannerImage.objects.create(
                    hackathon=hackathon,
                    image=banner_file,
                    display_order=idx + 1,
                )
            
            messages.success(request, f'Hackathon {name} created successfully.')
        except Exception as e:
            messages.error(request, f'Error creating hackathon: {e}')

    return redirect('/accounts/dashboard/?tab=events')


def edit_hackathon(request, hackathon_id):
    try:
        hackathon = Hackathon.objects.get(id=hackathon_id)
    except Hackathon.DoesNotExist:
        messages.error(request, 'Hackathon not found.')
        return redirect('/accounts/dashboard/?tab=events')

    if request.method == 'POST':
        hackathon.name = request.POST.get('name', hackathon.name)
        hackathon.organization_name = request.POST.get('organization_name', hackathon.organization_name)
        if 'organization_logo' in request.FILES:
            hackathon.organization_logo = request.FILES['organization_logo']
        if 'event_logo' in request.FILES:
            hackathon.event_logo = request.FILES['event_logo']
        if 'platform_logo' in request.FILES:
            hackathon.platform_logo = request.FILES['platform_logo']
        if 'hero_banner' in request.FILES:
            hackathon.hero_banner = request.FILES['hero_banner']
        hackathon.min_team_size = request.POST.get('min_team_size', hackathon.min_team_size)
        hackathon.max_team_size = request.POST.get('max_team_size', hackathon.max_team_size)
        hackathon.number_of_mentors = request.POST.get('number_of_mentors', hackathon.number_of_mentors)
        total_val = request.POST.get('total_team_members')
        hackathon.total_team_members = total_val if total_val else hackathon.max_team_size
        hackathon.number_of_rounds = request.POST.get('number_of_rounds', hackathon.number_of_rounds)

        for field in ['approval_date', 'poster_launching_date', 'website_launching_date',
                      'registration_open', 'registration_close']:
            val = request.POST.get(field)
            if val:
                setattr(hackathon, field, val)

        if 'approval_letter' in request.FILES:
            hackathon.approval_letter = request.FILES['approval_letter']

        for i in range(1, 6):
            name_val = request.POST.get(f'round_{i}_name')
            if name_val:
                setattr(hackathon, f'round_{i}_name', name_val)
            for suffix in ['start_date', 'end_date']:
                val = request.POST.get(f'round_{i}_{suffix}')
                setattr(hackathon, f'round_{i}_{suffix}', val or None)
            setattr(hackathon, f'round_{i}_is_enabled', _round_enabled_from_post(request, i))
            rtype = request.POST.get(f'round_{i}_type', 'Online')
            setattr(hackathon, f'round_{i}_type', rtype)
            rvenue = request.POST.get(f'round_{i}_venue', '') or None
            setattr(hackathon, f'round_{i}_venue', rvenue)

        status = request.POST.get('status')
        if status:
            hackathon.status = status

        try:
            hackathon.save()
            
            hackathon.marking_parameters.all().delete()
            for i in range(1, 6):
                try:
                    num_params = int(request.POST.get(f'round_{i}_num_params', 0))
                except ValueError:
                    num_params = 0
                for j in range(1, num_params + 1):
                    param_name = request.POST.get(f'round_{i}_param_{j}_name')
                    cutoff_val = request.POST.get(f'round_{i}_param_{j}_cutoff') or 0.00
                    if param_name:
                        RoundMarkingParameter.objects.create(
                            hackathon=hackathon, round_number=i, name=param_name, cutoff_score=cutoff_val
                        )
                if request.POST.get(f'round_{i}_has_others') == 'on':
                    RoundMarkingParameter.objects.create(
                        hackathon=hackathon, round_number=i, name="Others", is_others=True
                    )

            # Re-create dynamic PS domains
            hackathon.domains.all().delete()
            try:
                num_domains = int(request.POST.get('num_domains', 0))
            except ValueError:
                num_domains = 0
            for d in range(1, num_domains + 1):
                domain_name = (request.POST.get(f'domain_{d}_name') or '').strip()
                if domain_name:
                    HackathonDomain.objects.create(
                        hackathon=hackathon,
                        name=domain_name,
                        display_order=d,
                    )

            # Handle hero banner deletions
            delete_banner_ids = request.POST.getlist('delete_banner')
            if delete_banner_ids:
                hackathon.hero_banners.filter(id__in=delete_banner_ids).delete()

            # Handle new hero banner uploads
            new_banners = request.FILES.getlist('hero_banners')
            if new_banners:
                max_order = hackathon.hero_banners.order_by('-display_order').values_list('display_order', flat=True).first() or 0
                for idx, banner_file in enumerate(new_banners):
                    HeroBannerImage.objects.create(
                        hackathon=hackathon,
                        image=banner_file,
                        display_order=max_order + idx + 1,
                    )
                    
            messages.success(request, f'Hackathon {hackathon.name} updated successfully.')
            return redirect('/accounts/dashboard/?tab=events')
        except Exception as e:
            messages.error(request, f'Error updating hackathon: {e}')

    round_params = {}
    for i in range(1, 6):
        params = hackathon.marking_parameters.filter(round_number=i)
        normal_params = params.filter(is_others=False)
        has_others = params.filter(is_others=True).exists()
        round_params[i] = {
            'params': normal_params,
            'count': normal_params.count(),
            'has_others': has_others
        }

    existing_domains = list(hackathon.domains.order_by('display_order'))

    existing_banners = list(hackathon.hero_banners.order_by('display_order'))

    return render(request, 'events/edit_hackathon.html', {
        'hackathon': hackathon,
        'round_params': round_params,
        'existing_domains': existing_domains,
        'existing_banners': existing_banners,
    })


def toggle_round_status(request, hackathon_id, round_number):
    if request.method != 'POST':
        return redirect('/accounts/dashboard/?tab=events')
    if not _can_manage_events(request):
        messages.error(request, "Access denied.")
        return redirect('/accounts/dashboard/')
    if round_number < 1 or round_number > 5:
        messages.error(request, "Invalid round.")
        return redirect('/accounts/dashboard/?tab=events')

    try:
        hackathon = Hackathon.objects.get(id=hackathon_id)
        field_name = f'round_{round_number}_is_enabled'
        next_status = not getattr(hackathon, field_name)
        setattr(hackathon, field_name, next_status)
        hackathon.save(update_fields=[field_name, 'updated_at'])
        word = "activated" if next_status else "deactivated"
        messages.success(request, f"{getattr(hackathon, f'round_{round_number}_name')} {word}.")
    except Hackathon.DoesNotExist:
        messages.error(request, 'Hackathon not found.')

    return redirect(request.META.get('HTTP_REFERER', '/accounts/dashboard/?tab=events'))


def delete_hackathon(request, hackathon_id):
    if request.method == 'POST':
        try:
            hackathon = Hackathon.objects.get(id=hackathon_id)
            hackathon.status = 'Suspended'
            hackathon.save()
            messages.success(request, f'Hackathon {hackathon.name} has been suspended.')
        except Hackathon.DoesNotExist:
            messages.error(request, 'Hackathon not found.')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return redirect('/accounts/dashboard/?tab=events')


def view_hackathon(request, hackathon_id):
    try:
        hackathon = Hackathon.objects.get(id=hackathon_id)
        return render(request, 'events/view_hackathon.html', {
            'hackathon': hackathon,
            'active_nav': 'events',
        })
    except Hackathon.DoesNotExist:
        messages.error(request, 'Hackathon not found.')
        return redirect('/accounts/dashboard/?tab=events')


def create_problem_statement(request):
    if request.method == 'POST':
        ps_id = request.POST.get('ps_id')
        hackathon_id = request.POST.get('hackathon')
        title = request.POST.get('title')
        domain = request.POST.get('domain', '')
        description = request.POST.get('description', '')
        pdf_file = request.FILES.get('pdf_file')
        action = request.POST.get('action')
        landing_sections = _clean_landing_sections(request.POST.getlist('landing_sections'))

        try:
            hackathon = Hackathon.objects.get(id=hackathon_id)
            if ps_id:
                ps = ProblemStatement.objects.get(id=ps_id)
                ps.hackathon = hackathon
                ps.title = title
                ps.domain = domain
                ps.description = description
                ps.landing_sections = landing_sections
                if pdf_file:
                    ps.pdf_file = pdf_file
                if action == 'publish':
                    ps.is_published = True
                ps.save()
                messages.success(request, f'Problem statement "{title}" updated.')
            else:
                ps = ProblemStatement.objects.create(
                    hackathon=hackathon, title=title, domain=domain,
                    description=description, is_published=(action == 'publish'),
                    landing_sections=landing_sections,
                )
                if pdf_file:
                    ps.pdf_file = pdf_file
                    ps.save()
                status_text = "published" if ps.is_published else "saved as draft"
                messages.success(request, f'Problem statement "{title}" {status_text}.')
        except Hackathon.DoesNotExist:
            messages.error(request, 'Selected hackathon not found.')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return redirect('/accounts/dashboard/?tab=problem_statements')


def edit_problem_statement(request, ps_id):
    try:
        ps = ProblemStatement.objects.get(id=ps_id)
        if ps.is_published:
            messages.warning(request, 'Published problem statements cannot be edited.')
            return redirect('/accounts/dashboard/?tab=problem_statements')

        if request.method == 'POST':
            ps.title = request.POST.get('title')
            ps.domain = request.POST.get('domain')
            ps.description = request.POST.get('description')
            ps.hackathon_id = request.POST.get('hackathon_id')
            if 'pdf_file' in request.FILES:
                ps.pdf_file = request.FILES['pdf_file']
            ps.save()
            messages.success(request, 'Problem statement updated.')
            return redirect('/accounts/dashboard/?tab=problem_statements')

        hackathons = Hackathon.objects.filter(status='Live').order_by('-created_at')
        return render(request, 'events/edit_problem_statement.html', {
            'ps': ps, 'hackathons': hackathons, 'active_nav': 'events',
        })
    except ProblemStatement.DoesNotExist:
        messages.error(request, 'Problem statement not found.')
        return redirect('/accounts/dashboard/?tab=problem_statements')


def delete_problem_statement(request, ps_id):
    if request.method == 'POST':
        try:
            ps = ProblemStatement.objects.get(id=ps_id)
            if ps.is_published:
                messages.error(request, 'Published problem statements cannot be suspended.')
            else:
                ps.is_suspended = True
                ps.save()
                messages.success(request, 'Problem statement suspended.')
        except ProblemStatement.DoesNotExist:
            messages.error(request, 'Problem statement not found.')
    return redirect('/accounts/dashboard/?tab=problem_statements')


def publish_problem_statement(request, ps_id):
    if request.method == 'POST':
        try:
            ps = ProblemStatement.objects.get(id=ps_id)
            ps.is_published = True
            ps.save()
            messages.success(request, f'Problem statement "{ps.title}" published.')
        except ProblemStatement.DoesNotExist:
            messages.error(request, 'Problem statement not found.')
    return redirect('/accounts/dashboard/?tab=problem_statements')


def create_creative_material(request):
    if request.method == 'POST':
        hackathon_id = request.POST.get('hackathon_id')
        title = request.POST.get('title')
        file = request.FILES.get('file')
        action = request.POST.get('action')
        creative_id = request.POST.get('creative_id')
        landing_sections = _clean_landing_sections(request.POST.getlist('landing_sections'))

        try:
            hackathon = Hackathon.objects.get(id=hackathon_id)
            if creative_id:
                creative = CreativeMaterial.objects.get(id=creative_id)
                creative.hackathon = hackathon
                creative.title = title
                creative.is_published = (action == 'publish')
                creative.landing_sections = landing_sections
                if file:
                    creative.file = file
                creative.save()
                verb = "updated"
            else:
                creative = CreativeMaterial.objects.create(
                    hackathon=hackathon, title=title, file=file,
                    is_published=(action == 'publish'),
                    landing_sections=landing_sections,
                )
                verb = "published" if creative.is_published else "saved as draft"
            messages.success(request, f'Creative material "{title}" {verb}.')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return redirect('/accounts/dashboard/?tab=creatives')


def delete_creative_material(request, creative_id):
    if request.method == 'POST':
        try:
            creative = CreativeMaterial.objects.get(id=creative_id)
            title = creative.title
            creative.delete()
            messages.success(request, f'Creative material "{title}" deleted.')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return redirect('/accounts/dashboard/?tab=creatives')


def suspend_creative_material(request, creative_id):
    if request.method == 'POST':
        try:
            creative = CreativeMaterial.objects.get(id=creative_id)
            creative.is_suspended = not creative.is_suspended
            creative.save()
            status = "suspended" if creative.is_suspended else "re-activated"
            messages.success(request, f'Creative material "{creative.title}" {status}.')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    return redirect('/accounts/dashboard/?tab=creatives')


# ─────────────────────────── PUBLIC LANDING PAGE ───────────────────────────

@never_cache
def landing_page(request):
    """Public landing page displaying HackNexus statistics and info."""
    from accounts.models import ExpertInvitation, Institution, JuryInvitation
    from features.models import Documentation, Podcast, Team

    def _strip_prefix(title, prefix):
        if title and title.startswith(prefix):
            return title[len(prefix):].strip(" |")
        return title or ""

    def _timeline_date(value, fallback):
        return value.strftime("%b %d") if value else fallback

    active_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    if active_hackathon is None:
        active_hackathon = Hackathon.objects.exclude(status='Suspended').order_by('-updated_at').first()

    problem_context = _build_public_problem_statement_context(active_hackathon)
    published_problems = problem_context['published_problems']
    total_problem_statements = problem_context['total_problem_statements']
    themes_count = problem_context['themes_count']

    jury_testimonial_prefix = '[Jury Testimonial]'
    expert_testimonial_prefix = '[Expert Testimonial]'
    voice_inspiration_prefix = '[Voice of Inspiration]'
    gallery_prefix = '[Gallery]'
    testimonial_prefixes = (
        jury_testimonial_prefix,
        expert_testimonial_prefix,
        '[Team Testimonial]',
        '[VIP Testimonial]',
    )

    creative_queryset = CreativeMaterial.objects.filter(
        is_published=True,
        is_suspended=False,
    )
    if active_hackathon:
        creative_queryset = creative_queryset.filter(hackathon=active_hackathon)

    published_creatives = creative_queryset.exclude(
        title__startswith=gallery_prefix,
    ).exclude(
        title__startswith=testimonial_prefixes[0],
    ).exclude(
        title__startswith=testimonial_prefixes[1],
    ).exclude(
        title__startswith=testimonial_prefixes[2],
    ).exclude(
        title__startswith=testimonial_prefixes[3],
    ).exclude(
        title__startswith=voice_inspiration_prefix,
    ).order_by('-uploaded_at')[:6]

    published_podcasts = [
        podcast for podcast in problem_context['public_podcasts']
        if _item_matches_landing_section(podcast, 'podcasts', default_match=(podcast.problem_statement_id is None))
    ][:6]

    gallery_items = [
        asset for asset in creative_queryset.order_by('-uploaded_at')
        if _item_matches_landing_section(asset, 'gallery', legacy_prefixes=(gallery_prefix,))
    ][:8]

    jury_users = {
        user.id: user
        for user in User.objects.filter(
            from_jury_invitation__isnull=False
        ).select_related('from_jury_invitation')
    }
    expert_users = {
        user.id: user
        for user in User.objects.filter(
            from_expert_invitation__isnull=False
        ).select_related('from_expert_invitation')
    }
    testimonial_items = []
    testimonial_assets = [
        asset for asset in creative_queryset.order_by('-uploaded_at')
        if _item_matches_landing_section(
            asset,
            'testimonials',
            legacy_prefixes=(
                jury_testimonial_prefix,
                expert_testimonial_prefix,
                '[Team Testimonial]',
                '[VIP Testimonial]',
            ),
        )
    ][:8]
    for asset in testimonial_assets:
        is_jury = asset.title.startswith(jury_testimonial_prefix)
        prefix = jury_testimonial_prefix if is_jury else expert_testimonial_prefix
        kind = 'Jury' if is_jury else 'Expert'
        user = None
        role = f'{kind} Testimonial'
        organization = ''
        display_title = _strip_prefix(asset.title, prefix) or f'{kind} Testimonial'
        try:
            user_id = int(_strip_prefix(asset.title, prefix).split('|', 1)[0].strip())
        except (TypeError, ValueError, IndexError):
            user_id = None
        if user_id:
            user = jury_users.get(user_id) if is_jury else expert_users.get(user_id)
        if user:
            invite = getattr(user, 'from_jury_invitation', None) if is_jury else getattr(user, 'from_expert_invitation', None)
            display_title = user.get_full_name().strip() or user.username
            if invite:
                role = invite.designation or invite.domain or role
                organization = invite.organization or ''
        file_name = getattr(asset.file, 'name', '').lower()
        thumbnail_url = ''
        if asset.profile_image:
            try:
                thumbnail_url = asset.profile_image.url
            except Exception:
                pass
        # Use model fields if available, otherwise fall back to user-derived values
        final_name = asset.speaker_name.strip() if asset.speaker_name else display_title
        final_designation = asset.designation.strip() if asset.designation else role
        final_institute = asset.institute_name.strip() if asset.institute_name else organization
        testimonial_items.append({
            'kind': kind,
            'name': final_name,
            'role': final_designation,
            'organization': final_institute,
            'quote': f'Published {kind.lower()} testimonial from the HackNexus media library.',
            'media_url': asset.file.url if asset.file else '',
            'is_video': file_name.endswith(('.mp4', '.webm', '.ogg', '.mov', '.m4v')),
            'uploaded_at': asset.uploaded_at,
            'thumbnail_url': thumbnail_url,
        })
    if not testimonial_items:
        testimonial_items = [
            {
                'kind': 'Jury',
                'name': 'Dr. Evaluation Lead',
                'role': 'Senior Jury Member',
                'organization': 'Published testimonials will appear here',
                'quote': 'This placeholder stays visible until jury or expert testimonials are published from media communications.',
                'media_url': '',
                'is_video': False,
                'uploaded_at': None,
            },
            {
                'kind': 'Expert',
                'name': 'Innovation Mentor',
                'role': 'Domain Expert',
                'organization': 'Dynamic expert testimonials supported',
                'quote': 'Once an expert testimonial asset is published, this section will replace placeholders with live content.',
                'media_url': '',
                'is_video': False,
                'uploaded_at': None,
            },
        ]

    total_teams = Team.objects.filter(hackathon=active_hackathon).count() if active_hackathon else Team.objects.count()
    total_institutions = Institution.objects.count()
    today = timezone.localdate()
    registration_is_ongoing = bool(active_hackathon)
    if active_hackathon:
        if active_hackathon.registration_open and today < active_hackathon.registration_open:
            registration_is_ongoing = False
        elif active_hackathon.registration_close and today > active_hackathon.registration_close:
            registration_is_ongoing = False

    institution_queryset = (
        Institution.objects.select_related('extended')
        .annotate(
            team_count=Count('team', distinct=True),
            participant_count=Coalesce(Sum('team__declared_member_count'), Value(0), output_field=IntegerField()),
            ps_count=Count(
                'team__problem_statement',
                filter=Q(team__problem_statement__isnull=False),
                distinct=True,
            ),
        )
        .order_by('-team_count', 'name')
    )

    def _institution_initials(name):
        parts = [part for part in (name or '').replace('&', ' ').split() if part]
        if not parts:
            return 'IN'
        initials = ''.join(part[0] for part in parts[:3]).upper()
        return initials[:3]

    institution_cards = []
    for institution in institution_queryset:
        extended = getattr(institution, 'extended', None)
        institution_cards.append({
            'name': institution.name,
            'location': institution.location or 'Location not shared',
            'logo_url': extended.logo.url if extended and extended.logo else '',
            'logo_initials': _institution_initials(institution.name),
            'participant_count': institution.participant_count or 0,
            'team_count': institution.team_count or 0,
            'ps_count': institution.ps_count or 0,
            'is_highlighted': bool(institution.team_count or (extended and extended.logo)),
            'summary_text': (
                'Team registration ongoing..'
                if registration_is_ongoing
                else f"Team status: {institution.team_count or 0} teams registered"
            ),
        })

    track_domains = problem_context['track_domains']
    top_tracks = track_domains[:4]
    ps_modal_data = problem_context['ps_modal_data']

    leaders = []
    voice_inspiration_assets = [
        asset for asset in creative_queryset.order_by('-uploaded_at')
        if _item_matches_landing_section(
            asset,
            'voice-of-inspiration',
            legacy_prefixes=(voice_inspiration_prefix,),
        )
    ]
    # Sort by priority: items with priority 1-10 come first (ascending), then unprioritized (0) by upload date
    voice_inspiration_assets.sort(
        key=lambda a: (0 if a.display_priority > 0 else 1, a.display_priority if a.display_priority > 0 else 0)
    )
    for asset in voice_inspiration_assets:
        file_name = getattr(asset.file, 'name', '').lower()
        media_field = getattr(asset, 'profile_image', None) or getattr(asset, 'file', None)
        organization = asset.institute_name
        if not organization and active_hackathon:
            organization = active_hackathon.organization_name
        role = asset.designation or 'Voice of Inspiration'
        leaders.append({
            'avatar': '🎤',
            'name': asset.speaker_name or _strip_landing_section(asset.title) or 'Voice of Inspiration',
            'title': role,
            'organization': organization or '',
            'quote': asset.quote_text or 'Published inspiration shared through the HackNexus media library.',
            'media_url': _safe_media_url(media_field),
            'is_video': file_name.endswith(('.mp4', '.webm', '.ogg', '.mov', '.m4v')),
            'uploaded_at': asset.uploaded_at,
        })

    about_cards = [
        {
            'icon': '💡',
            'title': 'Innovation',
            'text': 'Spark practical ideas that move from concept to meaningful real-world impact.',
            'image': '/media/creatives/hero1-bg.jpg',
        },
        {
            'icon': '🏆',
            'title': 'Recognition',
            'text': 'Celebrate strong solutions with visibility, credibility, and momentum.',
            'image': '/media/creatives/hero2.jpg',
        },
        {
            'icon': '🌱',
            'title': 'Incubation',
            'text': 'Nurture early ideas with structure, support, and a path to growth.',
            'image': '/media/creatives/hero3.jpg',
        },
        {
            'icon': '⚖️',
            'title': 'Governance',
            'text': 'Enable transparent, organized, and accountable program operations.',
            'image': '/media/creatives/hero4.jpg',
        },
        {
            'icon': '🤝',
            'title': 'Supporting Community',
            'text': 'Bring together participants, mentors, institutions, and partners in one ecosystem.',
            'image': '/media/creatives/front-page.jpg',
        },
        {
            'icon': '🌿',
            'title': 'Sustainability',
            'text': 'Promote solutions that are resilient, scalable, and built to last.',
            'image': '/media/creatives/hero-bg.png',
        },
    ]

    expert_talks = []
    for podcast in published_podcasts:
        speaker = 'HackNexus Speaker'
        role = podcast.problem_statement.domain if podcast.problem_statement and podcast.problem_statement.domain else 'Featured expert session'
        if '|' in podcast.title:
            left, right = podcast.title.split('|', 1)
            speaker = left.strip() or speaker
            title = right.strip() or podcast.title
        else:
            title = podcast.title
        expert_talks.append({
            'title': title,
            'speaker': speaker,
            'role': role,
            'category': 'Expert Talk' if getattr(podcast, 'podcast_type', 'podcast') == 'expert_talk' else (podcast.problem_statement.domain if podcast.problem_statement and podcast.problem_statement.domain else 'Podcast'),
            'duration': 'Featured',
            'description': podcast.description or 'Watch this expert session to learn from practitioners and ecosystem leaders.',
            'url': podcast.video_url or (podcast.video_file.url if podcast.video_file else ''),
            'thumbnail_url': podcast.thumbnail.url if podcast.thumbnail else '',
        })
    if not expert_talks:
        expert_talks = [
            {
                'title': 'Building Scalable Civic Tech',
                'speaker': 'HackNexus Speaker',
                'role': 'Guest Expert',
                'category': 'Innovation',
                'duration': '28 mins',
                'description': 'A placeholder expert talk until website-published podcasts are added in the admin panel.',
                'url': '',
            },
            {
                'title': 'AI for Social Good',
                'speaker': 'HackNexus Speaker',
                'role': 'AI Mentor',
                'category': 'Technology',
                'duration': '35 mins',
                'description': 'A sample expert session card populated because no public podcast data is available yet.',
                'url': '',
            },
        ]

    timeline_events = []
    if active_hackathon:
        milestone_items = [
            ('Approval', active_hackathon.approval_date),
            ('Poster Launch', active_hackathon.poster_launching_date),
            ('Website Launch', active_hackathon.website_launching_date),
            ('Registration Open', active_hackathon.registration_open),
            ('Registration Close', active_hackathon.registration_close),
        ]
        milestone_items.extend(
            (
                round_data['name'] or f"Round {round_data['number']}",
                round_data['start_date'],
            )
            for round_data in active_hackathon.get_rounds()
        )

        for label, milestone_date in milestone_items:
            timeline_events.append({
                'date': _timeline_date(milestone_date, 'TBA'),
                'label': label,
                'sort_date': milestone_date,
            })

        timeline_events = sorted(
            enumerate(timeline_events),
            key=lambda item: (
                item[1]['sort_date'] is None,
                item[1]['sort_date'] or timezone.localdate(),
                item[0],
            ),
        )
        timeline_events = [
            {
                'number': index + 1,
                'date': item['date'],
                'label': item['label'],
            }
            for index, (_, item) in enumerate(timeline_events)
        ]

    judging_criteria = []
    if active_hackathon:
        params = list(RoundMarkingParameter.objects.filter(
            hackathon=active_hackathon,
            round_number=1,
            is_others=False,
        ).order_by('id')[:4])
        if params:
            share = max(10, int(100 / len(params)))
            for param in params:
                judging_criteria.append({
                    'title': param.name,
                    'percent': share,
                })
    if not judging_criteria:
        judging_criteria = [
            {'title': 'Innovation', 'percent': 25},
            {'title': 'Social Impact', 'percent': 20},
            {'title': 'Feasibility', 'percent': 15},
            {'title': 'Presentation', 'percent': 15},
        ]

    jury_members = []
    approved_juries = JuryInvitation.objects.filter(status='approved').order_by('-approved_at')[:4]
    approved_experts = ExpertInvitation.objects.filter(status='approved').order_by('-approved_at')[:4]

    def _member_photo(invite):
        if getattr(invite, 'photo', None):
            try:
                if invite.photo:
                    return invite.photo.url
            except Exception:
                pass
        created_user = getattr(invite, 'created_user', None)
        profile_image = getattr(created_user, 'profile_image', None) if created_user else None
        if profile_image:
            try:
                if profile_image:
                    return profile_image.url
            except Exception:
                pass
        return ''

    def _member_wish(invite, kind):
        if invite.bio:
            return invite.bio
        if kind == 'jury':
            return 'Sharing thoughtful evaluation to help the best ideas grow.'
        return 'Mentoring with practical guidance, clarity, and encouragement.'

    for invite in approved_juries:
        jury_members.append({
            'photo': _member_photo(invite),
            'name': invite.get_full_name(),
            'role': invite.domain or invite.designation or 'Jury Member',
            'wish': _member_wish(invite, 'jury'),
        })
    for invite in approved_experts:
        jury_members.append({
            'photo': _member_photo(invite),
            'name': invite.get_full_name(),
            'role': invite.domain or invite.designation or 'Expert',
            'wish': _member_wish(invite, 'expert'),
        })
    if not jury_members:
        jury_members = [
            {'photo': '', 'name': 'Dr. Vinod Dham', 'role': 'Semiconductor Expert & Entrepreneur', 'wish': 'Sharing thoughtful evaluation to help the best ideas grow.'},
            {'photo': '', 'name': 'Dr. R. A. Mashelkar', 'role': 'Former Director, CSIR', 'wish': 'Sharing thoughtful evaluation to help the best ideas grow.'},
            {'photo': '', 'name': 'Startup Ecosystem Mentor', 'role': 'Founder & Investor', 'wish': 'Mentoring with practical guidance, clarity, and encouragement.'},
            {'photo': '', 'name': 'Industry Technology Leader', 'role': 'Enterprise Innovation Expert', 'wish': 'Mentoring with practical guidance, clarity, and encouragement.'},
        ]

    institution_lookup = {
        _normalise_lookup(institution.name): institution
        for institution in institution_queryset
    }

    def _partner_tier(sponsorship):
        status_text = (sponsorship.status or '').strip().lower()
        if 'gold' in status_text:
            return 'gold'
        if 'silver' in status_text:
            return 'silver'
        amount_score = max(sponsorship.amount_received or 0, sponsorship.amount_pledged or 0)
        if amount_score >= 100000:
            return 'gold'
        if amount_score > 0:
            return 'silver'
        return 'silver'

    sponsor_card_pool = []
    sponsorship_queryset = SponsorshipFund.objects.select_related('hackathon')
    if active_hackathon:
        scoped_sponsorships = sponsorship_queryset.filter(hackathon=active_hackathon)
        if scoped_sponsorships.exists():
            sponsorship_queryset = scoped_sponsorships
    sponsorship_queryset = sponsorship_queryset.order_by('-amount_received', '-amount_pledged', 'sponsor_name')
    for sponsorship in sponsorship_queryset[:12]:
        institution = institution_lookup.get(_normalise_lookup(sponsorship.sponsor_name))
        extended = getattr(institution, 'extended', None) if institution else None
        tier_slug = _partner_tier(sponsorship)
        display_name = sponsorship.sponsor_name or (institution.name if institution else 'Sponsor')
        sponsor_card_pool.append({
            'name': display_name,
            'organization_name': display_name,
            'text': display_name,
            'location': sponsorship.location or (institution.location if institution and institution.location else 'Location not shared'),
            'logo_url': _safe_media_url(sponsorship.logo) or _safe_media_url(getattr(extended, 'logo', None)),
            'logo_initials': _institution_initials(display_name),
            'tier_slug': tier_slug,
            'tier_label': f'{tier_slug.title()} Partner',
            'amount_received': sponsorship.amount_received or 0,
            'amount_pledged': sponsorship.amount_pledged or 0,
        })

    if not sponsor_card_pool:
        fallback_cards = institution_cards[:8]
        mid_point = max(1, len(fallback_cards) // 2) if fallback_cards else 0
        for index, card in enumerate(fallback_cards):
            tier_slug = 'gold' if index < mid_point else 'silver'
            sponsor_card_pool.append({
                'name': card['name'],
                'organization_name': card['name'],
                'text': card['name'],
                'location': card['location'],
                'logo_url': card['logo_url'],
                'logo_initials': card['logo_initials'],
                'tier_slug': tier_slug,
                'tier_label': f'{tier_slug.title()} Partner',
            })

    sponsor_cards = [card for card in sponsor_card_pool if card['tier_slug'] == 'gold']
    partner_cards = [card for card in sponsor_card_pool if card['tier_slug'] == 'silver']
    if not sponsor_cards:
        sponsor_cards = sponsor_card_pool[:4]
    if not partner_cards:
        partner_cards = sponsor_card_pool[4:8] if len(sponsor_card_pool) > 4 else sponsor_card_pool[:4]

    faq_items = [
        {
            'question': 'Who can participate in HackNexus?',
            'answer': 'Students, startups, and professionals can participate. Use the registration page to check any current team-size or eligibility rules configured for the live hackathon.',
        },
        {
            'question': 'How do I register my team?',
            'answer': 'Use the Register action on the homepage to open the team registration flow. If registrations are not open yet, you can still explore the themes and public content.',
        },
        {
            'question': 'Are problem statements dynamic on this website?',
            'answer': 'Yes. Published problem statements are being loaded from the platform database and grouped by their configured domains.',
        },
        {
            'question': 'Will we get mentorship or expert support?',
            'answer': 'The platform supports mentor, jury, and expert workflows. Public details shown here expand automatically as those profiles are approved and published.',
        },
    ]

    documentation_links = Documentation.objects.filter(
        is_published=True,
    ).order_by('-created_at')
    if active_hackathon:
        scoped_docs = documentation_links.filter(hackathon=active_hackathon)
        if scoped_docs.exists():
            documentation_links = scoped_docs

    news_items = []
    news_prefixes = (
        ('[News]', 'news'),
        ('[Announcement]', 'announcement'),
    )
    for item in documentation_links:
        if not _item_matches_landing_section(
            item,
            'latest-news',
            legacy_prefixes=('[News]', '[Announcement]'),
        ):
            continue
        raw_title = (item.title or '').strip()
        news_type = None
        title = raw_title
        for prefix, mapped_type in news_prefixes:
            if raw_title.startswith(prefix):
                news_type = mapped_type
                title = raw_title[len(prefix):].strip(" |:-")
                break
        if not news_type:
            continue
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
        if len(news_items) >= 8:
            break
    resource_links = [
        item for item in documentation_links
        if _item_matches_landing_section(
            item,
            'latest-news',
            legacy_prefixes=('[News]', '[Announcement]'),
        )
    ][:3]

    stat_cards = [
        {'value': f'{total_problem_statements}+' if total_problem_statements else '75+', 'label': 'Problem Statements'},
        {'value': f'{total_teams}+' if total_teams else '500+', 'label': 'Teams'},
        {'value': f'{total_institutions}+' if total_institutions else '150+', 'label': 'Institutions'},
        {'value': f'{len(top_tracks)}' if top_tracks else '7', 'label': 'Tracks'},
        {'value': f'{len(expert_talks)}', 'label': 'Expert Talks'},
        {'value': f'{active_hackathon.number_of_rounds if active_hackathon else 1}', 'label': 'Rounds'},
    ]

    # Resolve branding URLs from the active hackathon
    hero_banner_url = ''
    event_logo_url = ''
    platform_logo_url = ''
    hero_banner_urls = []
    if active_hackathon:
        # Get multiple hero banner images
        banner_images = list(active_hackathon.hero_banners.order_by('display_order'))
        for b in banner_images:
            try:
                hero_banner_urls.append(b.image.url)
            except Exception:
                pass
        # Fallback to legacy single hero_banner field
        if not hero_banner_urls and active_hackathon.hero_banner:
            try:
                hero_banner_url = active_hackathon.hero_banner.url
                hero_banner_urls = [hero_banner_url]
            except Exception:
                pass
        if hero_banner_urls:
            hero_banner_url = hero_banner_urls[0]
        if active_hackathon.event_logo:
            try:
                event_logo_url = active_hackathon.event_logo.url
            except Exception:
                pass
        if active_hackathon.platform_logo:
            try:
                platform_logo_url = active_hackathon.platform_logo.url
            except Exception:
                pass

    # Default fallback banner images
    default_banners = [
        '/media/creatives/hero1-bg.jpg',
        '/media/creatives/hero2.jpg',
        '/media/creatives/hero3.jpg',
        '/media/creatives/hero4.jpg',
    ]

    # Slide content definitions (text/CTA per slide)
    slide_defs = [
        {
            'title_prefix': 'Build Solutions for',
            'highlight': 'Smart India',
            'description': 'Transform ideas into impactful innovations that drive national development.',
            'highlights': [
                {'icon': '📅', 'text': active_hackathon.registration_open.strftime('%b %d, %Y') if active_hackathon and active_hackathon.registration_open else 'Registrations Live'},
                {'icon': '📍', 'text': active_hackathon.organization_name if active_hackathon else 'HackNexus Platform'},
                {'icon': '💡', 'text': f'{total_problem_statements or 75}+ Challenges'},
                {'icon': '🌍', 'text': 'National Level'},
            ],
            'primary_label': 'Register Now',
            'primary_target': '#registerModal',
            'secondary_label': 'View Tracks',
            'secondary_target': '#tracksSection',
            'primary_type': 'primary',
        },
        {
            'title_prefix': 'Code. Innovate.',
            'highlight': 'Transform.',
            'description': 'Join builders, mentors, and institutions in solving India-first challenges with execution-focused ideas.',
            'highlights': [
                {'icon': '👥', 'text': f'{total_teams or 500}+ Teams'},
                {'icon': '🏫', 'text': f'{total_institutions or 150}+ Institutions'},
                {'icon': '🎯', 'text': f'{themes_count or len(top_tracks)} Themes'},
                {'icon': '🎙️', 'text': f'{len(expert_talks)} Expert Talks'},
            ],
            'primary_label': 'View Tracks',
            'primary_target': '#tracksSection',
            'secondary_label': 'Browse Problems',
            'secondary_target': '#tracksSection',
            'primary_type': 'orange',
        },
        {
            'title_prefix': 'Innovation for',
            'highlight': 'Nation',
            'description': 'A developed, self-reliant India needs bold prototypes, sharp teams, and practical follow-through.',
            'highlights': [
                {'icon': '🏆', 'text': 'Prize Support'},
                {'icon': '👨‍🏫', 'text': 'Expert Mentorship'},
                {'icon': '📈', 'text': 'Launch Visibility'},
                {'icon': '🌟', 'text': 'Recognition'},
            ],
            'primary_label': 'Browse Problems',
            'primary_target': '#tracksSection',
            'secondary_label': 'Explore Talks',
            'secondary_target': '#podcasts',
            'primary_type': 'primary',
        },
        {
            'title_prefix': 'Think Bold.',
            'highlight': 'Build Fast.',
            'description': 'Move from idea to prototype with a national-stage platform built for real outcomes and visible momentum.',
            'highlights': [
                {'icon': 'IDEA', 'text': 'Creative Thinking'},
                {'icon': 'ROCKET', 'text': 'Rapid Prototyping'},
                {'icon': 'SPEED', 'text': 'Fast Execution'},
                {'icon': 'BOOST', 'text': 'High Energy'},
            ],
            'primary_label': 'Register Now',
            'primary_target': '#registerModal',
            'secondary_label': 'View Tracks',
            'secondary_target': '#tracksSection',
            'primary_type': 'orange',
        },
    ]

    # Use uploaded banners; if more banners than slide_defs, duplicate defs cyclically
    banners = hero_banner_urls if hero_banner_urls else default_banners
    num_slides = max(len(banners), len(slide_defs))

    hero_slides = []
    for i in range(num_slides):
        slide_content = slide_defs[i % len(slide_defs)].copy()
        slide_content['background_image'] = banners[i % len(banners)]
        slide_content['title_color'] = '#0f172a'
        slide_content['muted_color'] = '#1f2937'
        slide_content['accent_color'] = '#ff6b1a'
        slide_content['label_color'] = '#0f172a'
        hero_slides.append(slide_content)

    ticker_message = ''
    if news_items:
        ticker_parts = []
        for item in news_items[:4]:
            published_at = item['item'].created_at.strftime('%d %b %Y, %I:%M %p') if item['item'].created_at else ''
            ticker_parts.append(
                f"{item['type_label']}: {item['title']}"
                + (f" ({published_at})" if published_at else '')
            )
        ticker_message = '  •  '.join(ticker_parts)
    elif active_hackathon and active_hackathon.registration_close:
        ticker_message = f'Registrations close on {active_hackathon.registration_close:%B %d, %Y}. Explore themes, problem statements, and expert content before applying.'
    else:
        ticker_message = 'Explore the latest published problem statements and public expert content on the platform.'

    return render(request, 'landing_page.html', {
        'active_hackathon': active_hackathon,
        'published_problems': published_problems[:6],
        'total_problem_statements': total_problem_statements,
        'themes_count': themes_count or len(top_tracks),
        'published_creatives': published_creatives,
        'published_podcasts': published_podcasts,
        'gallery_items': gallery_items,
        'news_items': news_items,
        'testimonial_items': testimonial_items,
        'total_teams': total_teams,
        'total_institutions': total_institutions,
        'institution_cards': institution_cards,
        'hero_slides': hero_slides,
        'ticker_message': ticker_message,
        'leaders': leaders,
        'about_cards': about_cards,
        'top_tracks': top_tracks,
        'track_domains': track_domains,
        'ps_modal_data': ps_modal_data,
        'expert_talks': expert_talks,
        'timeline_events': timeline_events,
        'judging_criteria': judging_criteria,
        'jury_members': jury_members[:8],
        'sponsor_cards': sponsor_cards[:10],
        'partner_cards': partner_cards[:10],
        'faq_items': faq_items,
        'documentation_links': resource_links,
        'stat_cards': stat_cards,
        'event_logo_url': event_logo_url,
        'platform_logo_url': platform_logo_url,
        'hero_banner_url': hero_banner_url,
    })


def public_problem_statements(request):
    """Public page that lists all published problem statements and their resources."""
    active_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    if active_hackathon is None:
        active_hackathon = Hackathon.objects.exclude(status='Suspended').order_by('-updated_at').first()

    problem_context = _build_public_problem_statement_context(active_hackathon)
    selected_domain = _normalise_lookup(request.GET.get('domain'))
    problem_statement_groups = _resolve_problem_domain_filter(
        problem_context['problem_statement_groups'],
        selected_domain,
    )
    problem_statements = []
    for group in problem_statement_groups:
        problem_statements.extend(group.get('problems', []))

    return render(request, 'problem_statements.html', {
        'active_hackathon': active_hackathon,
        'all_problem_statement_groups': problem_context['problem_statement_groups'],
        'problem_statement_groups': problem_statement_groups,
        'problem_statements': problem_statements,
        'total_problem_statements': problem_context['total_problem_statements'],
        'themes_count': problem_context['themes_count'],
        'selected_domain': selected_domain,
    })


@login_required(login_url="/accounts/")
def launch_event(request, hackathon_id):
    """Launch an event — set its status to Live and record the launch metadata."""
    import json
    from django.http import JsonResponse
    from django.views.decorators.http import require_POST

    if not _can_manage_events(request):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    hackathon = get_object_or_404(Hackathon, id=hackathon_id)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = {}

    hackathon.status = 'Live'
    hackathon.save()

    return JsonResponse({
        'success': True,
        'message': f'{hackathon.name} has been launched successfully!',
        'hackathon_id': hackathon.id,
        'status': hackathon.status,
    })


@login_required(login_url="/accounts/")
def draft_event(request, hackathon_id):
    """Revert an event to Draft status."""
    from django.http import JsonResponse
    if not _can_manage_events(request):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    hackathon = get_object_or_404(Hackathon, id=hackathon_id)
    hackathon.status = 'Draft'
    hackathon.save()

    return JsonResponse({
        'success': True,
        'message': f'{hackathon.name} has been reverted to Draft successfully!',
        'hackathon_id': hackathon.id,
        'status': hackathon.status,
    })

