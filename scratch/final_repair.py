
import os

view_file = r'D:\OKCL\Hackathon\code\Bput-Hackathon\features\views.py'

with open(view_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

def final_fix(lines):
    new_lines = []
    i = 0
    # Capture everything up to the end of create_team (line 820 approx)
    while i < len(lines):
        line = lines[i]
        
        # Look for the end of create_team return
        if 'return render_route(request, redirect_url)' in line and i > 0 and 'create_team' in "".join(lines[i-20:i]):
            new_lines.append(line)
            new_lines.append("\n\n")
            
            # INSERT ALL MISSING VIEWS HERE
            new_lines.append("""@login_required(login_url='/accounts/')
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

""")
            # Now SKIP everything until delete_team_document
            while i < len(lines) and 'def delete_team_document' not in lines[i]:
                i += 1
            if i < len(lines):
                # We are at 'def delete_team_document'
                # Backtrack to catch decorators correctly
                j = len(new_lines) - 1
                while j >= 0 and new_lines[j].strip().startswith('@'):
                     j -= 1
                # We want to keep ONLY ONE @login_required and NO @require_POST
                new_lines.append("@login_required(login_url='/accounts/')\\n")
                new_lines.append("def delete_team_document(request, doc_id):\\n")
                new_lines.append("    if request.method != 'POST':\\n")
                new_lines.append("        return render_route(request, '/features/teams/?sub=live_teams')\\n")
                
                # Advance i over the duplicate decorators and def
                while i < len(lines) and not lines[i].strip().startswith('if not _has_team_permission'):
                     i += 1
                # i is now at 'if not _has_team_permission'
                continue
        
        new_lines.append(line)
        i += 1
    return new_lines

fixed_lines = final_fix(lines)

with open(view_file, 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("Final repair completed successfully.")
