import random
from math import pow
from datetime import date

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
    PvpBattleLog
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

    # Último slot seleccionado (por defecto: arma)
    selected_slot = request.session.get(GACHA_LAST_SLOT_SESSION_KEY, "weapon")

    if request.method == "POST":
        slot_code = request.POST.get("slot", selected_slot)

        try:
            slot = ItemSlot(slot_code)
        except ValueError:
            messages.error(request, "Slot inválido.")
            return redirect("rpg_gacha")

        # Guardamos el último slot usado en la sesión
        request.session[GACHA_LAST_SLOT_SESSION_KEY] = slot.value
        selected_slot = slot.value

        COST = 15
        if profile.coins < COST:
            messages.error(request, "No tienes suficientes monedas.")
            return redirect("rpg_gacha")

        rarity = roll_rarity()
        stats = generate_item_stats(slot, rarity, from_gacha=True)
        name = f"{SLOT_LABELS[slot]} {ItemRarity(rarity).label}"

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

        profile.coins -= COST
        profile.save()

        rolled_item = item
        rolled_rarity = rarity

        messages.success(
            request,
            f"¡Has obtenido {item.name}! ATK {item.attack}, DEF {item.defense}, HP {item.hp}."
        )

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
        "selected_slot": selected_slot,
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
    items_qs = CombatItem.objects.filter(owner=request.user)
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
