from .models import Notification

MODERATOR_GROUP_NAME = "moderador"


def notifications_context(request):
    unread_count = 0
    is_moderator = False

    if request.user.is_authenticated:
        # Notificaciones no leídas
        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()

        # Es moderador si:
        # - es superusuario, o
        # - pertenece al grupo "moderador" (case-insensitive)
        is_moderator = (
            request.user.is_superuser
            or request.user.groups.filter(name__iexact=MODERATOR_GROUP_NAME).exists()
        )

    return {
        "unread_notifications_count": unread_count,
        "is_moderator": is_moderator,
    }
