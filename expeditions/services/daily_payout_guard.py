from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from expeditions.models import ExpeditionDailyPayout, ExpeditionRunResult
from notes.views import get_or_create_profile

REWARDS = {1: 1000, 2: 500, 3: 300}


@transaction.atomic
def try_pay_daily_top():
    today = timezone.localdate()
    day_to_pay = today - timedelta(days=1)

    # ¿Ya se pagó algo ese día?
    if ExpeditionDailyPayout.objects.filter(day=day_to_pay).exists():
        return  # ya pagado

    results = list(
        ExpeditionRunResult.objects
        .filter(day=day_to_pay)
        .order_by("-floor_reached", "created_at")[:3]
    )

    paid_users = set()

    for rank, res in enumerate(results, start=1):
        coins = REWARDS.get(rank, 0)
        if coins <= 0:
            continue

        for uid in res.member_ids:
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
