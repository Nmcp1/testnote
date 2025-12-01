from .models import Notification, UserProfile

MODERATOR_GROUP_NAME = "moderador"


def notifications_context(request):
    unread_count = 0
    is_moderator = False
    user_coins = 0
    user_rubies = 0

    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()

        is_moderator = (
            request.user.is_superuser
            or request.user.groups.filter(name__iexact=MODERATOR_GROUP_NAME).exists()
        )

        # Asegurar que el usuario tenga perfil y leer sus monedas
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        user_coins = profile.coins
        user_rubies = profile.rubies

    return {
        "unread_notifications_count": unread_count,
        "is_moderator": is_moderator,
        "user_coins": user_coins,
        "user_rubies": user_rubies, 
    }
