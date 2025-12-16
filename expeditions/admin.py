from django.contrib import admin
from django.utils import timezone

from .models import (
    ExpeditionLobby,
    ExpeditionParticipant,
    ExpeditionChatMessage,
    ExpeditionVote,
    ExpeditionDailyEarning,
)


# =========================
# INLINES
# =========================

class ExpeditionParticipantInline(admin.TabularInline):
    model = ExpeditionParticipant
    extra = 0
    fields = (
        "user",
        "is_alive",
        "base_hp", "base_attack", "base_defense",
        "max_hp", "current_hp", "attack", "defense",
        "joined_at",
    )
    readonly_fields = ("joined_at",)
    autocomplete_fields = ("user",)
    show_change_link = True


class ExpeditionChatInline(admin.TabularInline):
    model = ExpeditionChatMessage
    extra = 0
    fields = ("created_at", "user", "message")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("user",)
    show_change_link = True


class ExpeditionVoteInline(admin.TabularInline):
    model = ExpeditionVote
    extra = 0
    fields = ("created_at", "phase", "voter", "target", "extra")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("voter", "target")
    show_change_link = True


# =========================
# LOBBY ADMIN
# =========================

@admin.action(description="🧹 Resetear lobby (volver a WAITING, limpiar enemigo/orden/decisión)")
def reset_lobby(modeladmin, request, queryset):
    for lobby in queryset:
        lobby.status = "waiting"
        lobby.phase = "waiting"
        lobby.phase_deadline = None

        lobby.floor = 1

        lobby.order_1 = None
        lobby.order_2 = None

        lobby.enemy_hp = None
        lobby.enemy_attack = None
        lobby.enemy_defense = None

        lobby.last_killer = None
        lobby.last_enemy_snapshot = None

        lobby.decision_type = None
        lobby.decision_payload = None

        lobby.started_at = None
        lobby.ended_at = None

        lobby.save()


@admin.action(description="⛔ Forzar terminar lobby (FINISHED + ENDED)")
def force_finish_lobby(modeladmin, request, queryset):
    now = timezone.now()
    for lobby in queryset:
        lobby.status = "finished"
        lobby.phase = "ended"
        lobby.phase_deadline = None
        lobby.ended_at = now
        lobby.save(update_fields=["status", "phase", "phase_deadline", "ended_at"])


@admin.register(ExpeditionLobby)
class ExpeditionLobbyAdmin(admin.ModelAdmin):
    list_display = (
        "id", "code", "creator",
        "status", "phase", "floor",
        "participants_count", "alive_count",
        "created_at", "started_at", "ended_at",
    )
    list_filter = ("status", "phase", "created_at")
    search_fields = ("code", "creator__username", "creator__email")
    autocomplete_fields = ("creator", "order_1", "order_2", "last_killer")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("Identificación", {
            "fields": ("code", "creator")
        }),
        ("Estado", {
            "fields": ("status", "phase", "floor", "phase_deadline")
        }),
        ("Orden por votación", {
            "fields": ("order_1", "order_2")
        }),
        ("Enemigo actual", {
            "fields": ("enemy_hp", "enemy_attack", "enemy_defense")
        }),
        ("Última muerte (buffs)", {
            "fields": ("last_killer", "last_enemy_snapshot")
        }),
        ("Decisión opcional", {
            "fields": ("decision_type", "decision_payload")
        }),
        ("Tiempos", {
            "fields": ("created_at", "started_at", "ended_at")
        }),
    )

    readonly_fields = ("created_at",)

    inlines = (ExpeditionParticipantInline, ExpeditionVoteInline, ExpeditionChatInline)

    actions = (reset_lobby, force_finish_lobby)

    def participants_count(self, obj):
        return obj.participants.count()
    participants_count.short_description = "Players"

    def alive_count(self, obj):
        return obj.participants.filter(is_alive=True).count()
    alive_count.short_description = "Vivos"


# =========================
# PARTICIPANTS ADMIN
# =========================

@admin.register(ExpeditionParticipant)
class ExpeditionParticipantAdmin(admin.ModelAdmin):
    list_display = (
        "id", "lobby", "user", "is_alive",
        "max_hp", "current_hp", "attack", "defense",
        "joined_at",
    )
    list_filter = ("is_alive", "joined_at")
    search_fields = ("lobby__code", "user__username", "user__email")
    autocomplete_fields = ("lobby", "user")
    ordering = ("-joined_at",)
    readonly_fields = ("joined_at",)


# =========================
# CHAT ADMIN
# =========================

@admin.register(ExpeditionChatMessage)
class ExpeditionChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "lobby", "user", "created_at", "short_message")
    list_filter = ("created_at",)
    search_fields = ("lobby__code", "user__username", "message")
    autocomplete_fields = ("lobby", "user")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    def short_message(self, obj):
        msg = obj.message or ""
        return msg[:60] + ("..." if len(msg) > 60 else "")
    short_message.short_description = "Mensaje"


# =========================
# VOTES ADMIN
# =========================

@admin.register(ExpeditionVote)
class ExpeditionVoteAdmin(admin.ModelAdmin):
    list_display = ("id", "lobby", "phase", "voter", "target", "created_at")
    list_filter = ("phase", "created_at")
    search_fields = ("lobby__code", "voter__username", "target__username")
    autocomplete_fields = ("lobby", "voter", "target")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


# =========================
# DAILY EARNINGS ADMIN
# =========================

@admin.register(ExpeditionDailyEarning)
class ExpeditionDailyEarningAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "day", "earned_coins")
    list_filter = ("day",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)
    ordering = ("-day",)
