# notes/models.py
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
        # Si el código no existe, generarlo
        if not self.code:
            new_code = generate_random_code()

            # Asegurar unicidad
            while InvitationCode.objects.filter(code=new_code).exists():
                new_code = generate_random_code()

            self.code = new_code

        super().save(*args, **kwargs)

    def __str__(self):
        status = "USADO" if self.used_by else "DISPONIBLE"
        return f"{self.code} ({status})"


class Note(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notes')
    text = models.CharField(max_length=100)  # hasta 100 caracteres
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']  # más nuevas primero

    def __str__(self):
        return f'{self.author.username}: {self.text[:20]}'
