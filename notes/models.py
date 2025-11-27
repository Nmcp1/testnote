from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import string
import random


def generate_invitation_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    coins = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Perfil de {self.user.username} (monedas: {self.coins})"


class Note(models.Model):
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notes_authored'
    )
    # Si recipient es NULL => nota pública
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notes_received',
        null=True,
        blank=True,
    )
    text = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        if self.recipient:
            return f"Privada de {self.author} para {self.recipient}: {self.text[:20]}"
        return f"Publica de {self.author}: {self.text[:20]}"


class NoteLike(models.Model):
    note = models.ForeignKey(
        Note, on_delete=models.CASCADE, related_name='likes'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='note_likes'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('note', 'user')

    def __str__(self):
        return f"{self.user} likeó {self.note_id}"


class NoteReply(models.Model):
    note = models.ForeignKey(
        Note, on_delete=models.CASCADE, related_name='replies'
    )
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='note_replies'
    )
    text = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply de {self.author} en nota {self.note_id}"


class Notification(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notifications'
    )
    message = models.CharField(max_length=255)
    url = models.CharField(
        max_length=255,
        blank=True,
        help_text="URL interna para ir al detalle (ej: nota o privadas).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        estado = "NUEVA" if not self.is_read else "leída"
        return f"{self.user.username} - {self.message} ({estado})"


class InvitationCode(models.Model):
    code = models.CharField(max_length=8, unique=True, default=generate_invitation_code)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='invitation_codes_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invitation_code_used',
    )
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status = "USADO" if self.used_by else "DISPONIBLE"
        return f"{self.code} ({status})"


class MineGameResult(models.Model):
    RESULT_RETIRE = "retire"
    RESULT_BOMB = "bomb"

    RESULT_CHOICES = [
        (RESULT_RETIRE, "Retiro"),
        (RESULT_BOMB, "Bomba"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="mine_games",
    )
    score = models.PositiveIntegerField(default=0)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    finished_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-finished_at"]

    def __str__(self):
        return f"{self.user.username} - {self.score} pts ({self.get_result_display()})"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Crea el perfil automáticamente al crear un usuario.
    """
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Por si en el futuro se modifican cosas del perfil.
    """
    if hasattr(instance, "profile"):
        instance.profile.save()
