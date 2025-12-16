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


def _apply_heal_pct(p, pct: int):
    """
    Cura current_hp en base a max_hp (sin cambiar max_hp).
    pct = 10..100
    """
    pct = int(pct)
    max_hp = int(p.max_hp)
    cur = int(p.current_hp)

    heal = int(round(max_hp * pct / 100))
    new_cur = min(max_hp, cur + max(0, heal))

    p.current_hp = new_cur
    p.save(update_fields=["current_hp"])
    return {"pct": pct, "heal": (new_cur - cur)}


def _apply_heal_flat(p, amount: int):
    """
    Cura current_hp con un número fijo (sin cambiar max_hp).
    """
    amount = int(amount)
    max_hp = int(p.max_hp)
    cur = int(p.current_hp)

    new_cur = min(max_hp, cur + max(0, amount))

    p.current_hp = new_cur
    p.save(update_fields=["current_hp"])
    return {"amount": amount, "heal": (new_cur - cur)}


@transaction.atomic
def resolve_order_votes(lobby):
    alive_ids = list(
        lobby.participants.filter(is_alive=True).values_list("user_id", flat=True)
    )

    if not alive_ids:
        lobby.order_1_id = None
        lobby.order_2_id = None
        lobby.save(update_fields=["order_1_id", "order_2_id"])
        return {"done": True}

    # ✅ Si queda 1 vivo: no se vota nada.
    if len(alive_ids) == 1:
        lobby.order_1_id = alive_ids[0]
        lobby.order_2_id = None
        lobby.save(update_fields=["order_1_id", "order_2_id"])
        return {"done": True, "skip": "only_one"}

    # ✅ Si queda 2 vivos: solo voto para el primero, el segundo queda automático.
    if lobby.phase == ExpeditionPhase.VOTE_ORDER_1:
        pick = _resolve_majority_target(lobby, ExpeditionPhase.VOTE_ORDER_1, alive_ids)
        lobby.order_1_id = pick
        remaining = [u for u in alive_ids if u != pick] or alive_ids
        lobby.order_2_id = remaining[0] if remaining else None
        lobby.save(update_fields=["order_1_id", "order_2_id"])
        return {"done": True, "skip": "only_two"}

    # ✅ 3 vivos: comportamiento normal
    if lobby.phase == ExpeditionPhase.VOTE_ORDER_2:
        remaining = [u for u in alive_ids if u != lobby.order_1_id] or alive_ids
        pick = _resolve_majority_target(lobby, ExpeditionPhase.VOTE_ORDER_2, remaining)
        lobby.order_2_id = pick
        lobby.save(update_fields=["order_2_id"])
        return {"done": True}

    return {"done": False}


# =========================
# DECISIONES OPCIONALES
# =========================

def maybe_roll_optional_decision(_lobby) -> bool:
    # 70% por piso (como originalmente)
    return random.random() < 0.70


def _rand_stat():
    return random.choice(["hp", "attack", "defense"])


def _apply_delta(p, stat: str, delta: int):
    """Aplica delta permanente al stat (y ajusta current_hp si corresponde)."""
    delta = int(delta)

    if stat == "hp":
        p.max_hp = max(1, int(p.max_hp) + delta)
        p.current_hp = min(p.max_hp, max(1, int(p.current_hp) + delta))
        p.save(update_fields=["max_hp", "current_hp"])
        return

    if stat == "attack":
        p.attack = max(1, int(p.attack) + delta)
        p.save(update_fields=["attack"])
        return

    p.defense = max(0, int(p.defense) + delta)
    p.save(update_fields=["defense"])


def _apply_percent(p, stat: str, pct: int):
    """
    Cambia un stat por porcentaje (positivo o negativo) de forma permanente.
    pct = +20 => +20%, pct = -15 => -15%
    """
    pct = int(pct)

    if stat == "hp":
        base = int(p.max_hp)
        new_val = max(1, int(round(base * (100 + pct) / 100)))
        diff = new_val - base
        _apply_delta(p, "hp", diff)
        return {"stat": "hp", "pct": pct, "diff": diff}

    if stat == "attack":
        base = int(p.attack)
        new_val = max(1, int(round(base * (100 + pct) / 100)))
        diff = new_val - base
        _apply_delta(p, "attack", diff)
        return {"stat": "attack", "pct": pct, "diff": diff}

    base = int(p.defense)
    new_val = max(0, int(round(base * (100 + pct) / 100)))
    diff = new_val - base
    _apply_delta(p, "defense", diff)
    return {"stat": "defense", "pct": pct, "diff": diff}


@transaction.atomic
def start_optional_decision(lobby):
    dtype = random.choice([
        DecisionType.STAT_BOON_SMALL,
        DecisionType.STAT_BOON_BIG,
        DecisionType.STAT_CURSE_SMALL,
        DecisionType.STAT_CURSE_BIG,
        DecisionType.GAMBLE_SPIKE,
        DecisionType.REROLL_SPLIT,
        DecisionType.LIFE_TRADE,
        DecisionType.GLASS_CANNON,
        DecisionType.TURTLE,
        DecisionType.BERSERK,
        DecisionType.BLOODPACT,
        DecisionType.FORTUNE_WHEEL,
        DecisionType.HP_PERCENT_SHIFT,
        DecisionType.ATK_PERCENT_SHIFT,
        DecisionType.DEF_PERCENT_SHIFT,
        DecisionType.HEAL_PCT_SMALL,
        DecisionType.HEAL_PCT_BIG,
        DecisionType.HEAL_FLAT_SMALL,
        DecisionType.HEAL_FLAT_BIG,
        DecisionType.HEAL_TO_FULL,
    ])

    payload = {}

    SMALL = (5, 18)
    BIG = (20, 60)

    # ✅ FIX: no uses `"SMALL" in dtype` (dtype no es str)
    if dtype in (DecisionType.STAT_BOON_SMALL, DecisionType.STAT_CURSE_SMALL):
        stat = _rand_stat()
        amount = random.randint(*SMALL)
        if dtype == DecisionType.STAT_CURSE_SMALL:
            amount = -amount
        payload = {"stat": stat, "delta": amount}

    elif dtype in (DecisionType.STAT_BOON_BIG, DecisionType.STAT_CURSE_BIG):
        stat = _rand_stat()
        amount = random.randint(*BIG)
        if dtype == DecisionType.STAT_CURSE_BIG:
            amount = -amount
        payload = {"stat": stat, "delta": amount}

    elif dtype == DecisionType.GAMBLE_SPIKE:
        stat = _rand_stat()
        amount = random.randint(30, 90)
        if random.random() < 0.5:
            amount = -amount
        payload = {"stat": stat, "delta": amount, "coinflip": True}

    elif dtype == DecisionType.REROLL_SPLIT:
        stat_from = _rand_stat()
        stat_to = random.choice([s for s in ["hp", "attack", "defense"] if s != stat_from])
        x = random.randint(10, 70)
        payload = {"from": stat_from, "to": stat_to, "amount": x}

    elif dtype == DecisionType.LIFE_TRADE:
        hp_gain = random.randint(30, 120)
        penalty_stat = random.choice(["attack", "defense"])
        penalty = -random.randint(8, 40)
        payload = {"hp_gain": hp_gain, "penalty_stat": penalty_stat, "penalty": penalty}

    elif dtype == DecisionType.GLASS_CANNON:
        atk_gain = random.randint(15, 70)
        def_loss = -random.randint(5, 35)
        payload = {"atk_gain": atk_gain, "def_loss": def_loss}

    elif dtype == DecisionType.TURTLE:
        def_gain = random.randint(6, 40)
        atk_loss = -random.randint(5, 25)
        payload = {"def_gain": def_gain, "atk_loss": atk_loss}

    elif dtype == DecisionType.BERSERK:
        atk_gain = random.randint(10, 55)
        hp_loss = -random.randint(10, 80)
        payload = {"atk_gain": atk_gain, "hp_loss": hp_loss}

    elif dtype == DecisionType.BLOODPACT:
        if random.random() < 0.5:
            payload = {"mode": "atk_up_hp_down", "atk": random.randint(10, 60), "hp": -random.randint(15, 90)}
        else:
            payload = {"mode": "hp_up_atk_down", "hp": random.randint(20, 120), "atk": -random.randint(5, 35)}

    elif dtype == DecisionType.FORTUNE_WHEEL:
        outcomes = [
            {"stat": "attack", "delta": random.randint(8, 40)},
            {"stat": "defense", "delta": random.randint(4, 25)},
            {"stat": "hp", "delta": random.randint(20, 140)},
            {"stat": "attack", "delta": -random.randint(8, 35)},
            {"stat": "defense", "delta": -random.randint(3, 20)},
            {"stat": "hp", "delta": -random.randint(15, 120)},
        ]
        pick = random.choice(outcomes)
        payload = {"picked": pick}

    elif dtype == DecisionType.HP_PERCENT_SHIFT:
        pct = random.randint(-25, 35)
        payload = {"stat": "hp", "pct": pct}

    elif dtype == DecisionType.ATK_PERCENT_SHIFT:
        pct = random.randint(-25, 35)
        payload = {"stat": "attack", "pct": pct}

    elif dtype == DecisionType.DEF_PERCENT_SHIFT:
        pct = random.randint(-30, 45)
        payload = {"stat": "defense", "pct": pct}

    # ✅ Curaciones (solo current_hp, no tocan max_hp)
    elif dtype == DecisionType.HEAL_PCT_SMALL:
        pct = random.randint(10, 35)
        payload = {"pct": pct}

    elif dtype == DecisionType.HEAL_PCT_BIG:
        pct = random.randint(40, 80)
        payload = {"pct": pct}

    elif dtype == DecisionType.HEAL_FLAT_SMALL:
        amount = random.randint(10, 80)
        payload = {"amount": amount}

    elif dtype == DecisionType.HEAL_FLAT_BIG:
        amount = random.randint(90, 250)
        payload = {"amount": amount}

    elif dtype == DecisionType.HEAL_TO_FULL:
        payload = {"pct": 100}

    lobby.decision_type = dtype
    lobby.decision_payload = payload
    lobby.save(update_fields=["decision_type", "decision_payload"])


@transaction.atomic
def resolve_decision_vote(lobby):
    from ..models import ExpeditionParticipant

    alive_ids = list(
        lobby.participants.filter(is_alive=True).values_list("user_id", flat=True)
    )
    if not alive_ids:
        return None

    # ✅ Si queda 1 vivo: target automático
    if len(alive_ids) == 1:
        target_id = alive_ids[0]
    else:
        target_id = _resolve_majority_target(lobby, ExpeditionPhase.DECISION, alive_ids)

    if not target_id:
        return None

    p = ExpeditionParticipant.objects.select_for_update().get(lobby=lobby, user_id=target_id)

    dtype = lobby.decision_type
    payload = lobby.decision_payload or {}

    # 1) Buff/debuff directo por delta
    if dtype in (
        DecisionType.STAT_BOON_SMALL,
        DecisionType.STAT_BOON_BIG,
        DecisionType.STAT_CURSE_SMALL,
        DecisionType.STAT_CURSE_BIG,
        DecisionType.GAMBLE_SPIKE,
    ):
        stat = payload.get("stat", "attack")
        delta = int(payload.get("delta", 0))
        _apply_delta(p, stat, delta)
        return {"type": dtype, "target": target_id, "stat": stat, "delta": delta}

    # 2) Reroll split
    if dtype == DecisionType.REROLL_SPLIT:
        stat_from = payload.get("from", "attack")
        stat_to = payload.get("to", "defense")
        x = int(payload.get("amount", 0))
        _apply_delta(p, stat_from, -x)
        _apply_delta(p, stat_to, +x)
        return {"type": dtype, "target": target_id, "from": stat_from, "to": stat_to, "amount": x}

    # 3) Paquetes combinados
    if dtype == DecisionType.LIFE_TRADE:
        hp_gain = int(payload.get("hp_gain", 0))
        pen_stat = payload.get("penalty_stat", "attack")
        pen = int(payload.get("penalty", 0))
        _apply_delta(p, "hp", hp_gain)
        _apply_delta(p, pen_stat, pen)
        return {"type": dtype, "target": target_id, "hp_gain": hp_gain, "penalty_stat": pen_stat, "penalty": pen}

    if dtype == DecisionType.GLASS_CANNON:
        atk_gain = int(payload.get("atk_gain", 0))
        def_loss = int(payload.get("def_loss", 0))
        _apply_delta(p, "attack", atk_gain)
        _apply_delta(p, "defense", def_loss)
        return {"type": dtype, "target": target_id, "atk_gain": atk_gain, "def_loss": def_loss}

    if dtype == DecisionType.TURTLE:
        def_gain = int(payload.get("def_gain", 0))
        atk_loss = int(payload.get("atk_loss", 0))
        _apply_delta(p, "defense", def_gain)
        _apply_delta(p, "attack", atk_loss)
        return {"type": dtype, "target": target_id, "def_gain": def_gain, "atk_loss": atk_loss}

    if dtype == DecisionType.BERSERK:
        atk_gain = int(payload.get("atk_gain", 0))
        hp_loss = int(payload.get("hp_loss", 0))
        _apply_delta(p, "attack", atk_gain)
        _apply_delta(p, "hp", hp_loss)
        return {"type": dtype, "target": target_id, "atk_gain": atk_gain, "hp_loss": hp_loss}

    if dtype == DecisionType.BLOODPACT:
        mode = payload.get("mode")
        if mode == "atk_up_hp_down":
            atk = int(payload.get("atk", 0))
            hp = int(payload.get("hp", 0))
            _apply_delta(p, "attack", atk)
            _apply_delta(p, "hp", hp)
            return {"type": dtype, "target": target_id, "mode": mode, "atk": atk, "hp": hp}
        else:
            hp = int(payload.get("hp", 0))
            atk = int(payload.get("atk", 0))
            _apply_delta(p, "hp", hp)
            _apply_delta(p, "attack", atk)
            return {"type": dtype, "target": target_id, "mode": mode, "hp": hp, "atk": atk}

    # 4) Ruleta
    if dtype == DecisionType.FORTUNE_WHEEL:
        picked = payload.get("picked") or {"stat": "attack", "delta": 0}
        stat = picked.get("stat", "attack")
        delta = int(picked.get("delta", 0))
        _apply_delta(p, stat, delta)
        return {"type": dtype, "target": target_id, "stat": stat, "delta": delta, "wheel": True}

    # ✅ 5) Curaciones (solo current_hp)
    if dtype in (DecisionType.HEAL_PCT_SMALL, DecisionType.HEAL_PCT_BIG):
        pct = int(payload.get("pct", 10))
        info = _apply_heal_pct(p, pct)
        return {"type": dtype, "target": target_id, "heal_type": "pct", **info}

    if dtype in (DecisionType.HEAL_FLAT_SMALL, DecisionType.HEAL_FLAT_BIG):
        amount = int(payload.get("amount", 10))
        info = _apply_heal_flat(p, amount)
        return {"type": dtype, "target": target_id, "heal_type": "flat", **info}

    if dtype == DecisionType.HEAL_TO_FULL:
        info = _apply_heal_pct(p, 100)
        return {"type": dtype, "target": target_id, "heal_type": "pct", **info}

    # 6) Porcentaje permanente
    if dtype in (DecisionType.HP_PERCENT_SHIFT, DecisionType.ATK_PERCENT_SHIFT, DecisionType.DEF_PERCENT_SHIFT):
        stat = payload.get("stat", "attack")
        pct = int(payload.get("pct", 0))
        info = _apply_percent(p, stat, pct)
        return {"type": dtype, "target": target_id, **info}

    return {"type": dtype, "target": target_id}
