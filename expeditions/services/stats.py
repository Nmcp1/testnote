from ..models import ExpeditionParticipant

# Importamos TU cálculo real del RPG general:
from notes.views import get_total_stats  # usa el que suma equipo + mascota :contentReference[oaicite:3]{index=3}


def expedition_initial_stats(user):
    """
    Base expedición: 100 HP, 15 ATK, 2 DEF
    + 20% del BONUS que aporta el equipamiento (y mascota si aplica) según get_total_stats.
    """
    totals = get_total_stats(user)

    # Base “del RPG general” según tu función:
    base_general_hp = 100
    base_general_atk = 10
    base_general_def = 0  # :contentReference[oaicite:4]{index=4}

    equip_bonus_hp = max(0, int(totals["hp"]) - base_general_hp)
    equip_bonus_atk = max(0, int(totals["attack"]) - base_general_atk)
    equip_bonus_def = max(0, int(totals["defense"]) - base_general_def)

    base_hp = 100
    base_atk = 15
    base_def = 2

    hp = base_hp + int(equip_bonus_hp * 0.20)
    atk = base_atk + int(equip_bonus_atk * 0.20)
    df = base_def + int(equip_bonus_def * 0.20)

    return {
        "base_hp": base_hp, "base_attack": base_atk, "base_defense": base_def,
        "max_hp": max(1, hp), "attack": max(1, atk), "defense": max(0, df),
    }


def sync_participant_stats(participant: ExpeditionParticipant):
    """
    Recalcula stats al unirse (o si quieres recalcular al inicio).
    """
    s = expedition_initial_stats(participant.user)

    participant.base_hp = s["base_hp"]
    participant.base_attack = s["base_attack"]
    participant.base_defense = s["base_defense"]

    participant.max_hp = s["max_hp"]
    participant.attack = s["attack"]
    participant.defense = s["defense"]
    participant.current_hp = min(participant.max_hp, participant.current_hp or participant.max_hp)
    participant.save(update_fields=["base_hp","base_attack","base_defense","max_hp","attack","defense","current_hp"])
