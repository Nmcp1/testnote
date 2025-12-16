import random
from collections import Counter
from django.db import transaction

from ..models import ExpeditionVote, ExpeditionPhase, DecisionType


@transaction.atomic
def cast_vote(lobby, phase: str, voter_user_id: int, target_user_id: int | None):
    v = ExpeditionVote.objects.select_for_update().filter(
        lobby=lobby, phase=phase, voter_id=voter_user_id
    ).first()

    if not v:
        v = ExpeditionVote(lobby=lobby, phase=phase, voter_id=voter_user_id)

    v.target_id = target_user_id
    v.save()


@transaction.atomic
def clear_votes_for_lobby(lobby):
    ExpeditionVote.objects.filter(lobby=lobby).delete()


def _resolve_majority_target(lobby, phase: str, candidate_ids: list[int]) -> int | None:
    # votos válidos
    votes = list(
        ExpeditionVote.objects.filter(lobby=lobby, phase=phase)
        .values_list("target_id", flat=True)
    )
    votes = [v for v in votes if v in candidate_ids]

    if not votes:
        return random.choice(candidate_ids) if candidate_ids else None

    counts = Counter(votes)
    top_count = max(counts.values())
    top = [uid for uid, c in counts.items() if c == top_count]
    return random.choice(top)


def all_alive_voted(lobby, phase: str) -> bool:
    alive_ids = set(
        lobby.participants.filter(is_alive=True)
        .values_list("user_id", flat=True)
    )
    voted_ids = set(
        ExpeditionVote.objects.filter(lobby=lobby, phase=phase)
        .values_list("voter_id", flat=True)
    )
    return alive_ids.issubset(voted_ids)


@transaction.atomic
def resolve_order_votes(lobby):
    alive_ids = list(lobby.participants.filter(is_alive=True).values_list("user_id", flat=True))
    if not alive_ids:
        lobby.order_1_id = None
        lobby.order_2_id = None
        lobby.save(update_fields=["order_1", "order_2"])
        return

    if lobby.phase == ExpeditionPhase.VOTE_ORDER_1:
        pick = _resolve_majority_target(lobby, ExpeditionPhase.VOTE_ORDER_1, alive_ids)
        lobby.order_1_id = pick
        lobby.save(update_fields=["order_1"])
        return

    if lobby.phase == ExpeditionPhase.VOTE_ORDER_2:
        remaining = [u for u in alive_ids if u != lobby.order_1_id] or alive_ids
        pick = _resolve_majority_target(lobby, ExpeditionPhase.VOTE_ORDER_2, remaining)
        lobby.order_2_id = pick
        lobby.save(update_fields=["order_2"])
        return


# =========================
# DECISIONES OPCIONALES
# =========================

def maybe_roll_optional_decision(_lobby) -> bool:
    return random.random() < 0.70


@transaction.atomic
def start_optional_decision(lobby):
    dtype = random.choice([
        DecisionType.HEAL_50,
        DecisionType.DAMAGE_30,
        DecisionType.GIVE_STATS,
        DecisionType.REMOVE_STATS,
    ])
    payload = None
    if dtype in (DecisionType.GIVE_STATS, DecisionType.REMOVE_STATS):
        payload = {
            "stat": random.choice(["hp", "attack", "defense"]),
            "amount": random.randint(0, 100),
        }

    lobby.decision_type = dtype
    lobby.decision_payload = payload
    lobby.save(update_fields=["decision_type", "decision_payload"])


@transaction.atomic
def resolve_decision_vote(lobby):
    from ..models import ExpeditionParticipant

    alive_ids = list(lobby.participants.filter(is_alive=True).values_list("user_id", flat=True))
    if not alive_ids:
        return None

    target_id = _resolve_majority_target(lobby, ExpeditionPhase.DECISION, alive_ids)
    if not target_id:
        return None

    p = ExpeditionParticipant.objects.select_for_update().get(lobby=lobby, user_id=target_id)

    if lobby.decision_type == DecisionType.HEAL_50:
        heal = int(p.max_hp * 0.50)
        p.current_hp = min(p.max_hp, p.current_hp + heal)
        p.save(update_fields=["current_hp"])
        return {"type": lobby.decision_type, "target": target_id, "heal": heal}

    if lobby.decision_type == DecisionType.DAMAGE_30:
        dmg = int(p.max_hp * 0.30)
        p.current_hp = max(1, p.current_hp - dmg)
        p.save(update_fields=["current_hp"])
        return {"type": lobby.decision_type, "target": target_id, "dmg": dmg}

    payload = lobby.decision_payload or {"stat": "attack", "amount": 0}
    stat = payload.get("stat", "attack")
    amount = int(payload.get("amount", 0))
    sign = 1 if lobby.decision_type == DecisionType.GIVE_STATS else -1
    delta = sign * amount

    if stat == "hp":
        p.max_hp = max(1, p.max_hp + delta)
        p.current_hp = min(p.max_hp, max(1, p.current_hp + delta))
        p.save(update_fields=["max_hp", "current_hp"])
    elif stat == "attack":
        p.attack = max(1, p.attack + delta)
        p.save(update_fields=["attack"])
    else:
        p.defense = max(0, p.defense + delta)
        p.save(update_fields=["defense"])

    return {"type": lobby.decision_type, "target": target_id, "stat": stat, "delta": delta}
