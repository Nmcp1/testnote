from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Note, InvitationCode, NoteReply


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Escribe tu nota (máx. 100 caracteres)...'
            })
        }

    def clean_text(self):
        text = self.cleaned_data['text']
        if len(text) > 100:
            raise forms.ValidationError('La nota no puede tener más de 100 caracteres.')
        return text


class PrivateNoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['recipient', 'text']
        widgets = {
            'recipient': forms.Select(attrs={
                'class': 'form-select',
            }),
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Escribe tu nota privada (máx. 100 caracteres)...'
            })
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['recipient'].queryset = User.objects.exclude(pk=user.pk)

    def clean_text(self):
        text = self.cleaned_data['text']
        if len(text) > 100:
            raise forms.ValidationError('La nota no puede tener más de 100 caracteres.')
        return text


class NoteReplyForm(forms.ModelForm):
    class Meta:
        model = NoteReply
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Escribe tu comentario (máx. 200 caracteres)...'
            })
        }

    def clean_text(self):
        text = self.cleaned_data['text']
        if len(text) > 200:
            raise forms.ValidationError('El comentario no puede tener más de 200 caracteres.')
        return text


class RegistrationForm(UserCreationForm):
    invitation_code = forms.CharField(
        label='Código secreto',
        max_length=50,
        help_text='Ingresa el código entregado por un administrador.'
    )

    class Meta:
        model = User
        fields = ("username", "password1", "password2", "invitation_code")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_invitation_code(self):
        code = self.cleaned_data.get('invitation_code', '').strip()
        if not code:
            raise forms.ValidationError("Debes ingresar un código secreto.")

        try:
            invitation = InvitationCode.objects.get(code=code)
        except InvitationCode.DoesNotExist:
            raise forms.ValidationError("El código secreto no es válido.")

        if invitation.used_by is not None:
            raise forms.ValidationError("Este código ya fue usado para otra cuenta.")

        self.invitation_instance = invitation
        return code
