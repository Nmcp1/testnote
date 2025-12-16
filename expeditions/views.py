import random
import string
from datetime import timedelta
from expeditions.services.daily_payout_guard import try_pay_daily_top
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    ExpeditionLobby,
    ExpeditionParticipant,
    ExpeditionLobbyStatus,
    ExpeditionPhase,
    ExpeditionDailyEarning,
    ExpeditionRunResult,
)
from .services.player_stats import expedition_initial_stats


DAILY_CAP = 500


def _code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _local_day():
    return timezone.localdate()


def _user_total_coins(user):
    # Tu base.html usa user_coins desde context processor normalmente,
    # pero para el HUB lo mostramos explícito también.
    from notes.views import get_or_create_profile
    return get_or_create_profile(user).coins


@login_required
def expeditions_hub(request):
    try_pay_daily_top()
    today = _local_day()

    earning, _ = ExpeditionDailyEarning.objects.get_or_create(
        user=request.user,
        day=today,
        defaults={"earned_coins": 0},
    )
    earned_today = earning.earned_coins
    total_coins = _user_total_coins(request.user)

    lobbies = (
        ExpeditionLobby.objects
        .order_by("-created_at")[:20]
    )

    # TOP diario (hoy)
    top = list(
        ExpeditionRunResult.objects
        .filter(day=today)
        .order_by("-floor_reached", "created_at")[:5]
    )

    # Para mostrar nombres en template
    # (evitamos N+1: sacamos ids y consultamos users)
    all_ids = set()
    for r in top:
        for uid in (r.member_ids or []):
            all_ids.add(uid)

    users_map = {}
    if all_ids:
        from django.contrib.auth.models import User
        for u in User.objects.filter(id__in=list(all_ids)):
            users_map[u.id] = u.username

    top_view = []
    for idx, r in enumerate(top, start=1):
        members = [users_map.get(uid, f"User#{uid}") for uid in (r.member_ids or [])]
        top_view.append({
            "rank": idx,
            "floor": r.floor_reached,
            "members": members,
            "lobby_id": r.lobby_id,
        })

    return render(request, "expeditions/hub.html", {
        "lobbies": lobbies,
        "earned_today": earned_today,
        "daily_cap": DAILY_CAP,
        "total_coins": total_coins,
        "top_daily": top_view,
        "top_day": today,
    })


@login_required
def expeditions_daily_top(request):
    """
    Vista del top diario (por defecto hoy, opcional ?day=YYYY-MM-DD)
    """
    day_str = request.GET.get("day")
    if day_str:
        try:
            day = timezone.datetime.fromisoformat(day_str).date()
        except Exception:
            day = _local_day()
    else:
        day = _local_day()

    results = list(
        ExpeditionRunResult.objects
        .filter(day=day)
        .order_by("-floor_reached", "created_at")[:50]
    )

    all_ids = set()
    for r in results:
        for uid in (r.member_ids or []):
            all_ids.add(uid)

    users_map = {}
    if all_ids:
        from django.contrib.auth.models import User
        for u in User.objects.filter(id__in=list(all_ids)):
            users_map[u.id] = u.username

    rows = []
    for idx, r in enumerate(results, start=1):
        members = [users_map.get(uid, f"User#{uid}") for uid in (r.member_ids or [])]
        rows.append({
            "rank": idx,
            "floor": r.floor_reached,
            "members": members,
            "lobby_id": r.lobby_id,
            "created_at": r.created_at,
        })

    return render(request, "expeditions/top_daily.html", {
        "day": day,
        "rows": rows,
    })


# ====== Tu create/join/start/lobby_view quedan como los tenías ======

@login_required
def expeditions_create(request):
    return redirect("expeditions_create_impl")


@login_required
@transaction.atomic
def create_lobby(request):
    active = ExpeditionLobby.objects.select_for_update().filter(
        status__in=[ExpeditionLobbyStatus.WAITING, ExpeditionLobbyStatus.RUNNING]
    ).count()
    if active >= 3:
        messages.error(request, "Ya hay 3 expediciones activas. Espera a que termine una.")
        return redirect("expeditions_hub")

    lobby = ExpeditionLobby.objects.create(
        code=_code(),
        creator=request.user,
        status=ExpeditionLobbyStatus.WAITING,
        phase=ExpeditionPhase.WAITING,
        floor=1,
    )

    s = expedition_initial_stats(request.user)

    ExpeditionParticipant.objects.create(
        lobby=lobby,
        user=request.user,
        base_hp=s["base_hp"],
        base_attack=s["base_attack"],
        base_defense=s["base_defense"],
        max_hp=s["max_hp"],
        current_hp=s["max_hp"],
        attack=s["attack"],
        defense=s["defense"],
    )

    return redirect("expeditions_lobby", lobby_id=lobby.id)


@login_required
@transaction.atomic
def join_lobby(request, lobby_id: int):
    lobby = get_object_or_404(ExpeditionLobby.objects.select_for_update(), id=lobby_id)

    if lobby.status != ExpeditionLobbyStatus.WAITING:
        messages.error(request, "Esta expedición ya empezó o terminó.")
        return redirect("expeditions_hub")

    if lobby.participants.count() >= 3:
        messages.error(request, "Lobby lleno (máx 3).")
        return redirect("expeditions_hub")

    s = expedition_initial_stats(request.user)

    ExpeditionParticipant.objects.get_or_create(
        lobby=lobby,
        user=request.user,
        defaults={
            "base_hp": s["base_hp"],
            "base_attack": s["base_attack"],
            "base_defense": s["base_defense"],
            "max_hp": s["max_hp"],
            "current_hp": s["max_hp"],
            "attack": s["attack"],
            "defense": s["defense"],
            "is_alive": True,
        },
    )

    return redirect("expeditions_lobby", lobby_id=lobby.id)


@login_required
def lobby_view(request, lobby_id: int):
    lobby = get_object_or_404(ExpeditionLobby, id=lobby_id)
    return render(request, "expeditions/lobby.html", {"lobby": lobby})


@login_required
@transaction.atomic
def start_expedition(request, lobby_id: int):
    lobby = get_object_or_404(ExpeditionLobby.objects.select_for_update(), id=lobby_id)

    if lobby.creator_id != request.user.id:
        messages.error(request, "Solo el creador puede iniciar.")
        return redirect("expeditions_lobby", lobby_id=lobby.id)

    if lobby.status != ExpeditionLobbyStatus.WAITING:
        return redirect("expeditions_lobby", lobby_id=lobby.id)

    lobby.status = ExpeditionLobbyStatus.RUNNING
    lobby.started_at = timezone.now()
    lobby.save(update_fields=["status", "started_at"])

    lobby.set_phase(ExpeditionPhase.VOTE_ORDER_1, seconds=20)
    return redirect("expeditions_lobby", lobby_id=lobby.id)

@require_POST
@login_required
@transaction.atomic
def leave_lobby(request, lobby_id: int):
    lobby = get_object_or_404(ExpeditionLobby.objects.select_for_update(), id=lobby_id)

    # Solo permitir salir antes de iniciar
    if lobby.status != ExpeditionLobbyStatus.WAITING:
        messages.error(request, "No puedes salir: la expedición ya comenzó.")
        return redirect("expeditions_lobby", lobby_id=lobby.id)

    # Borrar participante si existe
    ExpeditionParticipant.objects.filter(lobby=lobby, user=request.user).delete()

    # Si ya no quedan jugadores, eliminar lobby completo
    remaining = list(
        lobby.participants.select_related("user").order_by("joined_at")
    )

    if len(remaining) == 0:
        lobby.delete()
        messages.info(request, "Saliste del lobby. El lobby se eliminó porque quedó vacío.")
        return redirect("expeditions_hub")

    # Si el creador salió, reasignar creator al primer jugador restante
    if lobby.creator_id == request.user.id:
        lobby.creator = remaining[0].user
        lobby.save(update_fields=["creator"])
        messages.info(request, f"Saliste del lobby. Nuevo creador: {lobby.creator.username}")
    else:
        messages.info(request, "Saliste del lobby.")

    return redirect("expeditions_hub")