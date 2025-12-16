from __future__ import annotations

from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ExpeditionLobbyStatus(models.TextChoices):
    WAITING = "waiting", "En espera"
    RUNNING = "running", "En progreso"
    FINISHED = "finished", "Finalizada"


class ExpeditionPhase(models.TextChoices):
    WAITING = "waiting", "Esperando jugadores"
    VOTE_ORDER_1 = "vote_order_1", "Votación: quién va primero"
    VOTE_ORDER_2 = "vote_order_2", "Votación: quién va segundo"
    DECISION = "decision", "Decisión (opcional)"
    COMBAT = "combat", "Combate"
    BETWEEN = "between", "Entre pisos"
    ENDED = "ended", "Terminada"


class DecisionType(models.TextChoices):
    HEAL_50 = "heal_50", "Curar 50% HP a un jugador"
    DAMAGE_30 = "damage_30", "Quitar 30% HP a un jugador"
    GIVE_STATS = "give_stats", "Dar stats aleatorias"
    REMOVE_STATS = "remove_stats", "Quitar stats aleatorias"


class ExpeditionLobby(models.Model):
    code = models.CharField(max_length=12, unique=True)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="expeditions_created")

    status = models.CharField(max_length=20, choices=ExpeditionLobbyStatus.choices, default=ExpeditionLobbyStatus.WAITING)
    phase = models.CharField(max_length=30, choices=ExpeditionPhase.choices, default=ExpeditionPhase.WAITING)

    floor = models.PositiveIntegerField(default=1)
    phase_deadline = models.DateTimeField(null=True, blank=True)

    # Orden elegido por votación
    order_1 = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    order_2 = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    # Enemigo actual
    enemy_hp = models.IntegerField(null=True, blank=True)
    enemy_attack = models.IntegerField(null=True, blank=True)
    enemy_defense = models.IntegerField(null=True, blank=True)

    # Último enemigo muerto y killer (para buffs)
    last_killer = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_enemy_snapshot = models.JSONField(null=True, blank=True)

    # Decisión opcional del piso
    decision_type = models.CharField(max_length=32, choices=DecisionType.choices, null=True, blank=True)
    decision_payload = models.JSONField(null=True, blank=True)  # ej: {"stat":"attack","amount":34}

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def is_active(self):
        return self.status in {ExpeditionLobbyStatus.WAITING, ExpeditionLobbyStatus.RUNNING}

    def __str__(self):
        return f"Expedition {self.code} ({self.status})"

    def set_phase(self, phase: str, seconds: int | None = None):
        self.phase = phase
        if seconds:
            self.phase_deadline = timezone.now() + timedelta(seconds=seconds)
        else:
            self.phase_deadline = None
        self.save(update_fields=["phase", "phase_deadline"])


class ExpeditionParticipant(models.Model):
    lobby = models.ForeignKey(ExpeditionLobby, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="expedition_participations")

    # “Base” del modo expedición (lo dejamos fijo)
    base_hp = models.IntegerField(default=100)
    base_attack = models.IntegerField(default=15)
    base_defense = models.IntegerField(default=2)

    # Stats actuales
    max_hp = models.IntegerField(default=100)
    current_hp = models.IntegerField(default=100)
    attack = models.IntegerField(default=15)
    defense = models.IntegerField(default=2)

    is_alive = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("lobby", "user")

    def __str__(self):
        return f"{self.user.username} en {self.lobby.code}"


class ExpeditionChatMessage(models.Model):
    lobby = models.ForeignKey(ExpeditionLobby, on_delete=models.CASCADE, related_name="chat_messages")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ExpeditionVote(models.Model):
    """
    Guardamos votos por fase:
    - VOTE_ORDER_1, VOTE_ORDER_2: target_user_id = quien eligen
    - DECISION: target_user_id = quien recibe/soporta el efecto
    """
    lobby = models.ForeignKey(ExpeditionLobby, on_delete=models.CASCADE, related_name="votes")
    phase = models.CharField(max_length=32)
    voter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    target = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    extra = models.JSONField(null=True, blank=True)  # por si después quieres opciones más complejas
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("lobby", "phase", "voter")


class ExpeditionDailyEarning(models.Model):
    """
    Cap diario: 500 oro por jugador por expediciones.
    day = fecha local.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="expedition_daily_earnings")
    day = models.DateField()
    earned_coins = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("user", "day")

class ExpeditionRunResult(models.Model):
    """
    Un resultado por lobby terminado, asociado al día local (Chile).
    Sirve para armar el Top Diario de equipos.
    """
    lobby = models.ForeignKey(ExpeditionLobby, on_delete=models.CASCADE, related_name="run_results")
    day = models.DateField()  # localdate Chile
    floor_reached = models.PositiveIntegerField(default=1)

    # Lista de IDs de usuarios del equipo (máx 3)
    member_ids = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["day", "-floor_reached", "created_at"]),
        ]


class ExpeditionDailyPayout(models.Model):
    """
    Para asegurar que la recompensa diaria se pague 1 vez por usuario por día.
    """
    day = models.DateField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="expedition_daily_payouts")
    coins = models.PositiveIntegerField(default=0)
    rank = models.PositiveIntegerField()  # 1,2,3
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("day", "user")
