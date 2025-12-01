import random
from math import pow
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q, Count, Max
from django.db import transaction, IntegrityError
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
    CombatItem,
    TowerProgress,
    TowerBattleResult,
    ItemRarity,
    ItemSlot,
    ItemSource,
    GachaProbability,
    PvpRanking,
    PvpBattleLog,
    Trade,
    WorldBossCycle,
    WorldBossParticipant,
    MiniBossParticipant,
    MiniBossLobby,
    MarketListing,

)
from .forms import (
    NoteForm,
    PrivateNoteForm,
    RegistrationForm,
    NoteReplyForm,
)

MODERATOR_GROUP_NAME = "moderador"
MINE_GAME_SESSION_KEY = "mine_game_state"
GACHA_LAST_SLOT_SESSION_KEY = "rpg_gacha_last_slot"



def ensure_moderator_group_exists():
    Group.objects.get_or_create(name=MODERATOR_GROUP_NAME)


def user_is_moderator(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    ensure_moderator_group_exists()
    return user.groups.filter(name__iexact=MODERATOR_GROUP_NAME).exists()


def get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


# =================
# NOTAS PÚBLICAS / PRIVADAS
# =================

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


# =================
# LEADERBOARD MONEDAS
# =================

def leaderboard(request):
    profiles = (
        UserProfile.objects
        .select_related("user")
        .order_by("-coins", "user__username")[:50]
    )

    current_user_profile = None
    if request.user.is_authenticated:
        current_user_profile = get_or_create_profile(request.user)

    context = {
        "profiles": profiles,
        "current_user_profile": current_user_profile,
    }
    return render(request, "notes/leaderboard.html", context)


# =================
# JUEGO DE MINAS
# =================

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

            bonus = score // 5
            if bonus > 0:
                profile = get_or_create_profile(request.user)
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


# =================
# RPG — GACHA CONFIG + STATS
# =================

# defaults por si la tabla está vacía
DEFAULT_GACHA_PROBS = [
    (ItemRarity.BASIC, 0.80),
    (ItemRarity.UNCOMMON, 0.15),
    (ItemRarity.SPECIAL, 0.04),
    (ItemRarity.EPIC, 0.009),
    (ItemRarity.LEGENDARY, 0.0009),
    (ItemRarity.MYTHIC, 0.00009),
    (ItemRarity.ASCENDED, 0.00001),
]


def get_gacha_probs():
    """
    Devuelve una lista de tuplas (rarity, prob) SIEMPRE ordenada
    por calidad: Básica → Poco común → Especial → Épica →
    Legendaria → Mítica → Ascendida.
    """
    qs = GachaProbability.objects.all()
    if not qs.exists():
        for rarity, prob in DEFAULT_GACHA_PROBS:
            GachaProbability.objects.create(rarity=rarity, probability=prob)
        qs = GachaProbability.objects.all()

    # Mapeamos lo que haya en BD
    db_map = {row.rarity: row.probability for row in qs}

    ordered = []
    for rarity, default_prob in DEFAULT_GACHA_PROBS:
        ordered.append((rarity, db_map.get(rarity, default_prob)))
    return ordered


def roll_rarity():
    probs = get_gacha_probs()
    r = random.random()
    acumulado = 0.0
    for rarity, prob in probs:
        acumulado += prob
        if r <= acumulado:
            return rarity
    return probs[-1][0]


SLOT_LABELS = {
    ItemSlot.WEAPON: "Espada",
    ItemSlot.HELMET: "Casco",
    ItemSlot.ARMOR: "Armadura",
    ItemSlot.PANTS: "Pantalones",
    ItemSlot.BOOTS: "Botas",
    ItemSlot.SHIELD: "Escudo",
    ItemSlot.AMULET: "Amuleto",
}

# Tablas de stats por rareza
WEAPON_ATK = {
    ItemRarity.BASIC: (5, 15),
    ItemRarity.UNCOMMON: (12, 35),
    ItemRarity.SPECIAL: (30, 65),
    ItemRarity.EPIC: (60, 130),
    ItemRarity.LEGENDARY: (120, 240),
    ItemRarity.MYTHIC: (230, 400),
    ItemRarity.ASCENDED: (390, 650),
}

ARMOR_DEF = {
    ItemRarity.BASIC: (2, 6),
    ItemRarity.UNCOMMON: (5, 15),
    ItemRarity.SPECIAL: (12, 28),
    ItemRarity.EPIC: (25, 55),
    ItemRarity.LEGENDARY: (50, 105),
    ItemRarity.MYTHIC: (90, 180),
    ItemRarity.ASCENDED: (160, 300),
}

SHIELD_DEF = {
    ItemRarity.BASIC: (2, 5),
    ItemRarity.UNCOMMON: (5, 12),
    ItemRarity.SPECIAL: (10, 20),
    ItemRarity.EPIC: (18, 40),
    ItemRarity.LEGENDARY: (35, 70),
    ItemRarity.MYTHIC: (60, 120),
    ItemRarity.ASCENDED: (100, 200),
}

SHIELD_HP = {
    ItemRarity.BASIC: (20, 40),
    ItemRarity.UNCOMMON: (35, 70),
    ItemRarity.SPECIAL: (60, 120),
    ItemRarity.EPIC: (100, 200),
    ItemRarity.LEGENDARY: (160, 300),
    ItemRarity.MYTHIC: (260, 450),
    ItemRarity.ASCENDED: (420, 700),
}

LIGHT_HP = {
    ItemRarity.BASIC: (15, 30),
    ItemRarity.UNCOMMON: (25, 50),
    ItemRarity.SPECIAL: (40, 80),
    ItemRarity.EPIC: (70, 140),
    ItemRarity.LEGENDARY: (120, 240),
    ItemRarity.MYTHIC: (200, 380),
    ItemRarity.ASCENDED: (350, 600),
}

LIGHT_DEF = {
    ItemRarity.BASIC: (0, 1),
    ItemRarity.UNCOMMON: (1, 3),
    ItemRarity.SPECIAL: (2, 6),
    ItemRarity.EPIC: (5, 12),
    ItemRarity.LEGENDARY: (10, 22),
    ItemRarity.MYTHIC: (20, 40),
    ItemRarity.ASCENDED: (35, 60),
}

LIGHT_SPEED = {
    ItemRarity.BASIC: (0, 1),
    ItemRarity.UNCOMMON: (1, 2),
    ItemRarity.SPECIAL: (1, 3),
    ItemRarity.EPIC: (2, 5),
    ItemRarity.LEGENDARY: (3, 7),
    ItemRarity.MYTHIC: (5, 10),
    ItemRarity.ASCENDED: (8, 15),
}

AMULET_CRIT = {
    ItemRarity.BASIC: (1, 2),
    ItemRarity.UNCOMMON: (3, 5),
    ItemRarity.SPECIAL: (5, 9),
    ItemRarity.EPIC: (7, 15),
    ItemRarity.LEGENDARY: (12, 22),
    ItemRarity.MYTHIC: (18, 25),
    ItemRarity.ASCENDED: (20, 30),
}

AMULET_DODGE = AMULET_CRIT.copy()

AMULET_SPEED = {
    ItemRarity.BASIC: (0, 1),
    ItemRarity.UNCOMMON: (1, 3),
    ItemRarity.SPECIAL: (2, 5),
    ItemRarity.EPIC: (4, 9),
    ItemRarity.LEGENDARY: (7, 14),
    ItemRarity.MYTHIC: (12, 20),
    ItemRarity.ASCENDED: (18, 30),
}

AMULET_ATK = {
    ItemRarity.BASIC: (1, 3),
    ItemRarity.UNCOMMON: (3, 7),
    ItemRarity.SPECIAL: (6, 15),
    ItemRarity.EPIC: (12, 28),
    ItemRarity.LEGENDARY: (25, 50),
    ItemRarity.MYTHIC: (45, 80),
    ItemRarity.ASCENDED: (75, 130),
}

RARITY_SELL_VALUE = {
    ItemRarity.BASIC: 2,
    ItemRarity.UNCOMMON: 20,
    ItemRarity.SPECIAL: 50,
    ItemRarity.EPIC: 100,
    ItemRarity.LEGENDARY: 300,
    ItemRarity.MYTHIC: 500,
    ItemRarity.ASCENDED: 1000,
}

RARITY_ORDER = {
    ItemRarity.BASIC: 0,
    ItemRarity.UNCOMMON: 1,
    ItemRarity.SPECIAL: 2,
    ItemRarity.EPIC: 3,
    ItemRarity.LEGENDARY: 4,
    ItemRarity.MYTHIC: 5,
    ItemRarity.ASCENDED: 6,
}

def roll_range(rng, from_gacha):
    mn, mx = rng
    if not from_gacha:
        return mn
    if mn == mx:
        return mn
    return random.randint(mn, mx)


def generate_item_stats(slot, rarity, from_gacha):
    atk = 0
    df = 0
    hp = 0
    crit = 0.0
    dodge = 0.0
    speed = 0

    if slot == ItemSlot.WEAPON:
        atk = roll_range(WEAPON_ATK[rarity], from_gacha)

    elif slot == ItemSlot.ARMOR:
        df = roll_range(ARMOR_DEF[rarity], from_gacha)

    elif slot == ItemSlot.SHIELD:
        df = roll_range(SHIELD_DEF[rarity], from_gacha)
        hp = roll_range(SHIELD_HP[rarity], from_gacha)

    elif slot in (ItemSlot.HELMET, ItemSlot.PANTS, ItemSlot.BOOTS):
        hp = roll_range(LIGHT_HP[rarity], from_gacha)
        df = roll_range(LIGHT_DEF[rarity], from_gacha)
        speed = roll_range(LIGHT_SPEED[rarity], from_gacha)

    elif slot == ItemSlot.AMULET:
        atk = roll_range(AMULET_ATK[rarity], from_gacha)
        crit = float(roll_range(AMULET_CRIT[rarity], from_gacha))
        dodge = float(roll_range(AMULET_DODGE[rarity], from_gacha))
        speed = roll_range(AMULET_SPEED[rarity], from_gacha)

    return {
        "attack": atk,
        "defense": df,
        "hp": hp,
        "crit_chance": crit,
        "dodge_chance": dodge,
        "speed": speed,
    }



def get_total_stats(user):
    profile = get_or_create_profile(user)

    base_hp = 100
    base_atk = 10
    base_def = 0
    base_crit = 0.0
    base_dodge = 0.0
    base_speed = 0

    total_hp = base_hp
    total_atk = base_atk
    total_def = base_def
    total_crit = base_crit
    total_dodge = base_dodge
    total_speed = base_speed

    mapping = [
        ("equipped_weapon", ItemSlot.WEAPON),
        ("equipped_helmet", ItemSlot.HELMET),
        ("equipped_armor", ItemSlot.ARMOR),
        ("equipped_pants", ItemSlot.PANTS),
        ("equipped_boots", ItemSlot.BOOTS),
        ("equipped_shield", ItemSlot.SHIELD),
        ("equipped_amulet1", ItemSlot.AMULET),
        ("equipped_amulet2", ItemSlot.AMULET),
        ("equipped_amulet3", ItemSlot.AMULET),
    ]

    for field_name, _slot in mapping:
        item = getattr(profile, field_name, None)
        if item:
            total_hp += item.hp
            total_atk += item.attack
            total_def += item.defense
            total_crit += item.crit_chance
            total_dodge += item.dodge_chance
            total_speed += item.speed

    return {
        "hp": total_hp,
        "attack": total_atk,
        "defense": total_def,
        "crit_chance": total_crit,
        "dodge_chance": total_dodge,
        "speed": total_speed,
    }


def enemy_stats_for_floor(floor):
    base_hp = 40
    base_atk = 8
    base_def = 2

    hp = int(base_hp * pow(1.18, floor))
    atk = int(base_atk * pow(1.14, floor))
    df = int(base_def * pow(1.12, floor))

    return {
        "hp": max(hp, 1),
        "attack": max(atk, 1),
        "defense": max(df, 0),
    }


def simulate_battle(user_stats, enemy_stats, max_turns=50):
    log_lines = []

    player_hp = user_stats["hp"]
    player_atk = user_stats["attack"]
    player_def = user_stats["defense"]
    player_crit = user_stats["crit_chance"]
    player_dodge = user_stats["dodge_chance"]
    player_speed = user_stats["speed"]

    enemy_hp = enemy_stats["hp"]
    enemy_atk = enemy_stats["attack"]
    enemy_def = enemy_stats["defense"]
    enemy_speed = 0

    for turn in range(1, max_turns + 1):
        if player_hp <= 0 or enemy_hp <= 0:
            break

        log_lines.append(f"TURNO {turn}:")

        if player_speed > enemy_speed:
            first = "player"
        elif enemy_speed > player_speed:
            first = "enemy"
        else:
            first = random.choice(["player", "enemy"])

        def do_attack(attacker_name):
            nonlocal player_hp, enemy_hp
            if attacker_name == "player":
                dmg = max(1, player_atk - enemy_def)
                crit = random.random() < (player_crit / 100.0)
                if crit:
                    dmg *= 2
                enemy_hp -= dmg
                if crit:
                    log_lines.append(f"- El jugador hace {dmg} de daño CRÍTICO al enemigo.")
                else:
                    log_lines.append(f"- El jugador hace {dmg} de daño al enemigo.")
            else:
                if random.random() < (player_dodge / 100.0):
                    log_lines.append("- El enemigo ataca pero el jugador ESQUIVA el golpe.")
                    return
                dmg = max(1, enemy_atk - player_def)
                player_hp -= dmg
                log_lines.append(f"- El enemigo hace {dmg} de daño al jugador.")

        if first == "player":
            do_attack("player")
            if enemy_hp <= 0:
                log_lines.append("El enemigo ha sido derrotado.")
                break
            do_attack("enemy")
            if player_hp <= 0:
                log_lines.append("El jugador ha sido derrotado.")
                break
        else:
            do_attack("enemy")
            if player_hp <= 0:
                log_lines.append("El jugador ha sido derrotado.")
                break
            do_attack("player")
            if enemy_hp <= 0:
                log_lines.append("El enemigo ha sido derrotado.")
                break

    victory = player_hp > 0 and enemy_hp <= 0
    return victory, log_lines


@login_required
def rpg_hub(request):
    profile = get_or_create_profile(request.user)
    stats = get_total_stats(request.user)
    tower, _ = TowerProgress.objects.get_or_create(user=request.user)

    context = {
        "profile": profile,
        "stats": stats,
        "tower": tower,
    }
    return render(request, "notes/rpg_hub.html", context)


@login_required
def rpg_shop(request):
    profile = get_or_create_profile(request.user)
    created_item = None

    if request.method == "POST":
        slot_code = request.POST.get("slot")
        try:
            slot = ItemSlot(slot_code)
        except ValueError:
            messages.error(request, "Slot inválido.")
            return redirect("rpg_shop")

        COST = 5
        if profile.coins < COST:
            messages.error(request, "No tienes suficientes monedas.")
            return redirect("rpg_shop")

        rarity = ItemRarity.BASIC
        stats = generate_item_stats(slot, rarity, from_gacha=False)
        name = f"{SLOT_LABELS[slot]} básica"

        item = CombatItem.objects.create(
            owner=request.user,
            name=name,
            slot=slot,
            rarity=rarity,
            source=ItemSource.SHOP,
            attack=stats["attack"],
            defense=stats["defense"],
            hp=stats["hp"],
            crit_chance=stats["crit_chance"],
            dodge_chance=stats["dodge_chance"],
            speed=stats["speed"],
        )

        profile.coins -= COST
        profile.save()

        created_item = item
        messages.success(
            request,
            f"Has comprado {item.name} (ATK {item.attack}, DEF {item.defense}, HP {item.hp}).",
        )

    items = CombatItem.objects.filter(owner=request.user).order_by("-created_at")

    context = {
        "profile": profile,
        "items": items,
        "created_item": created_item,
    }
    return render(request, "notes/rpg_shop.html", context)


@login_required
def rpg_gacha(request):
    profile = get_or_create_profile(request.user)
    rolled_item = None
    rolled_rarity = None
    auto_sold = False
    auto_sell_gain = 0

    # Último slot usado en el gacha (para que no se reseteé al refrescar)
    last_slot = request.session.get("rpg_gacha_last_slot", ItemSlot.WEAPON.value)

    # --- Preferencias de auto vender del usuario ---
    auto_sell_set = set()
    if profile.auto_sell_rarities:
        auto_sell_set = set(
            r for r in profile.auto_sell_rarities.split(",") if r.strip()
        )

    # Valores de venta por rareza (mismo sistema que el inventario)
    SELL_VALUES = {
        ItemRarity.BASIC: 2,
        ItemRarity.UNCOMMON: 20,
        ItemRarity.SPECIAL: 50,
        ItemRarity.EPIC: 100,
        ItemRarity.LEGENDARY: 300,
        ItemRarity.MYTHIC: 500,
        ItemRarity.ASCENDED: 1000,
    }

    if request.method == "POST":
        action = request.POST.get("action", "roll")

        # ----------------------------------------
        # 1) Actualizar configuración de AUTO VENDER
        # ----------------------------------------
        if action == "config_autosell":
            selected = request.POST.getlist("auto_sell")
            # Guardamos los códigos de rareza como 'basic,uncommon,...'
            profile.auto_sell_rarities = ",".join(selected)
            profile.save()
            messages.success(request, "Preferencias de auto vender actualizadas.")
            return redirect("rpg_gacha")

        # ----------------------------------------
        # 2) Tirada de GACHA normal
        # ----------------------------------------
        elif action == "roll":
            slot_code = request.POST.get("slot", last_slot)
            try:
                slot = ItemSlot(slot_code)
            except ValueError:
                messages.error(request, "Slot inválido.")
                return redirect("rpg_gacha")

            # Guardar en sesión el último slot seleccionado
            request.session["rpg_gacha_last_slot"] = slot.value
            last_slot = slot.value

            COST = 15
            if profile.coins < COST:
                messages.error(request, "No tienes suficientes monedas.")
                return redirect("rpg_gacha")

            # Determinar rareza según las probabilidades configuradas
            rarity = roll_rarity()
            stats = generate_item_stats(slot, rarity, from_gacha=True)
            name = f"{SLOT_LABELS[slot]} {ItemRarity(rarity).label}"

            # Crear el ítem
            item = CombatItem.objects.create(
                owner=request.user,
                name=name,
                slot=slot,
                rarity=rarity,
                source=ItemSource.GACHA,
                attack=stats["attack"],
                defense=stats["defense"],
                hp=stats["hp"],
                crit_chance=stats["crit_chance"],
                dodge_chance=stats["dodge_chance"],
                speed=stats["speed"],
            )

            # Cobrar coste del gacha
            profile.coins -= COST
            profile.save()

            # ¿Debe auto venderse según preferencias del usuario?
            if rarity in auto_sell_set:
                # Pasamos de código de rareza (string) a enum
                rarity_enum = ItemRarity(rarity)
                sell_price = SELL_VALUES.get(rarity_enum, 0)

                if sell_price > 0:
                    profile.coins += sell_price
                    profile.save()

                auto_sold = True
                auto_sell_gain = sell_price

                # Eliminamos el ítem del inventario
                item.delete()


                # No mostramos detalle del ítem porque ya no existe
                rolled_item = None
                rolled_rarity = rarity
            else:
                # Ítem se conserva normalmente
                rolled_item = item
                rolled_rarity = rarity


    # Tabla de probabilidades para mostrar en la UI
    probs = get_gacha_probs()
    probabilities = [
        {
            "code": rarity,
            "label": ItemRarity(rarity).label,
            "percent": prob * 100.0,
        }
        for (rarity, prob) in probs
    ]

    context = {
        "profile": profile,
        "rolled_item": rolled_item,
        "rolled_rarity": rolled_rarity,
        "probabilities": probabilities,
        "last_slot": last_slot,
        "auto_sold": auto_sold,
        "auto_sell_gain": auto_sell_gain,
        "auto_sell_selected": auto_sell_set,
    }
    return render(request, "notes/rpg_gacha.html", context)



@login_required
def rpg_tower(request):
    profile = get_or_create_profile(request.user)
    stats = get_total_stats(request.user)
    tower, _ = TowerProgress.objects.get_or_create(user=request.user)

    today = date.today()
    if tower.daily_date != today:
        tower.daily_date = today
        tower.daily_coins = 0
        tower.save()

    last_battle = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "fight":
            next_floor = tower.current_floor + 1
            enemy = enemy_stats_for_floor(next_floor)
            victory, log_lines = simulate_battle(stats, enemy)

            log_text = "\n".join(log_lines)
            battle = TowerBattleResult.objects.create(
                user=request.user,
                floor=next_floor,
                victory=victory,
                log_text=log_text,
            )

            last_battle = battle

            if victory:
                tower.current_floor = next_floor
                if next_floor > tower.max_floor_reached:
                    tower.max_floor_reached = next_floor

                reward = next_floor
                potencial = tower.daily_coins + reward
                if potencial > 100:
                    coins_awarded = max(0, 100 - tower.daily_coins)
                else:
                    coins_awarded = reward

                if coins_awarded > 0:
                    profile.coins += coins_awarded
                    tower.daily_coins += coins_awarded
                    profile.save()
                    tower.save()
                    messages.success(
                        request,
                        f"¡Victoria en el piso {next_floor}! Has ganado {coins_awarded} monedas (límite diario 100)."
                    )
                else:
                    tower.save()
                    messages.info(
                        request,
                        f"¡Victoria en el piso {next_floor}! Ya alcanzaste el máximo de 100 monedas diarias en la torre."
                    )
            else:
                tower.save()
                messages.error(
                    request,
                    f"Has sido derrotado en el piso {next_floor}..."
                )

        elif action == "reset":
            tower.current_floor = 0
            tower.save()
            messages.info(request, "Has reiniciado tu progreso actual en la torre.")

    if last_battle is None:
        last_battle = TowerBattleResult.objects.filter(user=request.user).first()

    top_players = (
        TowerProgress.objects
        .select_related("user")
        .order_by("-max_floor_reached", "user__username")[:10]
    )

    context = {
        "profile": profile,
        "stats": stats,
        "tower": tower,
        "last_battle": last_battle,
        "top_players": top_players,
    }
    return render(request, "notes/rpg_tower.html", context)


@login_required
def rpg_inventory(request):
    profile = get_or_create_profile(request.user)
    stats = get_total_stats(request.user)

    # Filtro por tipo de slot
    slot_filter = request.GET.get("slot", "all")
    items_qs = CombatItem.objects.filter(
    owner=request.user,
    market_listing__isnull=True,   # excluye los que están en el mercado
    ).order_by("-created_at")
    valid_slots = {s.value for s in ItemSlot}
    if slot_filter in valid_slots:
        items_qs = items_qs.filter(slot=slot_filter)

    # Ordenar por rareza (más alta primero) y dentro de la misma rareza por fecha
    def rarity_key(it):
        base = RARITY_ORDER.get(it.rarity, 0)
        created = it.created_at or timezone.now()
        return (base, created)

    items = sorted(items_qs, key=rarity_key, reverse=True)

    # IDs de items equipados (para mostrar "Equipado" y evitar venderlos)
    equipped_ids = set()
    for field in [
        "equipped_weapon", "equipped_helmet", "equipped_armor",
        "equipped_pants", "equipped_boots", "equipped_shield",
        "equipped_amulet1", "equipped_amulet2", "equipped_amulet3",
    ]:
        it = getattr(profile, field, None)
        if it:
            equipped_ids.add(it.id)

    if request.method == "POST":
        action = request.POST.get("action")

        # ------------------
        # EQUIPAR ITEM
        # ------------------
        if action == "equip":
            item_id = request.POST.get("item_id")
            item = get_object_or_404(CombatItem, pk=item_id, owner=request.user)

            if item.slot == ItemSlot.WEAPON:
                profile.equipped_weapon = item
                messages.success(request, f"Has equipado {item.name} como arma.")

            elif item.slot == ItemSlot.HELMET:
                profile.equipped_helmet = item
                messages.success(request, f"Has equipado {item.name} como casco.")

            elif item.slot == ItemSlot.ARMOR:
                profile.equipped_armor = item
                messages.success(request, f"Has equipado {item.name} como armadura.")

            elif item.slot == ItemSlot.PANTS:
                profile.equipped_pants = item
                messages.success(request, f"Has equipado {item.name} como pantalones.")

            elif item.slot == ItemSlot.BOOTS:
                profile.equipped_boots = item
                messages.success(request, f"Has equipado {item.name} como botas.")

            elif item.slot == ItemSlot.SHIELD:
                profile.equipped_shield = item
                messages.success(request, f"Has equipado {item.name} como escudo.")

            elif item.slot == ItemSlot.AMULET:
                # Elegir slot de amuleto 1 / 2 / 3
                slot_choice = request.POST.get("amulet_slot", "1")
                if slot_choice == "2":
                    profile.equipped_amulet2 = item
                    messages.success(request, f"Has equipado {item.name} en Amuleto 2.")
                elif slot_choice == "3":
                    profile.equipped_amulet3 = item
                    messages.success(request, f"Has equipado {item.name} en Amuleto 3.")
                else:
                    profile.equipped_amulet1 = item
                    messages.success(request, f"Has equipado {item.name} en Amuleto 1.")

            profile.save()
            return redirect("rpg_inventory")

        # ------------------
        # VENDER UN SOLO ITEM
        # ------------------
        elif action == "sell":
            item_id = request.POST.get("item_id")
            item = get_object_or_404(CombatItem, pk=item_id, owner=request.user)

            if item.id in equipped_ids:
                messages.error(
                    request,
                    "No puedes vender un objeto que tienes equipado. Desequípalo primero."
                )
                return redirect("rpg_inventory")

            value = RARITY_SELL_VALUE.get(item.rarity, 0)
            if value <= 0:
                messages.error(request, "Este objeto no se puede vender.")
                return redirect("rpg_inventory")

            profile.coins += value
            profile.save()
            name = item.name
            item.delete()

            messages.success(
                request,
                f"Has vendido {name} por {value} monedas."
            )
            return redirect("rpg_inventory")

        # ------------------
        # VENTA MÚLTIPLE
        # ------------------
        elif action == "sell_bulk":
            selected_ids = request.POST.getlist("selected_items")
            if not selected_ids:
                messages.info(request, "No seleccionaste ningún objeto para vender.")
                return redirect("rpg_inventory")

            items_to_sell_qs = CombatItem.objects.filter(
                owner=request.user,
                pk__in=selected_ids
            )

            total_value = 0
            sold_count = 0
            blocked_count = 0

            for it in items_to_sell_qs:
                if it.id in equipped_ids:
                    blocked_count += 1
                    continue

                value = RARITY_SELL_VALUE.get(it.rarity, 0)
                if value <= 0:
                    continue

                total_value += value
                sold_count += 1
                it.delete()

            if sold_count > 0:
                profile.coins += total_value
                profile.save()
                msg = f"Has vendido {sold_count} objeto(s) por un total de {total_value} monedas."
                if blocked_count > 0:
                    msg += f" {blocked_count} objeto(s) equipados no se vendieron."
                messages.success(request, msg)
            else:
                if blocked_count > 0:
                    messages.error(
                        request,
                        "Todos los objetos seleccionados estaban equipados y no se pudieron vender."
                    )
                else:
                    messages.info(
                        request,
                        "No se pudo vender ningún objeto con los criterios actuales."
                    )

            return redirect("rpg_inventory")

    # Recalcular stats y equipados tras cambios
    stats = get_total_stats(request.user)
    equipped_ids = set()
    for field in [
        "equipped_weapon", "equipped_helmet", "equipped_armor",
        "equipped_pants", "equipped_boots", "equipped_shield",
        "equipped_amulet1", "equipped_amulet2", "equipped_amulet3",
    ]:
        it = getattr(profile, field, None)
        if it:
            equipped_ids.add(it.id)

    context = {
        "profile": profile,
        "stats": stats,
        "items": items,
        "equipped_ids": equipped_ids,
        "slot_filter": slot_filter,
    }
    return render(request, "notes/rpg_inventory.html", context)





@login_required
def rpg_gacha_config(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Solo el superusuario puede modificar el gacha.")

    qs = GachaProbability.objects.all()
    if not qs.exists():
        for rarity, prob in DEFAULT_GACHA_PROBS:
            GachaProbability.objects.create(rarity=rarity, probability=prob)
        qs = GachaProbability.objects.all()

    if request.method == "POST":
        new_values = {}
        total = 0.0
        for rarity, _prob in DEFAULT_GACHA_PROBS:
            field_name = f"prob_{rarity}"
            val_str = request.POST.get(field_name, "").replace(",", ".")
            try:
                val_percent = float(val_str)
            except ValueError:
                messages.error(request, f"Valor inválido para {ItemRarity(rarity).label}.")
                return redirect("rpg_gacha_config")
            prob = val_percent / 100.0
            if prob < 0:
                messages.error(request, "Las probabilidades no pueden ser negativas.")
                return redirect("rpg_gacha_config")
            new_values[rarity] = prob
            total += prob

        if abs(total - 1.0) > 0.0001:
            messages.error(
                request,
                "La suma de todas las probabilidades debe ser exactamente 100%. "
                f"Actualmente es {total * 100:.4f}%."
            )
        else:
            for rarity, prob in new_values.items():
                obj, _ = GachaProbability.objects.get_or_create(rarity=rarity)
                obj.probability = prob
                obj.save()
            messages.success(request, "Probabilidades actualizadas correctamente.")
            return redirect("rpg_gacha_config")

    probs = get_gacha_probs()
    rows = []
    for rarity, prob in probs:
        rows.append({
            "code": rarity,
            "label": ItemRarity(rarity).label,
            "percent": prob * 100.0,
        })

    context = {
        "rows": rows,
    }
    return render(request, "notes/rpg_gacha_config.html", context)

# ============================================================
#  PVP — helpers
# ============================================================

def ensure_all_pvp_rankings():
    """
    Crea entradas de ranking PVP para todos los usuarios que aún no tienen,
    asignando posición inicial según fecha de registro (date_joined).
    """
    existing_user_ids = set(PvpRanking.objects.values_list("user_id", flat=True))
    missing_users = User.objects.exclude(id__in=existing_user_ids).order_by("date_joined")

    max_pos = PvpRanking.objects.aggregate(Max("position"))["position__max"] or 0
    next_pos = max_pos + 1

    for u in missing_users:
        PvpRanking.objects.create(user=u, position=next_pos)
        next_pos += 1


def get_or_create_pvp_ranking(user: User) -> PvpRanking:
    """
    Devuelve el ranking PvP del usuario, creándolo si no existe.
    Los nuevos usuarios se agregan al final del ranking.
    """
    ensure_all_pvp_rankings()
    ranking, created = PvpRanking.objects.get_or_create(user=user)
    if created:
        max_pos = PvpRanking.objects.aggregate(Max("position"))["position__max"] or 0
        ranking.position = max_pos + 1
        ranking.save()
    return ranking


class BattleStats:
    """
    Helper simple para encapsular stats de combate.
    """
    def __init__(self, hp, attack, defense, crit_chance, dodge_chance, speed):
        self.hp = hp
        self.attack = attack
        self.defense = defense
        self.crit_chance = crit_chance
        self.dodge_chance = dodge_chance
        self.speed = speed


def _stats_from_total(total_stats):
    """
    total_stats: lo que ya te devuelve get_total_stats(user),
    adaptado al pequeño helper BattleStats.
    """
    return BattleStats(
        hp=getattr(total_stats, "hp", 100),
        attack=getattr(total_stats, "attack", 10),
        defense=getattr(total_stats, "defense", 0),
        crit_chance=getattr(total_stats, "crit_chance", 0),
        dodge_chance=getattr(total_stats, "dodge_chance", 0),
        speed=getattr(total_stats, "speed", 0),
    )


def simulate_pvp_battle(attacker_user: User, defender_user: User):
    """
    Simula un combate PvP usando exactamente los stats calculados en get_total_stats,
    que devuelve un diccionario con hp, attack, defense, crit_chance, dodge_chance, speed.
    """
    atk = get_total_stats(attacker_user)
    deff = get_total_stats(defender_user)

    log = []
    log.append(f"Combate PvP entre {attacker_user.username} y {defender_user.username}\n")

    atk_hp = atk["hp"]
    def_hp = deff["hp"]

    atk_atk = atk["attack"]
    atk_def = atk["defense"]
    atk_crit = atk["crit_chance"]
    atk_dodge = atk["dodge_chance"]
    atk_speed = atk["speed"]

    def_atk = deff["attack"]
    def_def = deff["defense"]
    def_crit = deff["crit_chance"]
    def_dodge = deff["dodge_chance"]
    def_speed = deff["speed"]

    # Quién inicia
    if atk_speed > def_speed:
        turn = "A"
    elif def_speed > atk_speed:
        turn = "D"
    else:
        turn = random.choice(["A", "D"])

    turno = 1

    while atk_hp > 0 and def_hp > 0:
        log.append(f"Turno {turno}")

        if turn == "A":
            # Ataca atacante
            base = max(1, atk_atk - def_def)
            crit = random.random() < (atk_crit / 100.0)
            dodge = random.random() < (def_dodge / 100.0)

            if dodge:
                log.append(f" - {defender_user.username} esquiva el ataque.")
                dmg = 0
            else:
                dmg = base * (2 if crit else 1)

            def_hp -= dmg
            log.append(f" - {attacker_user.username} hace {dmg} de daño.")
            log.append(
                f"   Vida: {attacker_user.username}={atk_hp} | {defender_user.username}={max(def_hp, 0)}"
            )

            turn = "D"

        else:
            # Ataca defensor
            base = max(1, def_atk - atk_def)
            crit = random.random() < (def_crit / 100.0)
            dodge = random.random() < (atk_dodge / 100.0)

            if dodge:
                log.append(f" - {attacker_user.username} esquiva el ataque.")
                dmg = 0
            else:
                dmg = base * (2 if crit else 1)

            atk_hp -= dmg
            log.append(f" - {defender_user.username} hace {dmg} de daño.")
            log.append(
                f"   Vida: {attacker_user.username}={max(atk_hp, 0)} | {defender_user.username}={def_hp}"
            )

            turn = "A"

        log.append("")
        turno += 1

    if atk_hp > 0:
        log.append(f"{attacker_user.username} gana el combate.")
        return True, "\n".join(log)
    else:
        log.append(f"{defender_user.username} gana el combate.")
        return False, "\n".join(log)


@login_required
def rpg_pvp_arena(request):
    """
    Pantalla principal de la arena PvP.
    - Muestra tu puesto y recompensa diaria.
    - Muestra hasta 3 rivales por encima de ti para desafiar.
    - Muestra el último combate PvP.
    """
    profile = get_or_create_profile(request.user)
    my_rank = get_or_create_pvp_ranking(request.user)
    stats = get_total_stats(request.user)

    # Aseguramos que existan rankings para todos
    ensure_all_pvp_rankings()

    # Rivales crudos: hasta 3 puestos por encima
    raw_challengers = (
        PvpRanking.objects
        .select_related("user")
        .filter(position__lt=my_rank.position)
        .order_by("-position")[:3]
    )

    challengers = []
    for rank in raw_challengers:
        u = rank.user
        p = get_or_create_profile(u)
        s = get_total_stats(u)

        # ¿Tiene algo equipado?
        has_equipped = any([
            p.equipped_weapon,
            p.equipped_helmet,
            p.equipped_armor,
            p.equipped_pants,
            p.equipped_boots,
            p.equipped_shield,
            p.equipped_amulet1,
            p.equipped_amulet2,
            p.equipped_amulet3,
        ])

        # ¿O stats distintos a los básicos?
        has_stats = any([
            s["hp"] != 100,
            s["attack"] != 10,
            s["defense"] != 0,
            s["crit_chance"] != 0,
            s["dodge_chance"] != 0,
            s["speed"] != 0,
        ])

        challengers.append({
            "rank": rank,
            "user": u,
            "profile": p,
            "stats": s,
            "has_equipment": has_equipped or has_stats,
        })

    # Último combate donde participe el usuario
    last_battle = (
        PvpBattleLog.objects
        .filter(Q(attacker=request.user) | Q(defender=request.user))
        .select_related("attacker", "defender")
        .first()
    )

    # Recompensa diaria
    today = date.today()
    todays_reward = my_rank.daily_reward()
    can_claim = todays_reward > 0 and my_rank.last_reward_date != today

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "claim_reward":
            if not can_claim:
                messages.info(
                    request,
                    "Ya has cobrado tu recompensa diaria o tu puesto no otorga monedas."
                )
            else:
                profile.coins += todays_reward
                profile.save()
                my_rank.last_reward_date = today
                my_rank.save()
                messages.success(
                    request,
                    f"Has cobrado {todays_reward} monedas por tu puesto PvP #{my_rank.position}.",
                )
            return redirect("rpg_pvp_arena")

    context = {
        "profile": profile,
        "my_rank": my_rank,
        "challengers": challengers,
        "last_battle": last_battle,
        "todays_reward": todays_reward,
        "can_claim": can_claim,
        "stats": stats,
    }
    return render(request, "notes/rpg_pvp_arena.html", context)


@require_POST
@login_required
def rpg_pvp_challenge(request, target_id):
    """
    El jugador desafía a un rival con mejor puesto (posición menor).
    Solo se permite desafiar hasta 3 puestos por encima.
    Si gana, intercambian posiciones de forma segura (sin romper el UNIQUE).
    """
    attacker = request.user
    attacker_rank = get_or_create_pvp_ranking(attacker)

    # Rival a desafiar (entrada de PvpRanking)
    try:
        target_rank = PvpRanking.objects.select_related("user").get(id=target_id)
    except PvpRanking.DoesNotExist:
        messages.error(request, "El rival no existe.")
        return redirect("rpg_pvp_arena")

    # No puedes desafiar a alguien por debajo o igual
    if target_rank.position >= attacker_rank.position:
        messages.error(request, "Solo puedes desafiar a jugadores con mejor clasificación que tú.")
        return redirect("rpg_pvp_arena")

    # Máximo 3 puestos por encima
    if attacker_rank.position - target_rank.position > 3:
        messages.error(request, "Solo puedes desafiar hasta 3 puestos por encima.")
        return redirect("rpg_pvp_arena")

    defender = target_rank.user

    # Simulación de combate (usa el sistema de stats del RPG)
    attacker_won, log_text = simulate_pvp_battle(attacker, defender)

    # Guardar log
    PvpBattleLog.objects.create(
        attacker=attacker,
        defender=defender,
        attacker_won=attacker_won,
        log_text=log_text,
    )

    if attacker_won:
        old_attacker_pos = attacker_rank.position
        old_target_pos = target_rank.position

        try:
            # Swap SEGURO usando una posición temporal que no esté en uso
            with transaction.atomic():
                max_pos = PvpRanking.objects.aggregate(Max("position"))["position__max"] or 0
                temp_pos = max_pos + 1  # posición libre

                # 1) Mover al atacante a una posición temporal
                attacker_rank.position = temp_pos
                attacker_rank.save(update_fields=["position"])

                # 2) Mover al defensor al puesto original del atacante
                target_rank.position = old_attacker_pos
                target_rank.save(update_fields=["position"])

                # 3) Mover al atacante al antiguo puesto del defensor
                attacker_rank.position = old_target_pos
                attacker_rank.save(update_fields=["position"])

        except IntegrityError:
            messages.error(
                request,
                "Ocurrió un problema al actualizar el ranking. Inténtalo de nuevo."
            )
            return redirect("rpg_pvp_arena")

        messages.success(
            request,
            f"¡Has vencido a {defender.username} y ahora ocupas el puesto #{old_target_pos}!"
        )
    else:
        messages.info(
            request,
            f"Has perdido contra {defender.username}. Tu clasificación permanece en #{attacker_rank.position}."
        )

    return redirect("rpg_pvp_arena")


@login_required
def rpg_pvp_leaderboard(request):
    """
    Muestra el top 10 del ranking PvP.
    """
    ensure_all_pvp_rankings()
    top_ranks = (
        PvpRanking.objects
        .select_related("user")
        .order_by("position")[:10]
    )

    context = {
        "top_ranks": top_ranks,
    }
    return render(request, "notes/rpg_pvp_leaderboard.html", context)

@login_required
def rpg_trades(request):
    """
    Bandeja de intercambios:
    - Intercambios recibidos.
    - Intercambios enviados.
    """
    profile = get_or_create_profile(request.user)

    incoming = (
        Trade.objects
        .filter(to_user=request.user)
        .select_related("from_user", "to_user")
        .order_by("-created_at")
    )
    outgoing = (
        Trade.objects
        .filter(from_user=request.user)
        .select_related("from_user", "to_user")
        .order_by("-created_at")
    )

    context = {
        "profile": profile,
        "incoming": incoming,
        "outgoing": outgoing,
    }
    return render(request, "notes/rpg_trades.html", context)

@login_required
def rpg_trade_create(request):
    """
    Crear un nuevo trade:
    - Seleccionas al otro jugador.
    - Qué monedas tú pones (from_coins).
    - Qué monedas quieres que ponga el otro (to_coins).
    - Qué objetos tuyos ofreces (máx 10 objetos en total, pero aquí solo cuenta tu lado).
    El detalle se podrá ajustar luego (contra-oferta) por ambos.
    """
    profile = get_or_create_profile(request.user)

    users = User.objects.exclude(id=request.user.id).order_by("username")
    my_items = CombatItem.objects.filter(owner=request.user).order_by("-created_at")

    if request.method == "POST":
        to_user_id = request.POST.get("to_user")
        try:
            to_user = User.objects.get(pk=to_user_id)
        except (User.DoesNotExist, TypeError, ValueError):
            messages.error(request, "Debes seleccionar un jugador válido.")
            return redirect("rpg_trade_create")

        # Monedas
        def parse_int(value, default=0):
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return default

        from_coins = parse_int(request.POST.get("from_coins"), 0)
        to_coins = parse_int(request.POST.get("to_coins"), 0)

        # Objetos que tú ofreces
        offered_ids = request.POST.getlist("offered_items")
        offered_qs = CombatItem.objects.filter(
            owner=request.user,
            pk__in=offered_ids,
        )

        if offered_qs.count() > 10:
            messages.error(
                request,
                "No puedes ofrecer más de 10 objetos en un mismo intercambio."
            )
            return redirect("rpg_trade_create")

        # Crear trade
        trade = Trade.objects.create(
            from_user=request.user,
            to_user=to_user,
            from_coins=from_coins,
            to_coins=to_coins,
            last_actor=request.user,
        )
        trade.offered_from.set(offered_qs)

        # Notificación al otro jugador
        Notification.objects.create(
            user=to_user,
            message=f"{request.user.username} te ha enviado una oferta de intercambio.",
            url=reverse("rpg_trade_detail", args=[trade.id]),
        )

        messages.success(request, "Intercambio creado y enviado.")
        return redirect("rpg_trades")

    context = {
        "profile": profile,
        "users": users,
        "my_items": my_items,
    }
    return render(request, "notes/rpg_trade_create.html", context)

@login_required
def rpg_trade_detail(request, trade_id):
    """
    Detalle de un intercambio:
    - Ambos jugadores pueden hacer contra-oferta (editar monedas/objetos) mientras esté pendiente.
    - Cualquiera de los dos puede ACEPTAR (se ejecuta el intercambio).
    - El receptor puede RECHAZAR; el emisor puede CANCELAR.
    """
    trade = get_object_or_404(
        Trade.objects.select_related("from_user", "to_user"),
        pk=trade_id,
    )

    if request.user not in (trade.from_user, trade.to_user):
        return HttpResponseForbidden("No puedes ver este intercambio.")

    me = request.user
    other = trade.other_user(me)

    my_profile = get_or_create_profile(me)
    other_profile = get_or_create_profile(other)

    my_items = CombatItem.objects.filter(owner=me).order_by("-created_at")
    other_items = CombatItem.objects.filter(owner=other).order_by("-created_at")

    is_from_side = (me == trade.from_user)

    if request.method == "POST" and trade.is_pending():
        action = request.POST.get("action")

        # Helper para parsear ints >= 0
        def parse_int(value, default=0):
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return default

        # --------------------------
        # ACEPTAR INTERCAMBIO
        # --------------------------
        if action == "accept":
            try:
                with transaction.atomic():
                    # Refrescar perfiles
                    my_profile = get_or_create_profile(me)
                    other_profile = get_or_create_profile(other)

                    # Comprobar que ambos tienen las monedas suficientes
                    if my_profile.coins < (trade.from_coins if is_from_side else trade.to_coins):
                        messages.error(
                            request,
                            "No tienes suficientes monedas para completar el intercambio."
                        )
                        return redirect("rpg_trade_detail", trade_id=trade.id)

                    if other_profile.coins < (trade.to_coins if is_from_side else trade.from_coins):
                        messages.error(
                            request,
                            f"{other.username} no tiene suficientes monedas para completar el intercambio."
                        )
                        return redirect("rpg_trade_detail", trade_id=trade.id)

                    # Comprobar propiedad de los ítems
                    for item in trade.offered_from.all():
                        if item.owner != trade.from_user:
                            messages.error(
                                request,
                                f"El objeto {item.name} ya no pertenece a {trade.from_user.username}."
                            )
                            return redirect("rpg_trade_detail", trade_id=trade.id)

                    for item in trade.offered_to.all():
                        if item.owner != trade.to_user:
                            messages.error(
                                request,
                                f"El objeto {item.name} ya no pertenece a {trade.to_user.username}."
                            )
                            return redirect("rpg_trade_detail", trade_id=trade.id)

                    # Límite de 10 objetos total
                    if trade.total_items() > 10:
                        messages.error(
                            request,
                            "Este intercambio supera el máximo de 10 objetos en total."
                        )
                        return redirect("rpg_trade_detail", trade_id=trade.id)

                    # Transferir monedas
                    # from_user da from_coins a to_user
                    if trade.from_coins > 0:
                        from_profile = get_or_create_profile(trade.from_user)
                        to_profile = get_or_create_profile(trade.to_user)

                        if from_profile.coins < trade.from_coins:
                            messages.error(
                                request,
                                f"{trade.from_user.username} no tiene suficientes monedas."
                            )
                            return redirect("rpg_trade_detail", trade_id=trade.id)

                        from_profile.coins -= trade.from_coins
                        to_profile.coins += trade.from_coins
                        from_profile.save()
                        to_profile.save()

                    # to_user da to_coins a from_user
                    if trade.to_coins > 0:
                        from_profile = get_or_create_profile(trade.from_user)
                        to_profile = get_or_create_profile(trade.to_user)

                        if to_profile.coins < trade.to_coins:
                            messages.error(
                                request,
                                f"{trade.to_user.username} no tiene suficientes monedas."
                            )
                            return redirect("rpg_trade_detail", trade_id=trade.id)

                        to_profile.coins -= trade.to_coins
                        from_profile.coins += trade.to_coins
                        from_profile.save()
                        to_profile.save()

                    # Transferir objetos
                    for item in trade.offered_from.all():
                        item.owner = trade.to_user
                        item.save()

                    for item in trade.offered_to.all():
                        item.owner = trade.from_user
                        item.save()

                    trade.status = Trade.STATUS_ACCEPTED
                    trade.last_actor = me
                    trade.save()

                    # Notificaciones
                    Notification.objects.create(
                        user=other,
                        message=f"{me.username} ha aceptado el intercambio #{trade.id}.",
                        url=reverse("rpg_trade_detail", args=[trade.id]),
                    )

                    messages.success(request, "Intercambio completado correctamente.")
                    return redirect("rpg_trades")

            except IntegrityError:
                messages.error(
                    request,
                    "Ocurrió un problema al completar el intercambio. Inténtalo nuevamente."
                )
                return redirect("rpg_trade_detail", trade_id=trade.id)

        # --------------------------
        # RECHAZAR / CANCELAR
        # --------------------------
        elif action == "reject":
            if me == trade.to_user:
                trade.status = Trade.STATUS_REJECTED
                trade.last_actor = me
                trade.save()

                Notification.objects.create(
                    user=other,
                    message=f"{me.username} ha rechazado tu intercambio #{trade.id}.",
                    url=reverse("rpg_trade_detail", args=[trade.id]),
                )

                messages.info(request, "Has rechazado el intercambio.")
            else:
                messages.error(request, "Solo el receptor puede rechazar el intercambio.")
            return redirect("rpg_trades")

        elif action == "cancel":
            if me == trade.from_user:
                trade.status = Trade.STATUS_CANCELLED
                trade.last_actor = me
                trade.save()

                Notification.objects.create(
                    user=other,
                    message=f"{me.username} ha cancelado el intercambio #{trade.id}.",
                    url=reverse("rpg_trade_detail", args=[trade.id]),
                )

                messages.info(request, "Has cancelado el intercambio.")
            else:
                messages.error(request, "Solo el emisor puede cancelar el intercambio.")
            return redirect("rpg_trades")

        # --------------------------
        # CONTRA-OFERTA (editar trade)
        # --------------------------
        elif action == "counter":
            # Estos campos SIEMPRE representan lo que da cada lado
            new_from_coins = parse_int(request.POST.get("from_coins"), 0)
            new_to_coins = parse_int(request.POST.get("to_coins"), 0)

            from_items_ids = request.POST.getlist("from_items")
            to_items_ids = request.POST.getlist("to_items")

            from_items_qs = CombatItem.objects.filter(
                owner=trade.from_user,
                pk__in=from_items_ids,
            )
            to_items_qs = CombatItem.objects.filter(
                owner=trade.to_user,
                pk__in=to_items_ids,
            )

            if from_items_qs.count() + to_items_qs.count() > 10:
                messages.error(
                    request,
                    "No puedes tener más de 10 objetos en total en un intercambio."
                )
                return redirect("rpg_trade_detail", trade_id=trade.id)

            trade.from_coins = new_from_coins
            trade.to_coins = new_to_coins
            trade.offered_from.set(from_items_qs)
            trade.offered_to.set(to_items_qs)
            trade.status = Trade.STATUS_PENDING
            trade.last_actor = me
            trade.save()

            Notification.objects.create(
                user=other,
                message=f"{me.username} ha enviado una contra-oferta en el intercambio #{trade.id}.",
                url=reverse("rpg_trade_detail", args=[trade.id]),
            )

            messages.success(request, "Contra-oferta enviada.")
            return redirect("rpg_trade_detail", trade_id=trade.id)

    # Contexto para template
    context = {
        "trade": trade,
        "me": me,
        "other": other,
        "my_profile": my_profile,
        "other_profile": other_profile,
        "my_items": my_items,
        "other_items": other_items,
        "is_from_side": is_from_side,
    }
    return render(request, "notes/rpg_trade_detail.html", context)

# ============================================================
#  WORLD BOSS
# ============================================================

def _get_current_world_boss_cycle():
    """
    Cada día se divide en bloques de 3 horas empezando a las 00:00 (hora local).
    Este helper devuelve el ciclo actual de World Boss (prep/batalla/reposo).
    """
    now = timezone.localtime(timezone.now())
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    minutes_since_midnight = now.hour * 60 + now.minute
    block_minutes = 3 * 60  # 3 horas
    cycle_index = minutes_since_midnight // block_minutes

    cycle_start = start_of_day + timedelta(hours=3 * cycle_index)

    cycle, _ = WorldBossCycle.objects.get_or_create(start_time=cycle_start)
    return cycle, now, cycle_start


def _advance_world_boss_battle(cycle: WorldBossCycle, now_local, cycle_start):
    """
    Avanza los turnos de la batalla en base al tiempo real transcurrido desde
    el inicio de la fase de batalla. 1 turno = 1 minuto.
    El jefe:
      - recibe daño: sumamos el ataque de cada jugador vivo (sin defensa)
      - golpea a todos los jugadores vivos con 50 de daño fijo.
    La batalla termina cuando todos los participantes tienen 0 o menos de HP.
    Al terminar:
      - Se reparten 5 monedas por cada 100 puntos de daño TOTAL recibido
        a TODOS los participantes de este ciclo.
    """
    if cycle.finished:
        return

    battle_start = cycle_start + timedelta(hours=1)  # prep = 1h, luego batalla

    # Si aún no empieza la fase de batalla, no hacemos nada
    if now_local <= battle_start:
        return

    # ¿Cuántos turnos deberían haberse ejecutado hasta ahora?
    total_minutes = int((now_local - battle_start).total_seconds() // 60)
    pending_turns = total_minutes - cycle.turns_processed
    if pending_turns <= 0:
        return

    participants = list(
        cycle.participants.select_related("user")
    )
    if not participants:
        # Nadie participó: marcamos como terminada.
        cycle.finished = True
        cycle.save()
        return

    log_lines = []
    turn_number = cycle.turns_processed + 1

    for _ in range(pending_turns):
        # Jugadores vivos al inicio de este turno
        alive = [p for p in participants if p.current_hp > 0]
        if not alive:
            cycle.finished = True
            break

        log_lines.append(f"Turno {turn_number}")

        # 1) Todos los jugadores golpean al jefe
        for p in alive:
            stats = get_total_stats(p.user)
            dmg = max(1, stats["attack"])  # sin defensa del jefe
            p.total_damage_done += dmg
            cycle.total_damage += dmg
            log_lines.append(f"- {p.user.username} inflige {dmg} de daño al jefe.")

        # 2) El jefe golpea a todos con 50 de daño fijo
        log_lines.append(f"- El jefe golpea a todos y hace 50 de daño.")
        for p in alive:
            p.current_hp -= 50
            if p.current_hp <= 0:
                p.current_hp = 0
                log_lines.append(f"  · {p.user.username} ha sido derrotado.")

        log_lines.append("")
        turn_number += 1
        cycle.turns_processed += 1

    # Guardamos cambios en los participantes
    WorldBossParticipant.objects.bulk_update(
        participants,
        ["current_hp", "total_damage_done"],
    )

    # Append del log
    if log_lines:
        new_block = "\n".join(log_lines)
        if cycle.battle_log:
            cycle.battle_log += "\n" + new_block
        else:
            cycle.battle_log = new_block

    # ¿Queda alguien vivo?
    if not any(p.current_hp > 0 for p in participants):
        cycle.finished = True

    # Si la batalla acaba y aún no se han repartido las recompensas, las damos
    if cycle.finished and not cycle.rewards_given and cycle.total_damage > 0:
        reward_per_player = (cycle.total_damage // 100) * 5
        if reward_per_player > 0:
            for p in participants:
                prof = get_or_create_profile(p.user)
                prof.coins += reward_per_player
                prof.save()
        cycle.rewards_given = True

    cycle.save()


@login_required
def rpg_world_boss(request):
    """
    Vista principal de la World Boss Battle.
    Estados:
      - preparación (1h): los jugadores se pueden unir.
      - batalla (hasta 2h dentro del bloque): se simula 1 turno por minuto.
      - reposo (hasta el final del bloque de 3h): se ve log y daño total.
    """
    cycle, now_local, cycle_start = _get_current_world_boss_cycle()

    elapsed = now_local - cycle_start
    hours = elapsed.total_seconds() / 3600.0

    if cycle.finished:
        phase = "rest"
    else:
        if hours < 1:
            phase = "prep"
        elif hours < 2:
            phase = "battle"
        else:
            phase = "rest"

    prep_end = cycle_start + timedelta(hours=1)
    battle_start = cycle_start + timedelta(hours=1)
    battle_end = cycle_start + timedelta(hours=2)
    cycle_end = cycle_start + timedelta(hours=3)

    profile = get_or_create_profile(request.user)
    stats = get_total_stats(request.user)

    participation = WorldBossParticipant.objects.filter(
        cycle=cycle,
        user=request.user,
    ).first()

    # Unirse durante fase de preparación
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "join" and phase == "prep":
            if participation is None:
                participation = WorldBossParticipant.objects.create(
                    cycle=cycle,
                    user=request.user,
                    current_hp=stats["hp"],
                    total_damage_done=0,
                )
                messages.success(
                    request,
                    "Te has unido a la próxima batalla contra el World Boss."
                )
            else:
                messages.info(request, "Ya estás inscrito en esta batalla.")
            return redirect("rpg_world_boss")

    # Si estamos en batalla, avanzamos los turnos según el tiempo real
    if phase == "battle":
        _advance_world_boss_battle(cycle, now_local, cycle_start)

    # Refrescamos datos después de posible simulación
    participants_qs = cycle.participants.select_related("user").order_by(
        "-total_damage_done",
        "user__username",
    )
    participation = participants_qs.filter(user=request.user).first()
    total_damage = cycle.total_damage
    hero = participants_qs.first() if total_damage > 0 else None
    reward_preview = (total_damage // 100) * 5

    context = {
        "profile": profile,
        "stats": stats,
        "cycle": cycle,
        "phase": phase,
        "participants": participants_qs,
        "participation": participation,
        "hero": hero,
        "total_damage": total_damage,
        "reward_preview": reward_preview,
        "prep_end": prep_end,
        "battle_start": battle_start,
        "battle_end": battle_end,
        "cycle_end": cycle_end,
        "now": now_local,
    }
    return render(request, "notes/rpg_world_boss.html", context)


# ============================================================
#  MINI BOSS — Definiciones
# ============================================================

MINI_BOSS_DEFINITIONS = {
    "moth_baron": {
        "code": "moth_baron",
        "name": "Varón Polilla",
        "damage_per_turn": 30,
        "reward_per_100": 5,   # 1 moneda por cada 100 de daño
        "max_reward": 40,      # máximo 40 monedas
    },
    "cat_commander": {
        "code": "cat_commander",
        "name": "Comandante Gato",
        "damage_per_turn": 50,
        "reward_per_100": 5,
        "max_reward": 60,
    },
    "nightmare_freddy": {
        "code": "nightmare_freddy",
        "name": "Pesadilla Freddy",
        "damage_per_turn": 100,
        "reward_per_100": 5,
        "max_reward": 100,
    },
}


def get_miniboss_def(boss_code):
    return MINI_BOSS_DEFINITIONS.get(boss_code)


def get_user_miniboss_daily_count(user):
    """
    Cuenta cuántas veces ha participado un usuario hoy
    (en cualquier minijefe).
    """
    today = date.today()
    return MiniBossParticipant.objects.filter(
        user=user,
        lobby__created_at__date=today,
    ).values("lobby").distinct().count()


def _apply_miniboss_rewards(lobby, participants_qs):
    """
    Calcula y entrega recompensas SEGÚN EL DAÑO TOTAL GLOBAL
    que llevaba el jefe en el momento en que murió el jugador.

    Ejemplo: si el jugador muere cuando lobby.total_damage era 1100,
    se usan esos 1100 para el cálculo de monedas.
    """
    boss_def = get_miniboss_def(lobby.boss_code)
    if not boss_def:
        return

    reward_per_100 = boss_def["reward_per_100"]
    max_reward = boss_def["max_reward"]

    for p in participants_qs:
        if p.reward_given:
            continue

        # Si nunca se seteó durante la batalla (por seguridad),
        # usamos el total de daño final del lobby
        effective_damage = p.boss_damage_at_death or lobby.total_damage

        # monedas = floor(effective_damage / 100) * reward_per_100, cap max_reward
        coins = (effective_damage // 100) * reward_per_100
        if coins > max_reward:
            coins = max_reward

        if coins > 0:
            profile = get_or_create_profile(p.user)
            profile.coins += coins
            profile.save()

        p.reward_coins = coins
        p.reward_given = True
        p.save()


def _advance_miniboss_battle(lobby: MiniBossLobby):
    """
    Avanza la batalla del minijefe según el tiempo transcurrido.
    - 1 turno cada 30 segundos desde started_at.
    - El jefe hace daño fijo a todos los jugadores vivos.
    - Los jugadores hacen daño basado en su ataque total.
    - La batalla termina cuando todos los jugadores están derrotados.

    AHORA: cada participante guarda lobby.total_damage en boss_damage_at_death
    en el turno en que muere, para usarlo como base de recompensa.
    """
    if lobby.status != MiniBossLobby.STATUS_RUNNING or not lobby.started_at:
        return

    boss_def = get_miniboss_def(lobby.boss_code)
    if not boss_def:
        return

    now = timezone.now()
    elapsed = (now - lobby.started_at).total_seconds()

    # Si quieres 30 segundos por turno cambia 10 -> 30
    turns_should_have = int(elapsed // 10)
    if turns_should_have <= lobby.current_turn:
        # Ya estamos al día
        return

    participants = list(
        MiniBossParticipant.objects
        .filter(lobby=lobby)
        .select_related("user")
    )

    # Filtrar vivos
    alive = [p for p in participants if p.is_alive and p.hp_remaining > 0]

    log_lines = []
    if lobby.log_text:
        log_lines = lobby.log_text.splitlines()

    damage_per_turn = boss_def["damage_per_turn"]

    # Avanzamos turno a turno hasta alcanzar turns_should_have o que no queden vivos
    while lobby.current_turn < turns_should_have and alive:
        lobby.current_turn += 1
        turn_num = lobby.current_turn
        log_lines.append(f"Turno {turn_num}")

        # 1) Jugadores atacan
        turn_total_damage = 0
        for p in alive:
            stats = get_total_stats(p.user)
            dmg = max(1, stats["attack"])
            p.total_damage_done += dmg
            turn_total_damage += dmg

        lobby.total_damage += turn_total_damage
        log_lines.append(f"- Los jugadores infligen {turn_total_damage} de daño al jefe.")

        # 2) Jefe contraataca
        if alive:
            log_lines.append(f"- El jefe contraataca con {damage_per_turn} de daño a cada jugador.")
            for p in alive:
                if not p.is_alive or p.hp_remaining <= 0:
                    continue
                p.hp_remaining -= damage_per_turn
                if p.hp_remaining <= 0:
                    p.hp_remaining = 0
                    p.is_alive = False
                    # 🔥 Guardamos el daño global del jefe en el momento de la muerte
                    if p.boss_damage_at_death == 0:
                        p.boss_damage_at_death = lobby.total_damage

        # Actualizar lista de vivos
        alive = [p for p in alive if p.is_alive and p.hp_remaining > 0]

        if not alive:
            log_lines.append("- Todos los jugadores han sido derrotados.")
        log_lines.append("")

    # Guardar participantes
    for p in participants:
        # Por seguridad: si alguien nunca quedó con boss_damage_at_death,
        # le dejamos el total final
        if p.boss_damage_at_death == 0 and (not p.is_alive or p.hp_remaining <= 0):
            p.boss_damage_at_death = lobby.total_damage
        p.save()

    # Si ya no quedan vivos, terminamos la batalla
    if not any(p.is_alive and p.hp_remaining > 0 for p in participants):
        lobby.status = MiniBossLobby.STATUS_FINISHED
        lobby.ended_at = timezone.now()
        _apply_miniboss_rewards(lobby, participants)

    lobby.log_text = "\n".join(log_lines)
    lobby.save()


@login_required
def rpg_miniboss_hub(request):
    """
    Pantalla principal para minijefes:
    - Muestra los 3 jefes disponibles.
    - Muestra lobbies en espera.
    - Permite crear un lobby nuevo (respetando máximo 3 participaciones diarias).
    """
    profile = get_or_create_profile(request.user)

    today_count = get_user_miniboss_daily_count(request.user)
    remaining = max(0, 3 - today_count)

    # Crear lobby
    if request.method == "POST":
        boss_code = request.POST.get("boss_code")
        boss_def = get_miniboss_def(boss_code)

        if not boss_def:
            messages.error(request, "Jefe inválido.")
            return redirect("rpg_miniboss_hub")

        if remaining <= 0:
            messages.error(request, "Ya has participado en el máximo de 3 minijefes hoy.")
            return redirect("rpg_miniboss_hub")

        # Crear lobby
        lobby = MiniBossLobby.objects.create(
            creator=request.user,
            boss_code=boss_code,
        )

        # Crear participante para el creador
        stats = get_total_stats(request.user)
        MiniBossParticipant.objects.create(
            lobby=lobby,
            user=request.user,
            hp_remaining=stats["hp"],
        )

        messages.success(
            request,
            f"Has creado un lobby contra {boss_def['name']}."
        )
        return redirect("rpg_miniboss_lobby", lobby_id=lobby.id)

    # Listar lobbies en espera
    waiting_lobbies = (
        MiniBossLobby.objects
        .filter(status=MiniBossLobby.STATUS_WAITING)
        .select_related("creator")
        .order_by("-created_at")[:20]
    )

    lobby_rows = []
    for lb in waiting_lobbies:
        boss_def = get_miniboss_def(lb.boss_code)
        lobby_rows.append({
            "lobby": lb,
            "boss_name": boss_def["name"] if boss_def else lb.get_boss_code_display(),
        })

    bosses_list = []
    for code, cfg in MINI_BOSS_DEFINITIONS.items():
        bosses_list.append(cfg)

    context = {
        "profile": profile,
        "remaining": remaining,
        "today_count": today_count,
        "bosses": bosses_list,
        "waiting_lobbies": lobby_rows,
    }
    return render(request, "notes/rpg_miniboss_hub.html", context)

@login_required
def rpg_miniboss_lobby(request, lobby_id):
    """
    Vista del lobby de un minijefe:
    - Muestra participantes, jefe, estado y log.
    - Permite unirse (si hay cupo diario).
    - Solo el creador puede iniciar la batalla.
    - Hay un botón de "Actualizar" que recarga la vista.
    """
    lobby = get_object_or_404(MiniBossLobby, pk=lobby_id)
    boss_def = get_miniboss_def(lobby.boss_code)
    profile = get_or_create_profile(request.user)

    # Avanzar la batalla si está en curso
    if lobby.status == MiniBossLobby.STATUS_RUNNING:
        _advance_miniboss_battle(lobby)
        lobby.refresh_from_db()

    participants = list(
        MiniBossParticipant.objects
        .filter(lobby=lobby)
        .select_related("user")
    )

    is_participant = any(p.user_id == request.user.id for p in participants)
    is_creator = (lobby.creator_id == request.user.id)

    today_count = get_user_miniboss_daily_count(request.user)
    remaining = max(0, 3 - today_count)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "join":
            if is_participant:
                messages.info(request, "Ya estás en este lobby.")
            elif lobby.status != MiniBossLobby.STATUS_WAITING:
                messages.error(request, "Solo se puede entrar a lobbies en espera.")
            elif remaining <= 0:
                messages.error(request, "Ya has participado en el máximo de 3 minijefes hoy.")
            else:
                stats = get_total_stats(request.user)
                MiniBossParticipant.objects.create(
                    lobby=lobby,
                    user=request.user,
                    hp_remaining=stats["hp"],
                )
                messages.success(request, "Te has unido al lobby.")
            return redirect("rpg_miniboss_lobby", lobby_id=lobby.id)

        elif action == "start":
            if not is_creator:
                messages.error(request, "Solo el creador puede iniciar la batalla.")
            elif lobby.status != MiniBossLobby.STATUS_WAITING:
                messages.error(request, "La batalla ya ha comenzado o ha terminado.")
            else:
                if not participants:
                    messages.error(request, "No hay participantes en el lobby.")
                else:
                    lobby.status = MiniBossLobby.STATUS_RUNNING
                    lobby.started_at = timezone.now()
                    lobby.current_turn = 0
                    text = lobby.log_text or ""
                    if boss_def:
                        text += f"Comienza la batalla contra {boss_def['name']}.\n\n"
                    lobby.log_text = text
                    lobby.save()
                    messages.success(request, "¡La batalla ha comenzado!")
            return redirect("rpg_miniboss_lobby", lobby_id=lobby.id)

        elif action == "refresh":
            # Solo recarga
            return redirect("rpg_miniboss_lobby", lobby_id=lobby.id)

    # Recargar participantes por si algo cambió
    participants = list(
        MiniBossParticipant.objects
        .filter(lobby=lobby)
        .select_related("user")
    )

    hero = None
    if lobby.status == MiniBossLobby.STATUS_FINISHED and participants:
        hero = sorted(
            participants,
            key=lambda p: p.total_damage_done,
            reverse=True,
        )[0]

    context = {
        "lobby": lobby,
        "boss": boss_def,
        "participants": participants,
        "is_participant": is_participant,
        "is_creator": is_creator,
        "remaining": remaining,
        "hero": hero,
    }
    return render(request, "notes/rpg_miniboss_lobby.html", context)

# ============================================================
#  MERCADO
# ============================================================

RARITY_CHOICES_VALUES = [choice[0] for choice in ItemRarity.choices]


# ============================================================
#  MERCADO
# ============================================================

# valores de rareza (basic, uncommon, …) para validar el filtro
RARITY_CHOICES_VALUES = [choice[0] for choice in ItemRarity.choices]


@login_required
def rpg_market(request):
    """
    Mercado global:
    - Lista todas las ofertas activas.
    - Permite filtrar por rareza.
    - Muestra las publicaciones propias y los objetos disponibles para listar.
    """
    profile = get_or_create_profile(request.user)

    rarity_filter = request.GET.get("rarity", "all")

    listings_qs = (
        MarketListing.objects
        .filter(is_active=True)
        .select_related("item", "seller")
    )
    if rarity_filter in RARITY_CHOICES_VALUES:
        listings_qs = listings_qs.filter(item__rarity=rarity_filter)

    listings = list(listings_qs)

    # Publicaciones del usuario
    my_listings = list(
        MarketListing.objects
        .filter(is_active=True, seller=request.user)
        .select_related("item")
    )

    # Objetos disponibles para poner en venta (no listados ya)
    available_items = CombatItem.objects.filter(
        owner=request.user,
        market_listing__isnull=True,   # <-- importante para que no aparezcan los listados
    ).order_by("-created_at")

    # choices (value, label) para el combo de rareza en el template
    item_rarity_choices = ItemRarity.choices

    context = {
        "profile": profile,
        "listings": listings,
        "my_listings": my_listings,
        "available_items": available_items,
        "rarity_filter": rarity_filter,
        "item_rarity_choices": item_rarity_choices,
    }
    return render(request, "notes/rpg_market.html", context)


@login_required
@require_POST
def rpg_market_list_item(request, item_id):
    """
    Poner un objeto en el mercado con un precio en monedas.
    El objeto deja de aparecer en el inventario (porque lo filtramos por market_listing__isnull=True).
    """
    item = get_object_or_404(CombatItem, pk=item_id, owner=request.user)

    # Ya está listado
    if hasattr(item, "market_listing") and item.market_listing.is_active:
        messages.error(request, "Ese objeto ya está en el mercado.")
        return redirect("rpg_market")

    price_str = request.POST.get("price", "").strip()
    try:
        price = int(price_str)
    except ValueError:
        messages.error(request, "El precio debe ser un número entero.")
        return redirect("rpg_market")

    if price <= 0:
        messages.error(request, "El precio debe ser mayor que 0.")
        return redirect("rpg_market")

    # Si estaba equipado, lo desequipamos
    profile = get_or_create_profile(request.user)
    changed = False
    for field in [
        "equipped_weapon", "equipped_helmet", "equipped_armor",
        "equipped_pants", "equipped_boots", "equipped_shield",
        "equipped_amulet1", "equipped_amulet2", "equipped_amulet3",
    ]:
        if getattr(profile, field, None) == item:
            setattr(profile, field, None)
            changed = True
    if changed:
        profile.save()

    MarketListing.objects.create(
        item=item,
        seller=request.user,
        price_coins=price,
        is_active=True,
    )

    messages.success(request, f"Has puesto {item.name} en el mercado por {price} monedas.")
    return redirect("rpg_market")


@login_required
@require_POST
def rpg_market_cancel(request, listing_id):
    """
    Cancelar una publicación propia.
    El objeto vuelve a aparecer en el inventario.
    """
    listing = get_object_or_404(
        MarketListing,
        pk=listing_id,
        seller=request.user,
        is_active=True,
    )
    listing.is_active = False
    listing.save()
    messages.info(request, f"Has cancelado la venta de {listing.item.name}.")
    return redirect("rpg_market")


@login_required
@require_POST
def rpg_market_buy(request, listing_id):
    """
    Comprar una oferta del mercado:
    - Verifica monedas.
    - Transfiere monedas del comprador al vendedor.
    - Transfiere el objeto al comprador.
    - Desactiva la publicación.
    """
    listing = get_object_or_404(
        MarketListing.objects.select_related("item", "seller"),
        pk=listing_id,
        is_active=True,
    )

    if listing.seller_id == request.user.id:
        messages.error(request, "No puedes comprar tu propio objeto.")
        return redirect("rpg_market")

    buyer_profile = get_or_create_profile(request.user)
    if buyer_profile.coins < listing.price_coins:
        messages.error(request, "No tienes suficientes monedas para esta compra.")
        return redirect("rpg_market")

    seller_profile = get_or_create_profile(listing.seller)

    with transaction.atomic():
        # Bloqueo básico: volvemos a verificar que sigue activo
        listing = MarketListing.objects.select_for_update().get(pk=listing.pk)
        if not listing.is_active:
            messages.error(request, "La oferta ya no está disponible.")
            return redirect("rpg_market")

        if buyer_profile.coins < listing.price_coins:
            messages.error(request, "No tienes suficientes monedas.")
            return redirect("rpg_market")

        # Transferir monedas
        buyer_profile.coins -= listing.price_coins
        seller_profile.coins += listing.price_coins
        buyer_profile.save()
        seller_profile.save()

        # Transferir objeto
        item = listing.item
        item.owner = request.user
        item.save()

        # Cerrar listing
        listing.is_active = False
        listing.buyer = request.user
        listing.save()

    messages.success(
        request,
        f"Has comprado {item.name} por {listing.price_coins} monedas."
    )
    return redirect("rpg_market")
