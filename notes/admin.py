from django.contrib import admin
from .models import (
    UserProfile,
    Note,
    NoteLike,
    NoteReply,
    Notification,
    InvitationCode,
    MineGameResult,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "coins")
    search_fields = ("user__username",)


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "recipient", "text", "created_at")
    search_fields = ("author__username", "recipient__username", "text")
    list_filter = ("created_at",)


@admin.register(NoteLike)
class NoteLikeAdmin(admin.ModelAdmin):
    list_display = ("id", "note", "user", "created_at")
    search_fields = ("note__text", "user__username")


@admin.register(NoteReply)
class NoteReplyAdmin(admin.ModelAdmin):
    list_display = ("id", "note", "author", "created_at")
    search_fields = ("note__text", "author__username", "text")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "message", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("user__username", "message")


@admin.register(InvitationCode)
class InvitationCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "created_by", "created_at", "used_by", "used_at")
    search_fields = ("code", "created_by__username", "used_by__username")
    list_filter = ("created_at", "used_at")


@admin.register(MineGameResult)
class MineGameResultAdmin(admin.ModelAdmin):
    list_display = ("user", "score", "result", "finished_at")
    list_filter = ("result", "finished_at")
    search_fields = ("user__username",)
