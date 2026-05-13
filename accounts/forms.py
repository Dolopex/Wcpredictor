from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
import re


class RegisterForm(UserCreationForm):
    full_name = forms.CharField(
        max_length=120,
        required=True,
        label='Nombre completo',
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Juan García'}),
        help_text='Tu nombre real (solo lo usamos para identificarte internamente).',
    )
    phone_number = forms.CharField(
        max_length=20,
        required=True,
        label='Número de teléfono',
        widget=forms.TextInput(attrs={'placeholder': 'Ej: 300 123 4567', 'type': 'tel'}),
    )
    email = forms.EmailField(
        required=True,
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'placeholder': 'tu@email.com'}),
    )

    class Meta:
        model = User
        fields = ('full_name', 'phone_number', 'username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Username: update label and help_text
        self.fields['username'].label = 'Nombre de usuario (apodo)'
        self.fields['username'].help_text = (
            '⚠️ Por seguridad, usa un apodo o alias — no pongas tu nombre real. '
            'Este nombre será visible en el ranking público.'
        )
        self.fields['username'].widget.attrs['placeholder'] = 'Ej: ElTigreGol, Crack99…'
        self.fields['password1'].label = 'Contraseña'
        self.fields['password1'].help_text = 'Mínimo 8 caracteres.'
        self.fields['password2'].label = 'Confirmar contraseña'
        self.fields['password2'].help_text = ''

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        # Allow digits, spaces, hyphens, parentheses (no country code required)
        if not re.match(r'^[\d\s\-\(\)]{7,15}$', phone):
            raise forms.ValidationError('Ingresa un número de teléfono válido (solo dígitos).')
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Ya existe una cuenta con este correo.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            # Save extra profile fields
            user.profile.full_name = self.cleaned_data['full_name']
            user.profile.phone_number = self.cleaned_data['phone_number']
            user.profile.save(update_fields=['full_name', 'phone_number'])
        return user
