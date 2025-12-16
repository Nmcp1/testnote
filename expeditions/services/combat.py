from dataclasses import dataclass


@dataclass
class Fighter:
    username: str
    max_hp: int
    hp: int
    attack: int
    defense: int


@dataclass
class DuelResult:
    victory: bool
    fighter_end_hp: int
    log: list[str]


def simulate_duel(f: Fighter, enemy_hp: int, enemy_atk: int, enemy_def: int, max_turns: int = 50) -> DuelResult:
    log = []
    p_hp = int(f.hp)
    e_hp = int(enemy_hp)

    for t in range(1, max_turns + 1):
        if p_hp <= 0 or e_hp <= 0:
            break

        # jugador pega
        dmg = max(1, f.attack - enemy_def)
        e_hp -= dmg
        log.append(f"T{t}: {f.username} golpea por {dmg} (enemigo {max(e_hp,0)} HP)")
        if e_hp <= 0:
            break

        # enemigo pega
        edmg = max(1, enemy_atk - f.defense)
        p_hp -= edmg
        log.append(f"T{t}: enemigo golpea por {edmg} ({f.username} {max(p_hp,0)} HP)")

    victory = e_hp <= 0 and p_hp > 0
    return DuelResult(victory=victory, fighter_end_hp=max(p_hp, 0), log=log)


def apply_enemy_stat_buffs(participants, enemy_snapshot: dict | None, killer_user_id: int | None):
    """
    - Todos ganan 5% de atk/def/hp del enemigo
    - El killer gana 15%
    """
    if not enemy_snapshot:
        return

    ehp = int(enemy_snapshot.get("hp", 0))
    eatk = int(enemy_snapshot.get("attack", 0))
    edef = int(enemy_snapshot.get("defense", 0))

    for p in participants:
        if not p.is_alive:
            continue

        base_pct = 0.05
        killer_pct = 0.15 if killer_user_id and p.user_id == killer_user_id else 0.0
        pct = base_pct + killer_pct

        add_hp = int(ehp * pct)
        add_atk = int(eatk * pct)
        add_def = int(edef * pct)

        p.max_hp += add_hp
        p.current_hp += add_hp
        p.attack += add_atk
        p.defense += add_def
        p.save(update_fields=["max_hp", "current_hp", "attack", "defense"])


def apply_end_of_combat_heal(participants):
    """
    Todos curan 10% de su hp máxima al finalizar un combate
    """
    for p in participants:
        if not p.is_alive:
            continue
        heal = int(p.max_hp * 0.10)
        p.current_hp = min(p.max_hp, p.current_hp + heal)
        p.save(update_fields=["current_hp"])
