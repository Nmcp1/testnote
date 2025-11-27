import random

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q, Count
from django.urls import reverse
from django.http import HttpResponseForbidden
from django.contrib import messages

from django.contrib.auth.models import Group, User

from .models import (
    Note,
    NoteLike,
    Notification,
    InvitationCode,
    UserProfile,
    MineGameResult,
)
from .forms import (
    NoteForm,
    PrivateNoteForm,
    RegistrationForm,
    NoteReplyForm,
)

MODERATOR_GROUP_NAME = "moderador"
MINE_GAME_SESSION_KEY = "mine_game_state"


def ensure_moderator_group_exists():
    Group.objects.get_or_create(name=MODERATOR_GROUP_NAME)


def user_is_moderator(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    ensure_moderator_group_exists()
    return user.groups.filter(name__iexact=MODERATOR_GROUP_NAME).exists()


def home(request):
    orden = request.GET.get("orden", "fecha")

    notes_qs = (
        Note.objects.filter(recipient__isnull=True)
        .select_related("author")
        .annotate(
            likes_count=Count("likes", distinct=True),
            replies_count=Count("replies", distinct=True),
        )
    )

    if orden == "likes":
        notes_qs = notes_qs.order_by("-likes_count", "-created_at")
    else:
        notes_qs = notes_qs.order_by("-created_at")

    paginator = Paginator(notes_qs, 9)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    form = None
    liked_ids = set()

    if request.user.is_authenticated:
        liked_ids = set(
            NoteLike.objects.filter(
                user=request.user,
                note__in=page_obj.object_list,
            ).values_list("note_id", flat=True)
        )

        if request.method == "POST":
            form = NoteForm(request.POST)
            if form.is_valid():
                note = form.save(commit=False)
                note.author = request.user
                note.recipient = None
                note.save()
                return redirect(f"{request.path}?orden={orden}")
        else:
            form = NoteForm()

    context = {
        "form": form,
        "page_obj": page_obj,
        "liked_ids": liked_ids,
        "orden": orden,
    }
    return render(request, "notes/home.html", context)


def note_detail(request, note_id):
    note_qs = (
        Note.objects.filter(pk=note_id, recipient__isnull=True)
        .select_related("author")
        .annotate(
            likes_count=Count("likes", distinct=True),
            replies_count=Count("replies", distinct=True),
        )
    )
    note = get_object_or_404(note_qs)

    replies = note.replies.select_related("author").order_by("created_at")

    user_liked = False
    if request.user.is_authenticated:
        user_liked = NoteLike.objects.filter(note=note, user=request.user).exists()

    if request.method == "POST":
        if not request.user.is_authenticated:
            login_url = f"{reverse('login')}?next={request.path}"
            return redirect(login_url)

        form = NoteReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.note = note
            reply.author = request.user
            reply.save()

            if note.author != request.user:
                Notification.objects.create(
                    user=note.author,
                    message=f"{request.user.username} comentó tu nota pública.",
                    url=reverse("note_detail", args=[note.id]),
                )

            return redirect(request.path)
    else:
        form = NoteReplyForm() if request.user.is_authenticated else None

    context = {
        "note": note,
        "replies": replies,
        "user_liked": user_liked,
        "form": form,
    }
    return render(request, "notes/note_detail.html", context)


@login_required
def private_notes(request):
    filtro = request.GET.get("filtro", "recibidas")

    if filtro == "recibidas":
        notes_qs = Note.objects.filter(recipient=request.user)
    elif filtro == "enviadas":
        notes_qs = Note.objects.filter(
            author=request.user,
            recipient__isnull=False,
        )
    else:
        notes_qs = Note.objects.filter(
            Q(recipient=request.user) |
            Q(author=request.user, recipient__isnull=False)
        )

    notes_qs = notes_qs.select_related("author", "recipient")

    paginator = Paginator(notes_qs, 9)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if request.method == "POST":
        form = PrivateNoteForm(request.POST, user=request.user)
        if form.is_valid():
            note = form.save(commit=False)
            note.author = request.user
            note.save()

            if note.recipient and note.recipient != request.user:
                Notification.objects.create(
                    user=note.recipient,
                    message=f"{request.user.username} te envió una nota privada.",
                    url=reverse("private_notes"),
                )

            return redirect("private_notes")
    else:
        form = PrivateNoteForm(user=request.user)

    context = {
        "form": form,
        "page_obj": page_obj,
        "filtro": filtro,
    }
    return render(request, "notes/private_notes.html", context)


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()

            invitation = getattr(form, "invitation_instance", None)
            if invitation is not None:
                invitation.used_by = user
                invitation.used_at = timezone.now()
                invitation.save()

            auth_login(request, user)
            return redirect("home")
    else:
        form = RegistrationForm()

    return render(request, "registration/register.html", {"form": form})


@require_POST
@login_required
def toggle_like(request, note_id):
    note = get_object_or_404(Note, pk=note_id, recipient__isnull=True)

    like, created = NoteLike.objects.get_or_create(
        note=note,
        user=request.user,
    )

    if created:
        if note.author != request.user:
            Notification.objects.create(
                user=note.author,
                message=f"{request.user.username} dio like a tu nota pública.",
                url=reverse("note_detail", args=[note.id]),
            )
    else:
        like.delete()

    next_url = request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)


@login_required
def notifications(request):
    notifications_qs = request.user.notifications.all()
    notifications_qs.filter(is_read=False).update(is_read=True)

    context = {
        "notifications": notifications_qs,
    }
    return render(request, "notes/notifications.html", context)


@login_required
def invitation_admin(request):
    if not user_is_moderator(request.user):
        return HttpResponseForbidden("No tienes permiso para ver esta página.")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            InvitationCode.objects.create(created_by=request.user)
            messages.success(request, "Se creó un nuevo código de invitación.")
            return redirect("invitation_admin")

        elif action == "delete":
            code_id = request.POST.get("code_id")
            try:
                code = InvitationCode.objects.get(
                    id=code_id,
                    used_by__isnull=True,
                )
                code.delete()
                messages.success(request, "Código eliminado correctamente.")
            except InvitationCode.DoesNotExist:
                messages.error(
                    request,
                    "No se pudo eliminar el código (puede que ya haya sido usado).",
                )
            return redirect("invitation_admin")

    unused_codes = InvitationCode.objects.filter(
        used_by__isnull=True
    ).select_related("created_by").order_by("-created_at")

    used_codes = InvitationCode.objects.filter(
        used_by__isnull=False
    ).select_related("created_by", "used_by").order_by("-used_at", "-created_at")

    context = {
        "unused_codes": unused_codes,
        "used_codes": used_codes,
    }
    return render(request, "notes/invitation_admin.html", context)


@login_required
def moderator_panel(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Solo el superusuario puede gestionar moderadores.")

    ensure_moderator_group_exists()
    mod_group = Group.objects.get(name=MODERATOR_GROUP_NAME)

    if request.method == "POST":
        action = request.POST.get("action")
        user_id = request.POST.get("user_id")

        try:
            target_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, "El usuario no existe.")
            return redirect("moderator_panel")

        if action == "add":
            if mod_group in target_user.groups.all():
                messages.info(request, f"{target_user.username} ya es moderador.")
            else:
                target_user.groups.add(mod_group)
                messages.success(request, f"{target_user.username} ahora es moderador.")

        elif action == "remove":
            if target_user == request.user:
                messages.error(request, "No puedes quitarte el rol de moderador a ti mismo.")
            elif mod_group not in target_user.groups.all():
                messages.info(request, f"{target_user.username} no es moderador.")
            else:
                target_user.groups.remove(mod_group)
                messages.success(request, f"{target_user.username} ya no es moderador.")

        return redirect("moderator_panel")

    moderators = User.objects.filter(
        groups__name__iexact=MODERATOR_GROUP_NAME
    ).order_by("username")

    non_moderators = User.objects.exclude(
        groups__name__iexact=MODERATOR_GROUP_NAME
    ).order_by("username")

    context = {
        "moderators": moderators,
        "non_moderators": non_moderators,
    }
    return render(request, "notes/moderator_panel.html", context)


def leaderboard(request):
    """
    Ranking de usuarios por cantidad de monedas (perfil).
    """
    profiles = (
        UserProfile.objects
        .select_related("user")
        .order_by("-coins", "user__username")[:50]
    )

    current_user_profile = None
    if request.user.is_authenticated:
        current_user_profile, _ = UserProfile.objects.get_or_create(user=request.user)

    context = {
        "profiles": profiles,
        "current_user_profile": current_user_profile,
    }
    return render(request, "notes/leaderboard.html", context)


def _new_mine_game_state():
    rows = 10
    cols = 10
    mines_count = 15

    all_cells = [f"{r}-{c}" for r in range(rows) for c in range(cols)]
    mines = random.sample(all_cells, mines_count)

    return {
        "rows": rows,
        "cols": cols,
        "mines": mines,
        "revealed": [],
        "score": 0,
        "status": "playing",  # playing / lost
        "hit_cell": None,
    }


@login_required
def mine_game(request):
    """
    Minijuego de 10x10 con 15 minas.
    - Casillas seguras: verde claro (+1 punto).
    - Mina: roja, termina el juego y deja el puntaje en 0.
    - Botón "Retirarse": guarda partida y otorga 1 moneda por cada 10 puntos.
    - A la derecha: top 10 mayores puntuaciones y últimas 10 partidas.
    """
    state = request.session.get(MINE_GAME_SESSION_KEY)
    if not state:
        state = _new_mine_game_state()
        request.session[MINE_GAME_SESSION_KEY] = state

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "click" and state["status"] == "playing":
            cell = request.POST.get("cell")
            if cell and cell not in state["revealed"]:
                if cell in state["mines"]:
                    state["status"] = "lost"
                    state["hit_cell"] = cell
                    state["score"] = 0

                    MineGameResult.objects.create(
                        user=request.user,
                        score=0,
                        result=MineGameResult.RESULT_BOMB,
                    )
                    messages.error(
                        request,
                        "💥 Pisaste una bomba. Perdiste todos tus puntos."
                    )
                else:
                    state["revealed"].append(cell)
                    state["score"] += 1

            request.session[MINE_GAME_SESSION_KEY] = state

        elif action == "retire" and state["status"] == "playing":
            score = int(state.get("score", 0))

            MineGameResult.objects.create(
                user=request.user,
                score=score,
                result=MineGameResult.RESULT_RETIRE,
            )

            bonus = score // 10
            if bonus > 0:
                profile, _ = UserProfile.objects.get_or_create(user=request.user)
                profile.coins += bonus
                profile.save()
                messages.success(
                    request,
                    f"Te retiraste con {score} puntos. Has ganado {bonus} moneda(s).",
                )
            else:
                messages.info(
                    request,
                    f"Te retiraste con {score} puntos. No se otorgan monedas.",
                )

            state = _new_mine_game_state()
            request.session[MINE_GAME_SESSION_KEY] = state

        elif action == "new_game":
            state = _new_mine_game_state()
            request.session[MINE_GAME_SESSION_KEY] = state

    rows = state["rows"]
    cols = state["cols"]

    # Lista plana de celdas para CSS Grid (10x10)
    cells = [f"{r}-{c}" for r in range(rows) for c in range(cols)]

    revealed_cells = state["revealed"]
    hit_cell = state["hit_cell"]
    game_status = state["status"]
    current_score = state["score"]

    top_scores = (
        MineGameResult.objects
        .select_related("user")
        .order_by("-score", "-finished_at")[:10]
    )

    last_games = (
        MineGameResult.objects
        .select_related("user")
        .order_by("-finished_at")[:10]
    )

    context = {
        "cells": cells,
        "revealed_cells": revealed_cells,
        "hit_cell": hit_cell,
        "game_status": game_status,
        "current_score": current_score,
        "top_scores": top_scores,
        "last_games": last_games,
    }
    return render(request, "notes/mine_game.html", context)
