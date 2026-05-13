from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import RegisterForm

# FIFA World Cup 2026 start — 11 Jun 2026 19:00 CDT (UTC-5) = 12 Jun 2026 00:00 UTC
import datetime
_WC_START = datetime.datetime(2026, 6, 12, 0, 0, 0, tzinfo=datetime.timezone.utc)


def register_view(request):
    if request.user.is_authenticated:
        return redirect('tournament:home')

    if timezone.now() >= _WC_START:
        messages.error(request, 'El período de inscripción ha cerrado. El Mundial ya comenzó.')
        return redirect('tournament:home')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'¡Bienvenido {user.username}! Tu cuenta fue creada.')
            return redirect('tournament:home')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('tournament:home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', '')
            # Validar que 'next' sea una URL interna (evitar redirección a sitios externos)
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('tournament:home')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    else:
        form = AuthenticationForm()
        # Aplicar clases Tailwind a los campos del form
        input_class = 'w-full px-4 py-2 rounded-lg bg-gray-800 border border-gray-600 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500'
        for field in form.fields.values():
            field.widget.attrs['class'] = input_class

    return render(request, 'accounts/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('accounts:login')


@login_required
def profile_view(request):
    from tournament.models import GroupPrediction, KnockoutPrediction
    group_preds = GroupPrediction.objects.filter(
        user=request.user).select_related('group', 'predicted_first', 'predicted_second')
    knockout_preds = KnockoutPrediction.objects.filter(
        user=request.user).select_related('match__round', 'predicted_winner')

    context = {
        'group_preds': group_preds,
        'knockout_preds': knockout_preds,
        'total_points': request.user.profile.total_points,
    }
    return render(request, 'accounts/profile.html', context)
