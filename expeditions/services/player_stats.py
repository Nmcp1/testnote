from notes.views import get_total_stats  # <-- tu función real


BASE_EXP_HP = 100
BASE_EXP_ATK = 15
BASE_EXP_DEF = 2

BASE_RPG_HP = 100
BASE_RPG_ATK = 10
BASE_RPG_DEF = 0


def expedition_initial_stats(user):
    """
    Modo expedición:
    - Base expedición: 100 HP, 15 ATK, 2 DEF
    - + 20% del BONUS (equipo + mascota) del jugador.
      BONUS = total_stats - base_rpg
    """
    totals = get_total_stats(user)

    bonus_hp = max(0, int(totals["hp"]) - BASE_RPG_HP)
    bonus_atk = max(0, int(totals["attack"]) - BASE_RPG_ATK)
    bonus_def = max(0, int(totals["defense"]) - BASE_RPG_DEF)

    hp = BASE_EXP_HP + int(bonus_hp * 0.20)
    atk = BASE_EXP_ATK + int(bonus_atk * 0.20)
    df = BASE_EXP_DEF + int(bonus_def * 0.20)

    return {
        "base_hp": BASE_EXP_HP,
        "base_attack": BASE_EXP_ATK,
        "base_defense": BASE_EXP_DEF,
        "max_hp": max(1, hp),
        "attack": max(1, atk),
        "defense": max(0, df),
    }
