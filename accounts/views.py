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
    from tournament.models import GroupPrediction, KnockoutPrediction, GroupResult

    group_preds = list(GroupPrediction.objects.filter(
        user=request.user).select_related('group', 'predicted_first', 'predicted_second'))

    # Attach actual top-2 results to each group prediction
    group_ids = [p.group_id for p in group_preds]
    actual_results_qs = GroupResult.objects.filter(
        group_id__in=group_ids, position__in=[1, 2]
    ).select_related('team')
    actual_by_group = {}
    for r in actual_results_qs:
        actual_by_group.setdefault(r.group_id, {})[r.position] = r.team
    for pred in group_preds:
        grp = actual_by_group.get(pred.group_id, {})
        pred.actual_first = grp.get(1)
        pred.actual_second = grp.get(2)

    knockout_preds = list(KnockoutPrediction.objects.filter(
        user=request.user).select_related(
            'match__round', 'match__winner', 'match__team1', 'match__team2', 'predicted_winner'
        ).order_by('match__round__order', 'match__match_number'))

    group_points_total = sum(p.points_earned or 0 for p in group_preds)
    knockout_points_total = sum(p.points_earned or 0 for p in knockout_preds)

    # Agrupar predicciones eliminatorias por ronda
    knockout_by_round = []
    for pred in knockout_preds:
        round_slug = pred.match.round.slug
        if not knockout_by_round or knockout_by_round[-1]['round'].slug != round_slug:
            knockout_by_round.append({
                'round': pred.match.round,
                'preds': [],
                'total_pts': 0,
            })
        knockout_by_round[-1]['preds'].append(pred)
        knockout_by_round[-1]['total_pts'] += (pred.points_earned or 0)

    context = {
        'group_preds': group_preds,
        'knockout_by_round': knockout_by_round,
        'total_points': request.user.profile.total_points,
        'group_points_total': group_points_total,
        'knockout_points_total': knockout_points_total,
    }
    return render(request, 'accounts/profile.html', context)
