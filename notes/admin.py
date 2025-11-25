# notes/admin.py
from django.contrib import admin
from .models import Note, InvitationCode


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('author', 'text', 'created_at')
    search_fields = ('author__username', 'text')


@admin.register(InvitationCode)
class InvitationCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'created_by', 'created_at', 'used_by', 'used_at')
    search_fields = ('code', 'created_by__username', 'used_by__username')
    list_filter = ('created_at', 'used_at')
    readonly_fields = ('code', 'created_by', 'created_at', 'used_by', 'used_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
