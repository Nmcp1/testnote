import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from .models import (
    ExpeditionLobby,
    ExpeditionParticipant,
    ExpeditionChatMessage,
    ExpeditionPhase,
    ExpeditionLobbyStatus,
)
from .services.enemies import enemy_for_floor
from .services.combat import (
    Fighter,
    simulate_duel,
    apply_enemy_stat_buffs,
    apply_end_of_combat_heal,
)
from .services.voting import (
    cast_vote,
    resolve_order_votes,
    clear_votes_for_lobby,
    maybe_roll_optional_decision,
    start_optional_decision,
    resolve_decision_vote,
    all_alive_voted,
)
from .services.rewards import (
    grant_base_run_rewards,
    record_run_result,
)


# =========================================================
# Helpers DB
# =========================================================

@database_sync_to_async
def user_in_lobby(lobby_id: int, user_id: int) -> bool:
    return ExpeditionParticipant.objects.filter(
        lobby_id=lobby_id, user_id=user_id
    ).exists()


@database_sync_to_async
def save_chat(lobby_id: int, user_id: int, msg: str):
    lobby = ExpeditionLobby.objects.get(id=lobby_id)
    ExpeditionChatMessage.objects.create(
        lobby=lobby,
        user_id=user_id,
        message=(msg or "")[:300],
    )


@database_sync_to_async
def get_state(lobby_id: int):
    lobby = ExpeditionLobby.objects.get(id=lobby_id)

    players = list(
        lobby.participants
        .select_related("user")
        .order_by("joined_at")
        .values(
            "user__username",
            "user_id",
            "max_hp",
            "current_hp",
            "attack",
            "defense",
            "is_alive",
        )
    )
    while len(players) < 3:
        players.append(None)

    chat = list(
        lobby.chat_messages
        .select_related("user")
        .order_by("-created_at")[:50]
        .values("user__username", "message")
    )
    chat.reverse()

    votes = list(
        lobby.votes.values("voter_id", "phase")
    )

    return {
        "lobby": {
            "id": lobby.id,
            "code": lobby.code,
            "status": lobby.status,
            "phase": lobby.phase,
            "floor": lobby.floor,
            "deadline": lobby.phase_deadline.isoformat() if lobby.phase_deadline else None,
            "order_1_id": lobby.order_1_id,
            "order_2_id": lobby.order_2_id,
            "decision": {
                "type": lobby.decision_type,
                "payload": lobby.decision_payload,
            } if lobby.decision_type else None,
            "enemy": {
                "hp": lobby.enemy_hp,
                "attack": lobby.enemy_attack,
                "defense": lobby.enemy_defense,
            } if lobby.enemy_hp is not None else None,
            "votes": votes,
            "last_effect": lobby.last_effect,   # ✅ REGISTRO
        },
        "players": players,
        "chat": [{"user": c["user__username"], "msg": c["message"]} for c in chat],
    }


# =========================================================
# TIMEOUT / FLOW
# =========================================================

@database_sync_to_async
def resolve_timeout_step(lobby_id: int) -> dict:
    lobby = ExpeditionLobby.objects.get(id=lobby_id)

    alive_ids = list(
        lobby.participants.filter(is_alive=True)
        .values_list("user_id", flat=True)
    )
    alive_count = len(alive_ids)

    # =====================================================
    # FAST-FORWARD: 1 solo jugador vivo
    # - no timers
    # - PERO sí decisiones
    # =====================================================
    if alive_count <= 1:
        resolve_order_votes(lobby)

        # spawn enemigo
        if lobby.enemy_hp is None:
            enemy = enemy_for_floor(lobby.floor)
            lobby.enemy_hp = enemy.hp
            lobby.enemy_attack = enemy.attack
            lobby.enemy_defense = enemy.defense
            lobby.save(update_fields=["enemy_hp", "enemy_attack", "enemy_defense"])

        # si ya estamos en decisión → resolverla al tiro
        if lobby.phase == ExpeditionPhase.DECISION:
            result = resolve_decision_vote(lobby)
            lobby.last_effect = result
            lobby.save(update_fields=["last_effect"])

            clear_votes_for_lobby(lobby)
            lobby.set_phase(ExpeditionPhase.COMBAT, seconds=None)
            return {"did": True, "next": "combat"}

        # si venimos de votos u otra fase → generar decisión si corresponde
        if lobby.phase in (
            ExpeditionPhase.VOTE_ORDER_1,
            ExpeditionPhase.VOTE_ORDER_2,
            ExpeditionPhase.WAITING,
        ):
            if maybe_roll_optional_decision(lobby):
                start_optional_decision(lobby)

                result = resolve_decision_vote(lobby)
                lobby.last_effect = result
                lobby.save(update_fields=["last_effect"])

        clear_votes_for_lobby(lobby)
        lobby.set_phase(ExpeditionPhase.COMBAT, seconds=None)
        return {"did": True, "next": "combat"}

    # =====================================================
    # LÓGICA NORMAL CON DEADLINES
    # =====================================================
    if not lobby.phase_deadline:
        return {"did": False}

    if timezone.now() < lobby.phase_deadline:
        return {"did": False}

    # -------------------------
    # VOTE ORDER 1
    # -------------------------
    if lobby.phase == ExpeditionPhase.VOTE_ORDER_1:
        resolve_order_votes(lobby)

        # si quedan solo 2 vivos, no hay vote_order_2
        if alive_count == 2:
            if lobby.enemy_hp is None:
                enemy = enemy_for_floor(lobby.floor)
                lobby.enemy_hp = enemy.hp
                lobby.enemy_attack = enemy.attack
                lobby.enemy_defense = enemy.defense
                lobby.save(update_fields=["enemy_hp", "enemy_attack", "enemy_defense"])

            if maybe_roll_optional_decision(lobby):
                start_optional_decision(lobby)
                lobby.set_phase(ExpeditionPhase.DECISION, seconds=20)
                return {"did": True, "next": "decision"}

            clear_votes_for_lobby(lobby)
            lobby.set_phase(ExpeditionPhase.COMBAT, seconds=None)
            return {"did": True, "next": "combat"}

        lobby.set_phase(ExpeditionPhase.VOTE_ORDER_2, seconds=20)
        return {"did": True, "next": "vote2"}

    # -------------------------
    # VOTE ORDER 2
    # -------------------------
    if lobby.phase == ExpeditionPhase.VOTE_ORDER_2:
        resolve_order_votes(lobby)

        if lobby.enemy_hp is None:
            enemy = enemy_for_floor(lobby.floor)
            lobby.enemy_hp = enemy.hp
            lobby.enemy_attack = enemy.attack
            lobby.enemy_defense = enemy.defense
            lobby.save(update_fields=["enemy_hp", "enemy_attack", "enemy_defense"])

        if maybe_roll_optional_decision(lobby):
            start_optional_decision(lobby)
            lobby.set_phase(ExpeditionPhase.DECISION, seconds=20)
            return {"did": True, "next": "decision"}

        clear_votes_for_lobby(lobby)
        lobby.set_phase(ExpeditionPhase.COMBAT, seconds=None)
        return {"did": True, "next": "combat"}

    # -------------------------
    # DECISION
    # -------------------------
    if lobby.phase == ExpeditionPhase.DECISION:
        result = resolve_decision_vote(lobby)
        lobby.last_effect = result
        lobby.save(update_fields=["last_effect"])

        clear_votes_for_lobby(lobby)
        lobby.set_phase(ExpeditionPhase.COMBAT, seconds=None)
        return {"did": True, "next": "combat"}

    return {"did": False}


# =========================================================
# COMBATE
# =========================================================

@database_sync_to_async
def run_combat_sync(lobby_id: int):
    lobby = ExpeditionLobby.objects.get(id=lobby_id)

    if lobby.enemy_hp is None:
        enemy = enemy_for_floor(lobby.floor)
        lobby.enemy_hp = enemy.hp
        lobby.enemy_attack = enemy.attack
        lobby.enemy_defense = enemy.defense
        lobby.save(update_fields=["enemy_hp", "enemy_attack", "enemy_defense"])

    enemy_hp = int(lobby.enemy_hp or 1)
    enemy_atk = int(lobby.enemy_attack or 1)
    enemy_def = int(lobby.enemy_defense or 0)

    alive_participants = list(
        ExpeditionParticipant.objects
        .select_related("user")
        .filter(lobby=lobby, is_alive=True)
    )

    if not alive_participants:
        lobby.status = ExpeditionLobbyStatus.FINISHED
        lobby.phase = ExpeditionPhase.ENDED
        lobby.phase_deadline = None
        lobby.ended_at = timezone.now()
        lobby.save(update_fields=["status", "phase", "phase_deadline", "ended_at"])
        return

    alive_ids = [p.user_id for p in alive_participants]
    order = [lobby.order_1_id, lobby.order_2_id]
    third = next((u for u in alive_ids if u not in order), None)
    order.append(third)

    killer_id = None
    enemy_snapshot = None

    for uid in order:
        if uid is None:
            continue

        p = next((x for x in alive_participants if x.user_id == uid), None)
        if not p or not p.is_alive:
            continue

        fighter = Fighter(
            username=p.user.username,
            max_hp=p.max_hp,
            hp=p.current_hp,
            attack=p.attack,
            defense=p.defense,
        )

        result = simulate_duel(fighter, enemy_hp, enemy_atk, enemy_def)
        p.current_hp = result.fighter_end_hp

        if not result.victory:
            p.is_alive = False
            p.save(update_fields=["current_hp", "is_alive"])
            continue

        p.save(update_fields=["current_hp"])
        killer_id = p.user_id
        enemy_snapshot = {"hp": enemy_hp, "attack": enemy_atk, "defense": enemy_def}
        break

    participants_all = list(lobby.participants.all())

    if enemy_snapshot and killer_id:
        apply_enemy_stat_buffs(participants_all, enemy_snapshot, killer_id)
        apply_end_of_combat_heal(participants_all)

        lobby.last_killer_id = killer_id
        lobby.last_enemy_snapshot = enemy_snapshot

        lobby.enemy_hp = None
        lobby.enemy_attack = None
        lobby.enemy_defense = None

        # ❌ NO limpiar last_effect aquí
        lobby.save(update_fields=[
            "last_killer",
            "last_enemy_snapshot",
            "enemy_hp",
            "enemy_attack",
            "enemy_defense",
        ])


    alive_count = lobby.participants.filter(is_alive=True).count()
    if alive_count == 0:
        lobby.status = ExpeditionLobbyStatus.FINISHED
        lobby.phase = ExpeditionPhase.ENDED
        lobby.phase_deadline = None
        lobby.ended_at = timezone.now()
        lobby.save(update_fields=["status", "phase", "phase_deadline", "ended_at"])

        grant_base_run_rewards(lobby, lobby.floor)
        record_run_result(lobby, lobby.floor)
        return

    if enemy_snapshot and killer_id:
        lobby.floor += 1
        lobby.order_1 = None
        lobby.order_2 = None
        lobby.decision_type = None
        lobby.decision_payload = None

        lobby.save(update_fields=[
            "floor",
            "order_1",
            "order_2",
            "decision_type",
            "decision_payload",
        ])

        lobby.set_phase(ExpeditionPhase.VOTE_ORDER_1, seconds=20)


# =========================================================
# CONSUMER
# =========================================================

class ExpeditionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close()
            return

        self.lobby_id = int(self.scope["url_route"]["kwargs"]["lobby_id"])
        self.group_name = f"expedition_{self.lobby_id}"

        if not await user_in_lobby(self.lobby_id, user.id):
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        state = await get_state(self.lobby_id)
        await self.send(text_data=json.dumps({"type": "state", "data": state}))

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        payload = json.loads(text_data)
        t = payload.get("type")

        if t == "chat":
            await save_chat(self.lobby_id, self.scope["user"].id, payload.get("msg", ""))
            await self.broadcast_state()
            return

        if t == "vote":
            await self.handle_vote(payload)
            return

        if t == "tick":
            await self.check_phase_timeout()
            return

    async def broadcast_state(self):
        state = await get_state(self.lobby_id)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "state_msg", "state": state}
        )

    async def state_msg(self, event):
        await self.send(text_data=json.dumps({"type": "state", "data": event["state"]}))

    async def handle_vote(self, payload):
        target_id = payload.get("target_user_id")
        try:
            target_id = int(target_id) if target_id is not None else None
        except Exception:
            target_id = None

        state = await get_state(self.lobby_id)
        phase = state["lobby"]["phase"]

        if phase not in [
            ExpeditionPhase.VOTE_ORDER_1,
            ExpeditionPhase.VOTE_ORDER_2,
            ExpeditionPhase.DECISION,
        ]:
            return

        await database_sync_to_async(self._cast_vote_and_maybe_resolve)(phase, target_id)
        await self.broadcast_state()

    def _cast_vote_and_maybe_resolve(self, phase, target_id):
        lobby = ExpeditionLobby.objects.get(id=self.lobby_id)
        cast_vote(lobby, phase, self.scope["user"].id, target_id)

        if all_alive_voted(lobby, phase):
            lobby.phase_deadline = timezone.now()
            lobby.save(update_fields=["phase_deadline"])

    async def check_phase_timeout(self):
        step = await resolve_timeout_step(self.lobby_id)
        if not step.get("did"):
            return

        if step.get("next") == "combat":
            await run_combat_sync(self.lobby_id)

        await self.broadcast_state()
