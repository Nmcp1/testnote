# notes/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login
from django.core.paginator import Paginator
from django.utils import timezone

from .models import Note
from .forms import NoteForm, RegistrationForm


def home(request):
    notes_qs = Note.objects.select_related('author')
    paginator = Paginator(notes_qs, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    form = None

    if request.user.is_authenticated:
        if request.method == 'POST':
            form = NoteForm(request.POST)
            if form.is_valid():
                note = form.save(commit=False)
                note.author = request.user
                note.save()
                return redirect('home')
        else:
            form = NoteForm()

    context = {
        'form': form,
        'page_obj': page_obj,
    }
    return render(request, 'notes/home.html', context)


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
