from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from .forms import RegisterForm


def register_view(request):
    if request.user.is_authenticated:
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
            next_url = request.GET.get('next', 'tournament:home')
            return redirect(next_url)
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')
    else:
        form = AuthenticationForm()
        # Aplicar clases Tailwind a los campos del form
        input_class = 'w-full px-4 py-2 rounded-lg bg-gray-800 border border-gray-600 text-white focus:outline-none focus:ring-2 focus:ring-emerald-500'
        for field in form.fields.values():
            field.widget.attrs['class'] = input_class

    return render(request, 'accounts/login.html', {'form': form})


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
