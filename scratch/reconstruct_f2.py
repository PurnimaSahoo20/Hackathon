
import os

view_file = r'D:\OKCL\Hackathon\code\Bput-Hackathon\features\views.py'

with open(view_file, 'r', encoding='utf-8') as f:
    text = f.read()

# Marker for Feature 2 start
f2_start_marker = "#  FEATURE 2 : TEAM & EVENT MONITORING"
# Marker for Feature 3 start
f3_start_marker = "#  FEATURE 3 : CONTENT MANAGEMENT"

try:
    # Find positions
    start_pos = text.find(f2_start_marker)
    # We want to keep the box-line before it, but let's just find the start of the section
    # Actually, let's find the exact block.
    
    # Locate the header for F2
    idx_f2 = text.find(f2_start_marker)
    idx_f3 = text.find(f3_start_marker)
    
    # We want to replace everything between the line BEFORE idx_f2 and the line BEFORE idx_f3
    # Find the double-lines before idx_f2
    search_start = text.rfind("# ══════════════════════════════════════════════════════════════", 0, idx_f2)
    search_end = text.rfind("# ══════════════════════════════════════════════════════════════", 0, idx_f3)
    
    f2_content = """# ══════════════════════════════════════════════════════════════
#  FEATURE 2 : TEAM & EVENT MONITORING
# ══════════════════════════════════════════════════════════════

@login_required(login_url='/accounts/')
@never_cache
def team_event_monitoring(request):
    if not _has_team_permission(request):
        messages.error(request, "Access denied. You need Team & Event Monitoring permission.")
        return render_route(request, '/accounts/dashboard/')

    sub              = request.GET.get('sub', 'live_teams')
    hackathon_filter = request.GET.get('hackathon', '')
    status_filter    = request.GET.get('status', '')
    query            = request.GET.get('q', '')

    live_hackathon = Hackathon.objects.filter(status='Live').order_by('-updated_at').first()
    all_hackathons = Hackathon.objects.exclude(status='Suspended').order_by('-created_at')

    active_hackathon = None
    if hackathon_filter and hackathon_filter.isdigit():
        active_hackathon = Hackathon.objects.filter(id=hackathon_filter).first()
    elif live_hackathon:
        active_hackathon = live_hackathon

    context = {
        'tab':              'team_monitoring',
        'sub':              sub,
        'live_hackathon':   live_hackathon,
        'active_hackathon': active_hackathon,
        'all_hackathons':   all_hackathons,
        'hackathon_filter': hackathon_filter or (str(live_hackathon.id) if live_hackathon else ''),
        'status_filter':    status_filter,
        'q':                query,
        'STATUS_CHOICES':   TeamStatusLog.STATUS_CHOICES,
        'has_team_perm':    _has_team_permission(request),
        'institutions':      Institution.objects.order_by('name'),
        'problem_statements': ProblemStatement.objects.filter(
            **({'hackathon': active_hackathon} if active_hackathon else {})
        ).order_by('title'),
    }
    context['pending_count'] = TeamRegistration.objects.filter(
        status='pending',
        **({'hackathon': active_hackathon} if active_hackathon else {})
    ).count()

    if sub == 'pending_approvals':
        regs = TeamRegistration.objects.select_related(
            'hackathon', 'team_leader', 'institution', 'problem_statement', 'mentor'
        ).filter(status='pending').order_by('-registered_at')

        if active_hackathon:
            regs = regs.filter(hackathon=active_hackathon)
        if query:
            regs = regs.filter(
                Q(team_name__icontains=query) |
                Q(team_leader__username__icontains=query) |
                Q(team_leader__email__icontains=query)
            )

        paginator = Paginator(regs, 15)
        page = request.GET.get('page')
        try:
            context['pending_regs'] = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            context['pending_regs'] = paginator.page(1)

    elif sub == 'live_teams':
        teams = Team.objects.select_related(
            'hackathon', 'institution', 'team_leader', 'problem_statement'
        ).order_by('team_name')

        if active_hackathon:
            teams = teams.filter(hackathon=active_hackathon)
        if status_filter:
            teams = teams.filter(status=status_filter)
        if query:
            teams = teams.filter(
                Q(team_name__icontains=query) |
                Q(team_leader__username__icontains=query) |
                Q(team_leader__email__icontains=query)
            )

        paginator = Paginator(teams, 15)
        page = request.GET.get('page')
        try:
            context['teams'] = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            context['teams'] = paginator.page(1)

        if active_hackathon:
            ht = Team.objects.filter(hackathon=active_hackathon)
            context['summary'] = {
                'total':     ht.count(),
                'active':    ht.filter(status='spoc_approved').count(),
                'pending':   ht.filter(status__in=['pending_mentor', 'pending_spoc']).count(),
                'submitted': ht.filter(status='submitted').count(),
                'evaluated': ht.filter(status='evaluated').count(),
                'suspended': ht.filter(status='disqualified').count(),
            }

    elif sub == 'all_hackathons':
        stats = []
        for h in all_hackathons:
            t = Team.objects.filter(hackathon=h)
            r = TeamRegistration.objects.filter(hackathon=h)
            stats.append({
                'hackathon':   h,
                'total':       t.count(),
                'active':      t.filter(status='spoc_approved').count(),
                'pending_reg': r.filter(status='pending').count(),
                'submitted':   t.filter(status='submitted').count(),
                'evaluated':   t.filter(status='evaluated').count(),
            })
        context['stats'] = stats

    elif sub == 'team_detail':
        team_id = request.GET.get('team_id')
        try:
            team = Team.objects.select_related(
                'hackathon', 'institution', 'team_leader', 'problem_statement'
            ).get(id=team_id)
            context.update({
                'team':    team,
                'members': TeamMember.objects.filter(team=team).select_related('user'),
                'mentors': TeamMentor.objects.filter(team=team).select_related('mentor__user'),
                'logs':    TeamStatusLog.objects.filter(team=team).select_related('changed_by'),
                'docs':    TeamDocument.objects.filter(team=team),
                'reg':     getattr(team, 'from_registration', None),
            })
        except Team.DoesNotExist:
            messages.error(request, "Team not found.")
            return render_route(request, '/features/teams/?sub=live_teams')

    elif sub == 'reg_detail':
        reg_id = request.GET.get('reg_id')
        try:
            reg = TeamRegistration.objects.select_related(
                'hackathon', 'team_leader', 'institution',
                'problem_statement', 'mentor', 'reviewed_by'
            ).get(id=reg_id)
            context.update({
                'reg':  reg,
                'docs': TeamDocument.objects.filter(registration=reg),
            })
        except TeamRegistration.DoesNotExist:
            messages.error(request, "Registration not found.")
            return render_route(request, '/features/teams/?sub=pending_approvals')

    return render(request, 'features/team_monitoring.html', context)


@login_required(login_url='/accounts/')
def create_team(request):
    if request.method != 'POST':
        return render_route(request, '/features/teams/?sub=live_teams')

    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')

    hackathon_id = request.POST.get('hackathon_id', '').strip()
    team_name = request.POST.get('team_name', '').strip()
    institution_id = request.POST.get('institution_id', '').strip()
    problem_statement_id = request.POST.get('problem_statement_id', '').strip()
    status = request.POST.get('status', 'spoc_approved').strip() or 'spoc_approved'
    declared_member_count_raw = request.POST.get('declared_member_count', '').strip()

    redirect_url = f'/features/teams/?sub=live_teams&hackathon={hackathon_id}'

    try:
        if not hackathon_id or not team_name:
            raise ValueError("Hackathon and team name are required.")

        hackathon = Hackathon.objects.get(id=hackathon_id)
        if Team.objects.filter(hackathon=hackathon, team_name__iexact=team_name).exists():
            raise ValueError(f"A team named '{team_name}' already exists for this hackathon.")

        leader_email = request.POST.get('leader_email', '').strip().lower()
        leader_first_name = request.POST.get('leader_first_name', '').strip()
        leader_last_name = request.POST.get('leader_last_name', '').strip()
        leader_phone = request.POST.get('leader_phone_number', '').strip()
        leader_role = request.POST.get('leader_role_in_team', 'Leader').strip() or 'Leader'
        leader_aadhaar_proof = request.FILES.get('leader_aadhaar_proof')
        leader_college_id_proof = request.FILES.get('leader_college_id_proof')

        if not leader_email:
            raise ValueError("Team leader email is required.")
        if not leader_aadhaar_proof or not leader_college_id_proof:
            raise ValueError("Aadhaar proof and college ID proof are required for the team leader.")

        member_first_names = request.POST.getlist('member_first_name[]')
        member_last_names = request.POST.getlist('member_last_name[]')
        member_emails = request.POST.getlist('member_email[]')
        member_phones = request.POST.getlist('member_phone_number[]')
        member_roles = request.POST.getlist('member_role_in_team[]')
        member_indexes = request.POST.getlist('member_index[]')

        member_rows = []
        for index, email in enumerate(member_emails):
            email = email.strip()
            if not email:
                continue
            form_index = member_indexes[index] if index < len(member_indexes) else str(index)
            aadhaar_proof = request.FILES.get(f'member_aadhaar_proof_{form_index}')
            college_id_proof = request.FILES.get(f'member_college_id_proof_{form_index}')
            if not aadhaar_proof or not college_id_proof:
                raise ValueError(f"Aadhaar proof and college ID proof are required for member {index + 1}.")
            member_rows.append({
                'first_name': member_first_names[index].strip() if index < len(member_first_names) else '',
                'last_name': member_last_names[index].strip() if index < len(member_last_names) else '',
                'email': email,
                'phone_number': member_phones[index].strip() if index < len(member_phones) else '',
                'role_in_team': member_roles[index].strip() if index < len(member_roles) else 'Member',
                'aadhaar_proof': aadhaar_proof,
                'college_id_proof': college_id_proof,
            })

        total_members = len(member_rows) + 1
        try:
            declared_member_count = int(declared_member_count_raw)
        except (TypeError, ValueError):
            raise ValueError("Please mention a valid number of team members.")

        if declared_member_count != total_members:
            raise ValueError(
                f"Number of members ({declared_member_count}) mismatches the number of valid entries ({total_members}). "
                "Ensure all listed members have a valid email address."
            )

        if total_members < hackathon.min_team_size or total_members > hackathon.max_team_size:
            raise ValueError(
                f"Team size must be between {hackathon.min_team_size} and {hackathon.max_team_size} members."
            )

        from collections import Counter
        all_emails = [leader_email] + [row['email'].lower() for row in member_rows]
        email_counts = Counter(all_emails)
        duplicates = [email for email, count in email_counts.items() if count > 1]
        
        if duplicates:
            msg = f"Duplicate emails found: {', '.join(duplicates)}. Each member (including the leader) must have a unique email."
            raise ValueError(msg)

        valid_statuses = [value for value, _ in TeamStatusLog.STATUS_CHOICES]
        if status not in valid_statuses:
            status = 'spoc_approved'

        with transaction.atomic():
            leader = _get_or_create_team_user(
                leader_email,
                first_name=leader_first_name,
                last_name=leader_last_name,
                phone_number=leader_phone,
                role_name='Teamlead',
            )
            TeamleadProfile.objects.get_or_create(user=leader)

            team = Team.objects.create(
                team_name=team_name,
                hackathon=hackathon,
                institution_id=institution_id or None,
                team_leader=leader,
                problem_statement_id=problem_statement_id or None,
                declared_member_count=declared_member_count,
                leader_role_in_team=leader_role,
                leader_aadhaar_proof=leader_aadhaar_proof,
                leader_college_id_proof=leader_college_id_proof,
                status=status,
            )

            for row in member_rows:
                member_user = _get_or_create_team_user(
                    row['email'],
                    first_name=row['first_name'],
                    last_name=row['last_name'],
                    phone_number=row['phone_number'],
                )
                TeamMember.objects.create(
                    team=team,
                    user=member_user,
                    role_in_team=row['role_in_team'] or 'Member',
                    aadhaar_proof=row['aadhaar_proof'],
                    college_id_proof=row['college_id_proof'],
                )

            TeamStatusLog.objects.create(
                team=team,
                old_status='',
                new_status=status,
                changed_by=request.user,
                note=f"Team created directly by {request.user.get_username()}.",
            )

        messages.success(request, f"Team '{team.team_name}' created with {total_members} member(s).")
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team.id}&hackathon={hackathon.id}')

    except Hackathon.DoesNotExist:
        messages.error(request, "Selected hackathon was not found.")
    except Exception as exc:
        logger.error(f"Create team failed: {exc}", exc_info=True)
        messages.error(request, f"Team creation failed: {exc}")

    return render_route(request, redirect_url)


@login_required(login_url='/accounts/')
def approve_team_registration(request, reg_id):
    if request.method != 'POST':
        return render_route(request, '/features/teams/?sub=pending_approvals')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        reg = TeamRegistration.objects.get(id=reg_id)
        if reg.status != 'pending':
            messages.warning(request, f"Registration is already '{reg.status}'.")
            return render_route(request, '/features/teams/?sub=pending_approvals')
        reg.status      = 'approved'
        reg.reviewed_by = request.user
        reg.reviewed_at = timezone.now()
        reg.save()
        messages.success(request, f"Team '{reg.team_name}' approved. Team record created.")
    except TeamRegistration.DoesNotExist:
        messages.error(request, "Registration not found.")
    except Exception as exc:
        logger.error(f"Approve registration {reg_id}: {exc}", exc_info=True)
        messages.error(request, f"Approval failed: {exc}")
    return render_route(request, '/features/teams/?sub=pending_approvals')


@login_required(login_url='/accounts/')
def reject_team_registration(request, reg_id):
    if request.method != 'POST':
        return render_route(request, '/features/teams/?sub=pending_approvals')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        from accounts.signals import _send_team_rejection_email
        reg = TeamRegistration.objects.get(id=reg_id)
        note = request.POST.get('rejection_note', '').strip()
        reg.status         = 'rejected'
        reg.reviewed_by    = request.user
        reg.reviewed_at    = timezone.now()
        reg.rejection_note = note
        reg.save()
        try:
            _send_team_rejection_email(reg, note)
        except Exception:
            pass
        messages.success(request, f"Team '{reg.team_name}' registration rejected.")
    except TeamRegistration.DoesNotExist:
        messages.error(request, "Registration not found.")
    except Exception as exc:
        messages.error(request, f"Rejection failed: {exc}")
    return render_route(request, '/features/teams/?sub=pending_approvals')


@login_required(login_url='/accounts/')
def edit_team(request, team_id):
    if request.method != 'POST':
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team = Team.objects.get(id=team_id)
        new_name = request.POST.get('team_name', '').strip()
        if new_name:
            team.team_name = new_name
        ps_id = request.POST.get('problem_statement_id', '').strip()
        if ps_id and ps_id.isdigit():
            ps = ProblemStatement.objects.filter(id=ps_id).first()
            if ps:
                team.problem_statement = ps
        inst_id = request.POST.get('institution_id', '').strip()
        if inst_id and inst_id.isdigit():
            inst = Institution.objects.filter(id=inst_id).first()
            if inst:
                team.institution = inst
        team.save()
        messages.success(request, f"Team '{team.team_name}' updated.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        logger.error(f"Edit team {team_id}: {exc}", exc_info=True)
        messages.error(request, f"Update failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def suspend_team(request, team_id):
    if request.method != 'POST':
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team = Team.objects.get(id=team_id)
        note = request.POST.get('note', '').strip()
        old_status = team.status
        if team.status == 'disqualified':
            team.status = 'spoc_approved'
            word = "reactivated"
        else:
            team.status = 'disqualified'
            word = "suspended"
        team.save()
        TeamStatusLog.objects.create(
            team=team, old_status=old_status, new_status=team.status,
            changed_by=request.user, note=note or f"Admin {word} the team.",
        )
        messages.success(request, f"Team '{team.team_name}' {word}.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        logger.error(f"Suspend team {team_id}: {exc}", exc_info=True)
        messages.error(request, f"Failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def update_team_status(request, team_id):
    if request.method != 'POST':
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team = Team.objects.get(id=team_id)
        new_status = request.POST.get('new_status', '').strip()
        note       = request.POST.get('note', '').strip()
        valid = [s[0] for s in TeamStatusLog.STATUS_CHOICES]
        if new_status not in valid:
            messages.error(request, f"Invalid status: {new_status}")
            return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
        old_status = team.status
        team.status = new_status
        team.save()
        TeamStatusLog.objects.create(
            team=team, old_status=old_status, new_status=new_status,
            changed_by=request.user, note=note,
        )
        messages.success(request, f"Team '{team.team_name}' -> '{new_status}'.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        logger.error(f"Status update team {team_id}: {exc}", exc_info=True)
        messages.error(request, f"Failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def upload_team_document(request, team_id):
    if request.method != 'POST':
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    try:
        team  = Team.objects.get(id=team_id)
        title = request.POST.get('title', '').strip()
        dtype = request.POST.get('doc_type', 'other')
        f     = request.FILES.get('file')
        if not title or not f:
            messages.error(request, "Title and file are required.")
            return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
        TeamDocument.objects.create(
            team=team, uploaded_by=request.user, doc_type=dtype, title=title, file=f,
        )
        messages.success(request, f"Document '{title}' uploaded.")
    except Team.DoesNotExist:
        messages.error(request, "Team not found.")
    except Exception as exc:
        messages.error(request, f"Upload failed: {exc}")
    return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')


@login_required(login_url='/accounts/')
def delete_team_document(request, doc_id):
    if request.method != 'POST':
        return render_route(request, '/features/teams/?sub=live_teams')
    if not _has_team_permission(request):
        messages.error(request, "Access denied.")
        return render_route(request, '/accounts/dashboard/')
    team_id = request.POST.get('team_id', '')
    try:
        doc = TeamDocument.objects.get(id=doc_id)
        doc.delete()
        messages.success(request, "Document deleted.")
    except TeamDocument.DoesNotExist:
        messages.error(request, "Document not found.")
    except Exception as exc:
        messages.error(request, f"Failed: {exc}")
    if team_id:
        return render_route(request, f'/features/teams/?sub=team_detail&team_id={team_id}')
    return render_route(request, '/features/teams/?sub=live_teams')


"""

    new_text = text[:search_start] + f2_content + text[idx_f3:]
    with open(view_file, 'w', encoding='utf-8') as f:
        f.write(new_text)
    print("Feature 2 restored perfectly.")

except Exception as e:
    print(f"Error: {e}")

