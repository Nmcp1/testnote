import random
import string
from django.db import models
from django.contrib.auth.models import User


def generate_random_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


class InvitationCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_invitation_codes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_invitation_code'
    )
    used_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.code:
            new_code = generate_random_code()
            while InvitationCode.objects.filter(code=new_code).exists():
                new_code = generate_random_code()
            self.code = new_code
        super().save(*args, **kwargs)

    def __str__(self):
        status = "USADO" if self.used_by else "DISPONIBLE"
        return f"{self.code} ({status})"


class Note(models.Model):
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notes'
    )
    # recipient NULL => nota pública
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_notes',
        null=True,
        blank=True
    )
    text = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        kind = "privada" if self.recipient else "pública"
        return f'{self.author.username} -> {self.recipient or "ALL"} ({kind}): {self.text[:20]}'


class NoteLike(models.Model):
    note = models.ForeignKey(
        Note,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='note_likes'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('note', 'user')

    def __str__(self):
        return f'{self.user.username} ♥ {self.note.id}'


class NoteReply(models.Model):
    note = models.ForeignKey(
        Note,
        on_delete=models.CASCADE,
        related_name='replies'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='note_replies'
    )
    text = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author.username} → Note {self.note_id}: {self.text[:20]}'

class Notification(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    message = models.CharField(max_length=255)
    url = models.CharField(
        max_length=255,
        blank=True,
        help_text="URL interna para ir al detalle de la notificación."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        estado = "NUEVA" if not self.is_read else "leída"
        return f"{self.user.username} - {self.message} ({estado})"
