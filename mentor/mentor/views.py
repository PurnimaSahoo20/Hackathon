"""
mentor/views.py

Mentor portal views:
 - public accept-invite form (no login needed)
 - login + OTP 2FA
 - dashboard, team details, solution view, messages, profile
"""
import logging
import secrets
import string

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.passwords import PORTAL_PASSWORD_HELP_TEXT, validate_portal_password

logger = logging.getLogger(__name__)


def _mentor_required(request):
    return request.user.is_authenticated and hasattr(request.user, "mentor_profile")


def _get_mentor(request):
    return getattr(request.user, "mentor_profile", None)


def _generate_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _send_otp_email(user, otp_code):
    subject = "HackNexus Mentor - Login Verification Code"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;
                padding:32px;background:#fff;border-radius:12px;border:1px solid #e5e7eb;">
        <h2 style="color:#059669;">HackNexus Mentor 2FA</h2>
        <p>Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
        <p>Your verification code:</p>
        <div style="background:#f0fdf4;border:2px dashed #059669;border-radius:8px;
                    padding:24px;text-align:center;margin:24px 0;">
            <span style="font-size:36px;font-weight:900;letter-spacing:12px;color:#059669;">{otp_code}</span>
        </div>
        <p style="color:#6b7280;font-size:13px;">Valid for <strong>10 minutes</strong>.</p>
    </div>"""
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"Your OTP: {otp_code}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.error("Mentor OTP email error: %s", exc)


def _get_sidebar_team(request):
    mentor = _get_mentor(request)
    if not mentor:
        return None

    from features.models import Team

    session_team_id = request.session.get("mentor_current_team_id")
    if session_team_id:
        team = Team.objects.filter(
            id=session_team_id,
            assigned_mentors__mentor=mentor,
        ).select_related("hackathon", "team_leader", "problem_statement", "institution").first()
        if team:
            return team

    team = Team.objects.filter(
        assigned_mentors__mentor=mentor,
    ).select_related("hackathon", "team_leader", "problem_statement", "institution").order_by("team_name").first()

    if team:
        request.session["mentor_current_team_id"] = team.id
    else:
        request.session.pop("mentor_current_team_id", None)
    return team


def mentor_accept_invite(request, token):
    from .models import MentorInvitation

    try:
        invite = MentorInvitation.objects.get(token=token)
    except MentorInvitation.DoesNotExist:
        return render(request, "mentor/invite_invalid.html", {"reason": "Invalid or expired link."})

    if invite.status not in ("invited",):
        return render(
            request,
            "mentor/invite_invalid.html",
            {"reason": f"This invitation has already been {invite.status}."},
        )

    if request.method == "POST":
        invite.mentor_designation = request.POST.get("designation", "").strip()
        invite.mentor_institution = request.POST.get("institution", "").strip()
        invite.mentor_phone = request.POST.get("phone", "").strip()
        invite.mentor_expertise = request.POST.get("expertise", "").strip()
        if request.FILES.get("id_proof"):
            invite.id_proof = request.FILES["id_proof"]
        invite.status = "spoc_pending"
        invite.accepted_at = timezone.now()
        invite.save()

        _create_spoc_accept_notifications(invite)
        return render(request, "mentor/invite_success.html", {"invite": invite})

    return render(request, "mentor/accept_invite.html", {"invite": invite})


def _create_spoc_accept_notifications(invite):
    try:
        if not invite.registration or not invite.registration.institution:
            return

        from accounts.models import SpocInstitutionMap
        from spoc.spoc.models import SpocNotification
        from team.team.models import TeamNotification

        TeamNotification.objects.create(
            team_leader=invite.team_leader,
            registration=invite.registration,
            notif_type="mentor_accepted",
            title="Mentor accepted and sent to SPOC",
            body=(
                f"{invite.mentor_name} accepted your mentor invitation. "
                f"The request has been forwarded to the SPOC of {invite.registration.institution.name}."
            ),
        )

        maps = SpocInstitutionMap.objects.filter(
            institution=invite.registration.institution
        ).select_related("spoc")
        for mapping in maps:
            SpocNotification.objects.create(
                spoc=mapping.spoc,
                notif_type="team_reg",
                title=f"Mentor verification pending for {invite.registration.team_name}",
                body=(
                    f"Mentor {invite.mentor_name} accepted the invitation for "
                    f"{invite.registration.team_name}. Review the team and mentor details."
                ),
                link="/spoc/mentors/",
            )
    except Exception as exc:
        logger.error("Create mentor acceptance notifications failed: %s", exc)


@never_cache
def mentor_login(request):
    next_url = request.GET.get("next", "")
    login_url = reverse("login")
    if next_url:
        return redirect(f"{login_url}?next={next_url}")
    return redirect("login")


@never_cache
def mentor_verify_otp(request):
    user_id = request.session.get("mentor_pending_2fa_user_id")
    if not user_id:
        return redirect("mentor_login")

    from accounts.models import OTPVerification, User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect("mentor_login")

    if request.method == "POST":
        otp_code = request.POST.get("otp", "").strip()
        record = OTPVerification.objects.filter(
            user=user,
            code=otp_code,
            is_verified=False,
        ).order_by("-created_at").first()

        if record and not record.is_expired():
            record.is_verified = True
            record.save()
            del request.session["mentor_pending_2fa_user_id"]
            login(request, user)
            messages.success(request, "Login successful!")
            return redirect("mentor_dashboard")

        messages.error(request, "Invalid or expired OTP.")

    return render(request, "mentor/verify_otp.html", {"email": user.email})


@login_required(login_url="/mentor/login/")
def mentor_logout(request):
    logout(request)
    return redirect("landing_page")


@login_required(login_url="/mentor/login/")
@never_cache
def mentor_dashboard(request):
    if not _mentor_required(request):
        return redirect("mentor_login")

    mentor = _get_mentor(request)
    from features.models import TeamMentor, TeamRegistration
    from .models import MentorNotification

    assigned = TeamMentor.objects.filter(mentor=mentor).select_related("team", "team__hackathon")
    teams = [tm.team for tm in assigned]
    reg_teams = TeamRegistration.objects.filter(mentor=mentor).select_related("hackathon", "team_leader")
    notifs = MentorNotification.objects.filter(mentor=mentor, is_read=False)[:5]

    context = {
        "mentor": mentor,
        "teams": teams,
        "reg_teams": reg_teams,
        "notif_count": notifs.count(),
        "notifications": notifs,
        "active_nav": "dashboard",
        "sidebar_team": _get_sidebar_team(request),
        "team_nav_active": "",
    }
    return render(request, "mentor/dashboard.html", context)


@login_required(login_url="/mentor/login/")
@never_cache
def mentor_team_detail(request, team_id):
    if not _mentor_required(request):
        return redirect("mentor_login")

    context = _build_team_portal_context(request, team_id)
    context["team_nav_active"] = "details"
    return render(request, "mentor/team_detail.html", context)


@login_required(login_url="/mentor/login/")
@never_cache
def mentor_team_problem_statement(request, team_id):
    if not _mentor_required(request):
        return redirect("mentor_login")

    context = _build_team_portal_context(request, team_id)
    context["team_nav_active"] = "ps"
    return render(request, "mentor/team_problem_statement.html", context)


@login_required(login_url="/mentor/login/")
@never_cache
def mentor_team_resources(request, team_id):
    if not _mentor_required(request):
        return redirect("mentor_login")

    context = _build_team_portal_context(request, team_id)
    context["team_nav_active"] = "resources"
    return render(request, "mentor/team_resources.html", context)


@login_required(login_url="/mentor/login/")
@never_cache
def mentor_profile(request):
    if not _mentor_required(request):
        return redirect("mentor_login")

    mentor = _get_mentor(request)
    if request.method == "POST":
        form_type = request.POST.get("form_type", "profile")
        if form_type == "password":
            current_password = request.POST.get("current_password", "").strip()
            new_password = request.POST.get("new_password", "").strip()
            confirm_password = request.POST.get("confirm_password", "").strip()

            if not current_password or not new_password or not confirm_password:
                messages.error(request, "All password fields are required.")
            elif not request.user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
            elif new_password != confirm_password:
                messages.error(request, "New password and confirm password do not match.")
            else:
                try:
                    validate_portal_password(new_password, request.user)
                    request.user.set_password(new_password)
                    request.user.save(update_fields=["password"])
                    update_session_auth_hash(request, request.user)
                    messages.success(request, "Password changed successfully.")
                except Exception as exc:
                    for error in (getattr(exc, "messages", None) or [str(exc)]):
                        messages.error(request, error)
        else:
            mentor.expertise = request.POST.get("expertise", mentor.expertise)
            mentor.save()
            request.user.first_name = request.POST.get("first_name", request.user.first_name)
            request.user.last_name = request.POST.get("last_name", request.user.last_name)
            request.user.phone_number = request.POST.get("phone_number", request.user.phone_number)
            if request.FILES.get("profile_image"):
                request.user.profile_image = request.FILES["profile_image"]
            request.user.save()
            messages.success(request, "Profile updated.")
        return redirect("mentor_profile")

    return render(
        request,
        "mentor/profile.html",
        {
            "mentor": mentor,
            "password_help_text": PORTAL_PASSWORD_HELP_TEXT,
            "active_nav": "profile",
            "sidebar_team": _get_sidebar_team(request),
            "team_nav_active": "",
        },
    )


@login_required(login_url="/mentor/login/")
@never_cache
def mentor_messages(request):
    if not _mentor_required(request):
        return redirect("mentor_login")

    mentor = _get_mentor(request)
    from .models import MentorMessage
    from accounts.models import User
    from features.models import TeamMentor, TeamRegistration
    from team.team.models import TeamSupportMessage

    # Assigned team messages
    assigned = TeamMentor.objects.filter(mentor=mentor).values_list("team_id", flat=True)
    reg_teams = TeamRegistration.objects.filter(mentor=mentor).values_list("id", flat=True)
    all_team_ids = set(list(assigned) + list(reg_teams))

    team_support_messages = TeamSupportMessage.objects.filter(
        registration_id__in=all_team_ids
    ).select_related("registration", "registration__team_leader", "sender").order_by("-created_at")

    sent = MentorMessage.objects.filter(sender=request.user).values_list("recipient_id", flat=True)
    received = MentorMessage.objects.filter(recipient=request.user).values_list("sender_id", flat=True)
    conv_user_ids = set(list(sent) + list(received))
    conv_users = User.objects.filter(id__in=conv_user_ids)

    active_tab = request.GET.get('tab', 'teams')

    context = {
        "mentor": mentor,
        "conv_users": conv_users,
        "team_support_messages": team_support_messages,
        "active_tab": active_tab,
        "active_nav": "messages",
        "sidebar_team": _get_sidebar_team(request),
        "team_nav_active": "",
    }
    return render(request, "mentor/messages.html", context)


@login_required(login_url="/mentor/login/")
@require_POST
def mentor_reply_team_message(request, message_id):
    if not _mentor_required(request):
        return redirect("mentor_login")

    from team.team.models import TeamSupportMessage, TeamNotification
    msg = get_object_or_404(TeamSupportMessage, id=message_id)

    reply_text = request.POST.get("reply", "").strip()
    status = request.POST.get("status", "reviewed").strip()
    if reply_text:
        mentor_name = request.user.get_full_name() or request.user.username
        msg.admin_reply = f"[Mentor ({mentor_name})]: {reply_text}"
        msg.status = status
        msg.save(update_fields=["admin_reply", "status", "updated_at"])

        if msg.registration and msg.registration.team_leader:
            try:
                TeamNotification.objects.create(
                    team_leader=msg.registration.team_leader,
                    registration=msg.registration,
                    notif_type="mentor_accepted",
                    title=f"Reply from Mentor on '{msg.subject}'",
                    body=f"Mentor Response: {reply_text}",
                )
            except Exception as e:
                logger.error(f"Failed to create TeamNotification: {e}")
        messages.success(request, "Reply sent to team successfully.")
    else:
        msg.status = status
        msg.save(update_fields=["status", "updated_at"])
        messages.success(request, "Message status updated.")
    return redirect(f"{reverse('mentor_messages')}?tab=teams")


@login_required(login_url="/mentor/login/")
def mentor_conversation(request, user_id):
    if not _mentor_required(request):
        return redirect("mentor_login")

    from .models import MentorMessage
    from accounts.models import User

    other_user = get_object_or_404(User, id=user_id)
    thread = MentorMessage.objects.filter(
        sender__in=[request.user, other_user],
        recipient__in=[request.user, other_user],
    ).order_by("sent_at")
    MentorMessage.objects.filter(sender=other_user, recipient=request.user, is_read=False).update(is_read=True)

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            MentorMessage.objects.create(sender=request.user, recipient=other_user, body=body)
        return redirect("mentor_conversation", user_id=user_id)

    context = {
        "mentor": _get_mentor(request),
        "other_user": other_user,
        "thread": thread,
        "active_nav": "messages",
        "sidebar_team": _get_sidebar_team(request),
        "team_nav_active": "",
    }
    return render(request, "mentor/conversation.html", context)


def _build_team_portal_context(request, team_id):
    from features.models import Documentation, Podcast, Team, TeamDocument, TeamMember

    team = get_object_or_404(
        Team.objects.select_related("hackathon", "team_leader", "problem_statement", "institution"),
        id=team_id,
    )
    request.session["mentor_current_team_id"] = team.id

    members = TeamMember.objects.filter(team=team).select_related("user")
    documents = TeamDocument.objects.filter(team=team).select_related("uploaded_by").order_by("-uploaded_at")

    problem_statement = team.problem_statement
    podcasts = Podcast.objects.none()
    documentaries = Documentation.objects.none()
    if problem_statement:
        podcasts = Podcast.objects.filter(
            hackathon=team.hackathon,
            problem_statement=problem_statement,
            is_published=True,
            publication_scope="internal",
        ).order_by("-created_at")
        documentaries = Documentation.objects.filter(
            hackathon=team.hackathon,
            problem_statement=problem_statement,
            is_published=True,
        ).order_by("-created_at")

    return {
        "mentor": _get_mentor(request),
        "team": team,
        "members": members,
        "documents": documents,
        "problem_statement": problem_statement,
        "podcasts": podcasts,
        "documentaries": documentaries,
        "resource_count": podcasts.count() + documentaries.count(),
        "active_nav": "dashboard",
        "sidebar_team": team,
    }
