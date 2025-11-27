from django.db import models
from django.contrib.auth.models import User
import string
import random
from django.utils import timezone


def generate_invitation_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


class Note(models.Model):
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notes_authored'
    )
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


class UserProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile"
    )
    coins = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Equipamiento actual
    equipped_weapon = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    equipped_helmet = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    equipped_armor = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    equipped_pants = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    equipped_boots = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    equipped_shield = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    equipped_amulet1 = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    equipped_amulet2 = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    equipped_amulet3 = models.ForeignKey(
        'CombatItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )

    def __str__(self):
        return f"Perfil de {self.user.username} (monedas: {self.coins})"


class MineGameResult(models.Model):
    RESULT_RETIRE = "retire"
    RESULT_BOMB = "bomb"

    RESULT_CHOICES = [
        (RESULT_RETIRE, "Se retiró"),
        (RESULT_BOMB, "Pisó bomba"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mine_results")
    score = models.PositiveIntegerField(default=0)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    finished_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-finished_at"]

    def __str__(self):
        return f"{self.user.username} - {self.result} ({self.score} pts)"


class ItemRarity(models.TextChoices):
    BASIC = "basic", "Básica"
    UNCOMMON = "uncommon", "Poco común"
    SPECIAL = "special", "Especial"
    EPIC = "epic", "Épica"
    LEGENDARY = "legendary", "Legendaria"
    MYTHIC = "mythic", "Mítica"
    ASCENDED = "ascended", "Ascendida"


class ItemSlot(models.TextChoices):
    WEAPON = "weapon", "Arma"
    HELMET = "helmet", "Casco"
    ARMOR = "armor", "Armadura"
    PANTS = "pants", "Pantalones"
    BOOTS = "boots", "Botas"
    SHIELD = "shield", "Escudo"
    AMULET = "amulet", "Amuleto"


class ItemSource(models.TextChoices):
    SHOP = "shop", "Tienda"
    GACHA = "gacha", "Gacha"
    DROP = "drop", "Drop"


class CombatItem(models.Model):
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="combat_items"
    )
    name = models.CharField(max_length=100)
    slot = models.CharField(max_length=20, choices=ItemSlot.choices)
    rarity = models.CharField(max_length=20, choices=ItemRarity.choices)
    source = models.CharField(
        max_length=10, choices=ItemSource.choices, default=ItemSource.GACHA
    )

    attack = models.IntegerField(default=0)
    defense = models.IntegerField(default=0)
    hp = models.IntegerField(default=0)
    crit_chance = models.FloatField(default=0.0)
    dodge_chance = models.FloatField(default=0.0)
    speed = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_rarity_display()} - {self.get_slot_display()})"


class TowerProgress(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="tower_progress"
    )
    current_floor = models.PositiveIntegerField(default=0)
    max_floor_reached = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    # límite de monedas diarias en torre
    daily_coins = models.PositiveIntegerField(default=0)
    daily_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - piso actual {self.current_floor}, max {self.max_floor_reached}"


class TowerBattleResult(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="tower_battles"
    )
    floor = models.PositiveIntegerField()
    victory = models.BooleanField(default=False)
    log_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        estado = "Victoria" if self.victory else "Derrota"
        return f"{self.user.username} - Piso {self.floor} ({estado})"


class GachaProbability(models.Model):
    rarity = models.CharField(
        max_length=20,
        choices=ItemRarity.choices,
        unique=True,
    )
    probability = models.FloatField(
        help_text="Probabilidad entre 0 y 1. La suma de todas las rarezas debe ser 1.0"
    )

    class Meta:
        ordering = ["rarity"]

    def __str__(self):
        return f"{self.get_rarity_display()}: {self.probability:.6f}"
