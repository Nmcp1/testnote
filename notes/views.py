from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q, Count

from .models import Note, NoteLike
from .forms import NoteForm, PrivateNoteForm, RegistrationForm


def home(request):
    # Filtro de orden: por fecha o por likes
    orden = request.GET.get('orden', 'fecha')

    # SOLO notas públicas (recipient NULL)
    notes_qs = Note.objects.filter(recipient__isnull=True).select_related('author')

    # Anotar cantidad de likes
    notes_qs = notes_qs.annotate(likes_count=Count('likes'))

    if orden == 'likes':
        notes_qs = notes_qs.order_by('-likes_count', '-created_at')
    else:  # 'fecha'
        notes_qs = notes_qs.order_by('-created_at')

    paginator = Paginator(notes_qs, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    form = None
    liked_ids = set()

    if request.user.is_authenticated:
        # Saber qué notas de la página actual tiene like del usuario
        liked_ids = set(
            NoteLike.objects.filter(
                user=request.user,
                note__in=page_obj.object_list
            ).values_list('note_id', flat=True)
        )

        if request.method == 'POST':
            form = NoteForm(request.POST)
            if form.is_valid():
                note = form.save(commit=False)
                note.author = request.user
                note.recipient = None  # pública
                note.save()
                # Mantener el orden actual al recargar
                return redirect(f'{request.path}?orden={orden}')
        else:
            form = NoteForm()

    context = {
        'form': form,
        'page_obj': page_obj,
        'liked_ids': liked_ids,
        'orden': orden,
    }
    return render(request, 'notes/home.html', context)


@login_required
def private_notes(request):
    filtro = request.GET.get("filtro", "recibidas")

    if filtro == "recibidas":
        notes_qs = Note.objects.filter(recipient=request.user)
    elif filtro == "enviadas":
        notes_qs = Note.objects.filter(author=request.user, recipient__isnull=False)
    else:  # "todas"
        notes_qs = Note.objects.filter(
            Q(recipient=request.user) |
            Q(author=request.user, recipient__isnull=False)
        )

    notes_qs = notes_qs.select_related('author', 'recipient')

    paginator = Paginator(notes_qs, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    if request.method == 'POST':
        form = PrivateNoteForm(request.POST, user=request.user)
        if form.is_valid():
            note = form.save(commit=False)
            note.author = request.user
            note.save()
            return redirect('private_notes')
    else:
        form = PrivateNoteForm(user=request.user)

    context = {
        'form': form,
        'page_obj': page_obj,
        'filtro': filtro,
    }
    return render(request, 'notes/private_notes.html', context)


def register(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()

            invitation = getattr(form, 'invitation_instance', None)
            if invitation is not None:
                invitation.used_by = user
                invitation.used_at = timezone.now()
                invitation.save()

            auth_login(request, user)
            return redirect('home')
    else:
        form = RegistrationForm()

    return render(request, 'registration/register.html', {'form': form})


@require_POST
@login_required
def toggle_like(request, note_id):
    # Solo se pueden likear notas públicas
    note = get_object_or_404(Note, pk=note_id, recipient__isnull=True)

    like, created = NoteLike.objects.get_or_create(
        note=note,
        user=request.user
    )

    if not created:
        # Ya tenía like -> quitar
        like.delete()

    # Volver a la página de donde vino
    next_url = request.META.get('HTTP_REFERER') or '/'
    return redirect(next_url)
