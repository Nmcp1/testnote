# notes/admin.py
from django.contrib import admin
from .models import (
    Note,
    NoteLike,
    NoteReply,
    Notification,
    InvitationCode,
    UserProfile,
    MineGameResult,
    CombatItem,
    TowerProgress,
    TowerBattleResult,
    GachaProbability,
    PvpRanking,
    PvpBattleLog,
    Trade,
    WorldBossCycle,
    WorldBossParticipant,
    MiniBossLobby,
    MiniBossParticipant,
    MarketListing,
)

# --- Notas -------------------------------------------------------

@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "recipient", "text", "created_at")
    list_filter = ("created_at", "author", "recipient")
    search_fields = ("text", "author__username", "recipient__username")


@admin.register(NoteLike)
class NoteLikeAdmin(admin.ModelAdmin):
    list_display = ("id", "note", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("note__text", "user__username")


@admin.register(NoteReply)
class NoteReplyAdmin(admin.ModelAdmin):
    list_display = ("id", "note", "author", "text", "created_at")
    list_filter = ("created_at", "author")
    search_fields = ("text", "author__username", "note__text")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "message", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("message", "user__username")


@admin.register(InvitationCode)
class InvitationCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "created_by", "created_at", "used_by", "used_at")
    list_filter = ("created_at", "used_at")
    search_fields = ("code", "created_by__username", "used_by__username")


# --- Perfil / Economía ------------------------------------------

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "coins", "rubies", "created_at", "updated_at")
    search_fields = ("user__username",)
    list_filter = ("created_at", "updated_at")


@admin.register(MineGameResult)
class MineGameResultAdmin(admin.ModelAdmin):
    list_display = ("user", "score", "result", "finished_at")
    list_filter = ("result", "finished_at")
    search_fields = ("user__username",)


# --- RPG: Ítems / Torre / Gacha --------------------------------

@admin.register(CombatItem)
class CombatItemAdmin(admin.ModelAdmin):
    list_display = (
        "id", "owner", "name", "slot", "rarity", "source",
        "attack", "defense", "hp", "crit_chance", "dodge_chance", "speed",
        "created_at",
    )
    list_filter = ("slot", "rarity", "source", "created_at")
    search_fields = ("name", "owner__username")


@admin.register(TowerProgress)
class TowerProgressAdmin(admin.ModelAdmin):
    list_display = (
        "user", "current_floor", "max_floor_reached",
        "daily_coins", "daily_date", "updated_at",
    )
    search_fields = ("user__username",)
    list_filter = ("daily_date",)


@admin.register(TowerBattleResult)
class TowerBattleResultAdmin(admin.ModelAdmin):
    list_display = ("user", "floor", "victory", "created_at")
    list_filter = ("victory", "created_at")
    search_fields = ("user__username",)


@admin.register(GachaProbability)
class GachaProbabilityAdmin(admin.ModelAdmin):
    list_display = ("rarity", "probability")
    list_filter = ("rarity",)
    search_fields = ("rarity",)


# --- PvP --------------------------------------------------------

@admin.register(PvpRanking)
class PvpRankingAdmin(admin.ModelAdmin):
    list_display = ("position", "user", "last_reward_date", "created_at")
    list_filter = ("last_reward_date", "created_at")
    search_fields = ("user__username",)
    ordering = ("position",)


@admin.register(PvpBattleLog)
class PvpBattleLogAdmin(admin.ModelAdmin):
    list_display = ("id", "attacker", "defender", "attacker_won", "created_at")
    list_filter = ("attacker_won", "created_at")
    search_fields = ("attacker__username", "defender__username")


# --- Trades -----------------------------------------------------

@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("id", "from_user", "to_user", "status", "from_coins", "to_coins", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("from_user__username", "to_user__username")


# --- World Boss -------------------------------------------------

@admin.register(WorldBossCycle)
class WorldBossCycleAdmin(admin.ModelAdmin):
    list_display = (
        "id", "start_time", "total_damage", "turns_processed",
        "finished", "rewards_given",
    )
    list_filter = ("finished", "rewards_given", "start_time")
    search_fields = ("start_time",)


@admin.register(WorldBossParticipant)
class WorldBossParticipantAdmin(admin.ModelAdmin):
    list_display = ("id", "cycle", "user", "current_hp", "total_damage_done", "joined_at")
    list_filter = ("cycle",)
    search_fields = ("user__username",)


# --- MiniBoss ---------------------------------------------------

@admin.register(MiniBossLobby)
class MiniBossLobbyAdmin(admin.ModelAdmin):
    list_display = ("id", "boss_code", "creator", "status", "created_at", "started_at", "ended_at")
    list_filter = ("status", "boss_code", "created_at")
    search_fields = ("creator__username", "boss_code")


@admin.register(MiniBossParticipant)
class MiniBossParticipantAdmin(admin.ModelAdmin):
    list_display = (
        "id", "lobby", "user", "hp_remaining", "is_alive",
        "total_damage_done", "boss_damage_at_death",
        "reward_coins", "reward_given",
    )
    list_filter = ("lobby", "is_alive", "reward_given")
    search_fields = ("user__username",)


# --- Mercado ----------------------------------------------------

@admin.register(MarketListing)
class MarketListingAdmin(admin.ModelAdmin):
    list_display = ("id", "item", "seller", "buyer", "price_coins", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("item__name", "seller__username", "buyer__username")
