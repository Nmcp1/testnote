from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q, Count
from django.urls import reverse
from django.http import HttpResponseForbidden
from django.contrib import messages

from django.contrib.auth.models import Group, User

from .models import Note, NoteLike, Notification, InvitationCode
from .forms import (
    NoteForm,
    PrivateNoteForm,
    RegistrationForm,
    NoteReplyForm,
)

MODERATOR_GROUP_NAME = "moderador"


def ensure_moderator_group_exists():
    """Crea el grupo 'moderador' si no existe."""
    Group.objects.get_or_create(name=MODERATOR_GROUP_NAME)


def user_is_moderator(user):
    """Devuelve True si el usuario es moderador (o superusuario)."""
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    ensure_moderator_group_exists()
    return user.groups.filter(name__iexact=MODERATOR_GROUP_NAME).exists()


def home(request):
    # Filtro de orden: por fecha o por likes
    orden = request.GET.get("orden", "fecha")

    # SOLO notas públicas (recipient NULL)
    notes_qs = (
        Note.objects.filter(recipient__isnull=True)
        .select_related("author")
        .annotate(
            likes_count=Count("likes", distinct=True),
            replies_count=Count("replies", distinct=True),
        )
    )

    if orden == "likes":
        notes_qs = notes_qs.order_by("-likes_count", "-created_at")
    else:  # 'fecha'
        notes_qs = notes_qs.order_by("-created_at")

    paginator = Paginator(notes_qs, 9)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    form = None
    liked_ids = set()

    if request.user.is_authenticated:
        liked_ids = set(
            NoteLike.objects.filter(
                user=request.user,
                note__in=page_obj.object_list,
            ).values_list("note_id", flat=True)
        )

        if request.method == "POST":
            form = NoteForm(request.POST)
            if form.is_valid():
                note = form.save(commit=False)
                note.author = request.user
                note.recipient = None  # pública
                note.save()
                return redirect(f"{request.path}?orden={orden}")
        else:
            form = NoteForm()

    context = {
        "form": form,
        "page_obj": page_obj,
        "liked_ids": liked_ids,
        "orden": orden,
    }
    return render(request, "notes/home.html", context)


def note_detail(request, note_id):
    # Detalle solo para notas públicas
    note_qs = (
        Note.objects.filter(pk=note_id, recipient__isnull=True)
        .select_related("author")
        .annotate(
            likes_count=Count("likes", distinct=True),
            replies_count=Count("replies", distinct=True),
        )
    )
    note = get_object_or_404(note_qs)

    replies = note.replies.select_related("author").order_by("created_at")

    user_liked = False
    if request.user.is_authenticated:
        user_liked = NoteLike.objects.filter(note=note, user=request.user).exists()

    if request.method == "POST":
        if not request.user.is_authenticated:
            login_url = f"{reverse('login')}?next={request.path}"
            return redirect(login_url)

        form = NoteReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.note = note
            reply.author = request.user
            reply.save()

            # Notificar al autor de la nota (si no es la misma persona)
            if note.author != request.user:
                Notification.objects.create(
                    user=note.author,
                    message=f"{request.user.username} comentó tu nota pública.",
                    url=reverse("note_detail", args=[note.id]),
                )

            return redirect(request.path)
    else:
        form = NoteReplyForm() if request.user.is_authenticated else None

    context = {
        "note": note,
        "replies": replies,
        "user_liked": user_liked,
        "form": form,
    }
    return render(request, "notes/note_detail.html", context)


@login_required
def private_notes(request):
    filtro = request.GET.get("filtro", "recibidas")

    if filtro == "recibidas":
        notes_qs = Note.objects.filter(recipient=request.user)
    elif filtro == "enviadas":
        notes_qs = Note.objects.filter(
            author=request.user,
            recipient__isnull=False,
        )
    else:  # "todas"
        notes_qs = Note.objects.filter(
            Q(recipient=request.user)
            | Q(author=request.user, recipient__isnull=False)
        )

    notes_qs = notes_qs.select_related("author", "recipient")

    paginator = Paginator(notes_qs, 9)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    if request.method == "POST":
        form = PrivateNoteForm(request.POST, user=request.user)
        if form.is_valid():
            note = form.save(commit=False)
            note.author = request.user
            note.save()

            # Notificación para el destinatario
            if note.recipient and note.recipient != request.user:
                Notification.objects.create(
                    user=note.recipient,
                    message=f"{request.user.username} te envió una nota privada.",
                    url=reverse("private_notes"),
                )

            return redirect("private_notes")
    else:
        form = PrivateNoteForm(user=request.user)

    context = {
        "form": form,
        "page_obj": page_obj,
        "filtro": filtro,
    }
    return render(request, "notes/private_notes.html", context)


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()

            invitation = getattr(form, "invitation_instance", None)
            if invitation is not None:
                invitation.used_by = user
                invitation.used_at = timezone.now()
                invitation.save()

            auth_login(request, user)
            return redirect("home")
    else:
        form = RegistrationForm()

    return render(request, "registration/register.html", {"form": form})


@require_POST
@login_required
def toggle_like(request, note_id):
    # Solo se pueden likear notas públicas
    note = get_object_or_404(Note, pk=note_id, recipient__isnull=True)

    like, created = NoteLike.objects.get_or_create(
        note=note,
        user=request.user,
    )

    if created:
        # Like nuevo -> notificar al autor (si no soy yo)
        if note.author != request.user:
            Notification.objects.create(
                user=note.author,
                message=f"{request.user.username} dio like a tu nota pública.",
                url=reverse("note_detail", args=[note.id]),
            )
    else:
        # Ya tenía like -> quitar
        like.delete()

    next_url = request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)


@login_required
def notifications(request):
    notifications_qs = request.user.notifications.all()
    notifications_qs.filter(is_read=False).update(is_read=True)

    context = {
        "notifications": notifications_qs,
    }
    return render(request, "notes/notifications.html", context)


@login_required
def invitation_admin(request):
    """Vista de administración de códigos de invitación (solo moderadores)."""
    if not user_is_moderator(request.user):
        return HttpResponseForbidden("No tienes permiso para ver esta página.")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            InvitationCode.objects.create(created_by=request.user)
            messages.success(request, "Se creó un nuevo código de invitación.")
            return redirect("invitation_admin")

        elif action == "delete":
            code_id = request.POST.get("code_id")
            try:
                code = InvitationCode.objects.get(
                    id=code_id,
                    used_by__isnull=True,
                )
                code.delete()
                messages.success(request, "Código eliminado correctamente.")
            except InvitationCode.DoesNotExist:
                messages.error(
                    request,
                    "No se pudo eliminar el código (puede que ya haya sido usado).",
                )
            return redirect("invitation_admin")

    unused_codes = InvitationCode.objects.filter(
        used_by__isnull=True
    ).select_related("created_by").order_by("-created_at")

    used_codes = InvitationCode.objects.filter(
        used_by__isnull=False
    ).select_related("created_by", "used_by").order_by("-used_at", "-created_at")

    context = {
        "unused_codes": unused_codes,
        "used_codes": used_codes,
    }
    return render(request, "notes/invitation_admin.html", context)


@login_required
def moderator_panel(request):
    """Panel para asignar y quitar el rol de moderador (solo superusuario)."""
    # ✅ Solo superusuario puede entrar aquí
    if not request.user.is_superuser:
        return HttpResponseForbidden("Solo el superusuario puede gestionar moderadores.")

    ensure_moderator_group_exists()
    mod_group = Group.objects.get(name=MODERATOR_GROUP_NAME)

    if request.method == "POST":
        action = request.POST.get("action")
        user_id = request.POST.get("user_id")

        try:
            target_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, "El usuario no existe.")
            return redirect("moderator_panel")

        if action == "add":
            if mod_group in target_user.groups.all():
                messages.info(request, f"{target_user.username} ya es moderador.")
            else:
                target_user.groups.add(mod_group)
                messages.success(request, f"{target_user.username} ahora es moderador.")

        elif action == "remove":
            # Opcional: impedir que te quites el rol a ti mismo
            if target_user == request.user:
                messages.error(request, "No puedes quitarte el rol de moderador a ti mismo.")
            elif mod_group not in target_user.groups.all():
                messages.info(request, f"{target_user.username} no es moderador.")
            else:
                target_user.groups.remove(mod_group)
                messages.success(request, f"{target_user.username} ya no es moderador.")

        return redirect("moderator_panel")

    moderators = User.objects.filter(
        groups__name__iexact=MODERATOR_GROUP_NAME
    ).order_by("username")

    non_moderators = User.objects.exclude(
        groups__name__iexact=MODERATOR_GROUP_NAME
    ).order_by("username")

    context = {
        "moderators": moderators,
        "non_moderators": non_moderators,
    }
    return render(request, "notes/moderator_panel.html", context)
