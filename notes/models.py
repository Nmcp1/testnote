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

# --- PVP ARENA -------------------------------------------------------

class PvpRanking(models.Model):
    """
    Ranking PvP por puestos.
    position = 1 es el top1, 2 es top2, etc.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="pvp_ranking",
    )
    position = models.PositiveIntegerField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_reward_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"PvP #{self.position} - {self.user.username}"

    def daily_reward(self) -> int:
        """
        Top1 = 200, top2 = 180, bajando de 20 en 20 hasta 0.
        """
        base = 200
        reward = base - 20 * (self.position - 1)
        return max(reward, 0)


class PvpBattleLog(models.Model):
    """
    Log de combates PvP entre jugadores.
    """
    attacker = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="pvp_battles_as_attacker",
    )
    defender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="pvp_battles_as_defender",
    )
    attacker_won = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)
    log_text = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        result = "ganó" if self.attacker_won else "perdió"
        return f"{self.attacker.username} {result} contra {self.defender.username} (PvP)"

class Trade(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_ACCEPTED, "Aceptado"),
        (STATUS_REJECTED, "Rechazado"),
        (STATUS_CANCELLED, "Cancelado"),
    ]

    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="trades_sent",
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="trades_received",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    # Monedas que pone cada lado
    from_coins = models.PositiveIntegerField(
        default=0,
        help_text="Monedas que entrega el emisor.",
    )
    to_coins = models.PositiveIntegerField(
        default=0,
        help_text="Monedas que entrega el receptor.",
    )

    # Objetos que pone cada lado (máx 10 en total, se valida en la vista)
    offered_from = models.ManyToManyField(
        CombatItem,
        blank=True,
        related_name="trades_offered_from",
    )
    offered_to = models.ManyToManyField(
        CombatItem,
        blank=True,
        related_name="trades_offered_to",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    last_actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trades_last_actor",
    )

    def total_items(self):
        return self.offered_from.count() + self.offered_to.count()

    def is_pending(self):
        return self.status == self.STATUS_PENDING

    def other_user(self, user):
        return self.to_user if user == self.from_user else self.from_user

    def __str__(self):
        return f"Trade #{self.pk} {self.from_user} ↔ {self.to_user} ({self.status})"

class WorldBossCycle(models.Model):
    """
    Un ciclo de World Boss dura 3 horas (anclado a las 00:00 del día):
      - 1h de preparación (join)
      - 1h de batalla (1 turno por minuto, en base al tiempo real transcurrido)
      - 1h de reposo (se ve el log y el daño total)
    """
    start_time = models.DateTimeField(help_text="Inicio local del ciclo (fase de preparación).")
    created_at = models.DateTimeField(auto_now_add=True)

    total_damage = models.PositiveIntegerField(default=0)
    turns_processed = models.PositiveIntegerField(default=0)

    finished = models.BooleanField(default=False)
    rewards_given = models.BooleanField(default=False)

    battle_log = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-start_time"]
        unique_together = ("start_time",)

    def __str__(self):
        local_start = timezone.localtime(self.start_time)
        return f"WorldBoss {local_start.strftime('%Y-%m-%d %H:%M')}"


class WorldBossParticipant(models.Model):
    """
    Participación de un jugador en un ciclo de World Boss.
    Se guarda su HP actual y el daño total que ha hecho.
    """
    cycle = models.ForeignKey(
        WorldBossCycle,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="worldboss_participations",
    )
    current_hp = models.IntegerField()
    total_damage_done = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cycle", "user")
        ordering = ["-total_damage_done", "user__username"]

    def __str__(self):
        return f"{self.user.username} en {self.cycle}"


from django.utils import timezone

class MiniBossLobby(models.Model):
    """
    Lobby de minijefe. Varios jugadores pueden unirse, el creador
    puede iniciar la batalla. La batalla avanza 1 turno cada 30 segundos.
    """

    BOSS_MOTH = "moth_baron"
    BOSS_CAT = "cat_commander"
    BOSS_FREDDY = "nightmare_freddy"

    BOSS_CHOICES = [
        (BOSS_MOTH, "Varón Polilla"),
        (BOSS_CAT, "Comandante Gato"),
        (BOSS_FREDDY, "Pesadilla Freddy"),
    ]

    STATUS_WAITING = "waiting"
    STATUS_RUNNING = "running"
    STATUS_FINISHED = "finished"

    STATUS_CHOICES = [
        (STATUS_WAITING, "En espera"),
        (STATUS_RUNNING, "En batalla"),
        (STATUS_FINISHED, "Finalizada"),
    ]

    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="miniboss_lobbies_created",
    )
    boss_code = models.CharField(max_length=32, choices=BOSS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_WAITING,
    )

    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Turnos y daño total al jefe
    current_turn = models.IntegerField(default=0)
    total_damage = models.IntegerField(default=0)

    # Log de la batalla (texto)
    log_text = models.TextField(blank=True)

    def __str__(self):
        return f"MiniBossLobby #{self.id} - {self.get_boss_code_display()} ({self.get_status_display()})"


class MiniBossParticipant(models.Model):
    """
    Jugador dentro de un lobby de minijefe.
    Se guarda su vida restante, daño total e información de recompensa.
    """

    lobby = models.ForeignKey(
        MiniBossLobby,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="miniboss_participations",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    # Vida que le queda en este combate
    hp_remaining = models.IntegerField(default=0)

    # Daño total que le ha hecho al jefe
    total_damage_done = models.IntegerField(default=0)

    # Estado
    is_alive = models.BooleanField(default=True)

    # Recompensa en monedas (calculada al final)
    reward_coins = models.IntegerField(default=0)
    reward_given = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} en lobby {self.lobby_id} (DMG {self.total_damage_done})"
