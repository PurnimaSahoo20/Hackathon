import re
import sys

file_path = r'd:\OKCL\Hackathon\code\Bput-Hackathon\accounts\views.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

target_pattern = r"elif tab == 'creatives':\s*query = request\.GET\.get\('search_creatives', ''\)\s*f\"  Username : \{user\.username\}\\n\"\s*f\"  Password : \{plain_password\}\\n\"\s*f\"  Role     : \{role_name\}\\n\\n\"\s*f\"Please log in at: http://127\.0\.0\.1:8000/accounts/\\n\\n\"\s*f\"We strongly recommend changing your password after your first login\.\\n\\n\"\s*f\"— HackNexus Team\"\s*\)"

replacement = """    elif tab == 'creatives':
        query = request.GET.get('search_creatives', '')
        creatives = CreativeMaterial.objects.all().select_related('hackathon').order_by('-uploaded_at')
        if query:
            creatives = creatives.filter(
                Q(title__icontains=query) | Q(hackathon__name__icontains=query)
            )
        context['creatives_list'] = creatives
        context['hackathons'] = Hackathon.objects.filter(status='Live').order_by('-created_at')
        context['search_creatives'] = query

    return render(request, 'accounts/superadmin_dashboard.html', context)


@login_required(login_url="/accounts/")
@never_cache
def admin_dashboard(request):
    if not hasattr(request.user, 'admin_profile'):
        messages.error(request, "Permission denied.")
        return render_route(request, '/accounts/dashboard/')

    from features.views import ADMIN_PERMISSION_META

    admin_prof = request.user.admin_profile
    assigned_codenames = set(
        admin_prof.permissions.all().values_list('codename', flat=True)
    )

    # Colour palette cycling across deduplicated feature cards
    CARD_COLOURS = [
        'fc-blue', 'fc-indigo', 'fc-violet', 'fc-emerald', 'fc-teal',
        'fc-orange', 'fc-rose', 'fc-amber', 'fc-cyan', 'fc-sky',
    ]

    # Build feature card list — deduplicated by url_name, each card knows
    # whether it is enabled and which colour to use.
    feature_cards = []
    seen_urls = set()
    colour_idx = 0
    for codename, meta in ADMIN_PERMISSION_META.items():
        url_key = meta.get('url_name', '')
        if url_key in seen_urls:
            # Two codenames share a URL → merge into the existing card
            for card in feature_cards:
                if card['url_name'] == url_key:
                    card['is_enabled'] = card['is_enabled'] or (codename in assigned_codenames)
                    if codename in assigned_codenames:
                        card['codenames'].append(codename)
            continue
        seen_urls.add(url_key)
        feature_cards.append({
            'codename': codename,
            'codenames': [codename],
            'label': meta.get('label', codename),
            'description': meta.get('description', ''),
            'icon': meta.get('icon', 'grid-outline'),
            'url_name': url_key,
            'is_enabled': codename in assigned_codenames,
            'colour': CARD_COLOURS[colour_idx % len(CARD_COLOURS)],
        })
        colour_idx += 1

    context = {
        'permissions': assigned_codenames,
        'feature_cards': feature_cards,
        'enabled_count': len([c for c in feature_cards if c['is_enabled']]),
        'admin_profile': admin_prof,
        'live_hackathon': Hackathon.objects.filter(status='Live').order_by('-updated_at').first(),
        'active_nav': 'admin_dashboard',
    }
    return render(request, 'accounts/admin_dashboard.html', context)


# ─────────────────────────── USER CREATION ───────────────────────────

def _send_welcome_email(user, plain_password, role_name):
    \"\"\"Send a welcome email to a newly created user with their login credentials.\"\"\"
    try:
        subject = f"Welcome to HackNexus — Your {role_name} Account Details"

        plain_body = (
            f"Hello {user.get_full_name() or user.username},\\n\\n"
            f"Your HackNexus account has been created by the Super Administrator.\\n\\n"
            f"Your login credentials:\\n"
            f"  Username : {user.username}\\n"
            f"  Password : {plain_password}\\n"
            f"  Role     : {role_name}\\n\\n"
            f"Please log in at: http://127.0.0.1:8000/accounts/\\n\\n"
            f"We strongly recommend changing your password after your first login.\\n\\n"
            f"— HackNexus Team"
        )"""

if re.search(target_pattern, content):
    content = re.sub(target_pattern, replacement, content)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS: Content replaced using regex.')
else:
    print('ERROR: Regex not found.')
