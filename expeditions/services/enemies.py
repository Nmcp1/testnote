from dataclasses import dataclass
from math import pow


@dataclass
class Enemy:
    hp: int
    attack: int
    defense: int


def enemy_for_floor(floor: int) -> Enemy:
    base_hp = 100
    base_atk = 25
    base_def = 10

    hp = int(base_hp * pow(1.18, floor))
    atk = int(base_atk * pow(1.14, floor))
    df = int(base_def * pow(1.12, floor))

    return Enemy(
        hp=max(hp, 1),
        attack=max(atk, 1),
        defense=max(df, 0),
    )


def as_dict(enemy: Enemy) -> dict:
    return {"hp": enemy.hp, "attack": enemy.attack, "defense": enemy.defense}
