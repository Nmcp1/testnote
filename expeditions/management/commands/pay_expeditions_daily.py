from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from expeditions.models import ExpeditionRunResult, ExpeditionDailyPayout
from notes.views import get_or_create_profile

REWARDS = {1: 600, 2: 400, 3: 200}


class Command(BaseCommand):
    help = "Paga recompensas del Top Diario de Expediciones para el día anterior."

    @transaction.atomic
    def handle(self, *args, **options):
        # A las 00:00 se paga el día ANTERIOR
        day_to_pay = timezone.localdate() - timedelta(days=1)

        results = list(
            ExpeditionRunResult.objects
            .filter(day=day_to_pay)
            .order_by("-floor_reached", "created_at")[:3]
        )

        if not results:
            self.stdout.write(self.style.WARNING(f"No hay resultados para {day_to_pay}."))
            return

        paid_users = set(
            ExpeditionDailyPayout.objects
            .filter(day=day_to_pay)
            .values_list("user_id", flat=True)
        )

        for rank, res in enumerate(results, start=1):
            coins = REWARDS.get(rank, 0)
            if coins <= 0:
                continue

            for uid in (res.member_ids or []):
                if uid in paid_users:
                    continue

                payout = ExpeditionDailyPayout.objects.create(
                    day=day_to_pay,
                    user_id=uid,
                    coins=coins,
                    rank=rank,
                )

                profile = get_or_create_profile(payout.user)
                profile.coins += coins
                profile.save(update_fields=["coins"])

                paid_users.add(uid)

        self.stdout.write(self.style.SUCCESS(f"Pagos realizados para {day_to_pay}."))
