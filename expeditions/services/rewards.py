from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from ..models import (
    ExpeditionDailyEarning,
    ExpeditionRunResult,
    ExpeditionParticipant,
)


DAILY_CAP = 500


def _local_day():
    # Usa TIME_ZONE del proyecto (debería ser America/Santiago)
    return timezone.localdate()


@transaction.atomic
def grant_base_run_rewards(lobby, floor_reached: int):
    """
    Recompensa monetaria por run (por piso alcanzado) con cap diario 500.
    Ajusta la fórmula como quieras.
    """
    # fórmula simple (ejemplo): 20 por piso alcanzado
    reward = max(0, int(floor_reached) * 20)

    day = _local_day()

    # Todos los participantes del lobby (vivos o muertos) ganan
    user_ids = list(
        lobby.participants.values_list("user_id", flat=True)
    )

    for uid in user_ids:
        earning, _ = ExpeditionDailyEarning.objects.get_or_create(
            user_id=uid,
            day=day,
            defaults={"earned_coins": 0},
        )

        remaining = max(0, DAILY_CAP - earning.earned_coins)
        add = min(reward, remaining)

        if add <= 0:
            continue

        earning.earned_coins += add
        earning.save(update_fields=["earned_coins"])

        # Sumamos al saldo real del usuario (tu sistema usa profile)
        from notes.views import get_or_create_profile  # tu helper existente
        profile = get_or_create_profile(earning.user)
        profile.coins += add
        profile.save(update_fields=["coins"])


@transaction.atomic
def record_run_result(lobby, floor_reached: int):
    """
    Guarda resultado del equipo para el Top Diario.
    """
    day = _local_day()
    member_ids = list(
        lobby.participants.order_by("joined_at").values_list("user_id", flat=True)
    )
    ExpeditionRunResult.objects.create(
        lobby=lobby,
        day=day,
        floor_reached=max(1, int(floor_reached)),
        member_ids=member_ids,
    )
