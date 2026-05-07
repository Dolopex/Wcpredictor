from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Sum

from .models import Group, Round, Match, GroupPrediction, KnockoutPrediction, GroupResult, Team
from .utils import get_group_team_multiplier, get_knockout_net_multiplier


def home_view(request):
    groups = Group.objects.prefetch_related('teams').all()
    active_round = Round.objects.filter(is_active=True).order_by('order').first()
    top_users = (
        User.objects.filter(profile__total_points__gt=0)
        .select_related('profile')
        .order_by('-profile__total_points')[:5]
    )

    user_group_preds = set()
    if request.user.is_authenticated:
        preds = GroupPrediction.objects.filter(user=request.user).values_list('group_id', flat=True)
        user_group_preds = set(preds)

    context = {
        'groups': groups,
        'active_round': active_round,
        'top_users': top_users,
        'user_group_preds': user_group_preds,
    }
    return render(request, 'tournament/home.html', context)


def groups_view(request):
    groups = Group.objects.prefetch_related('teams', 'results__team').all()
    context = {'groups': groups}
    return render(request, 'tournament/groups.html', context)


@login_required
def group_predict_view(request, group_name):
    group = get_object_or_404(Group, name=group_name.upper())
    groups_round = Round.objects.filter(slug='groups').first()

    if groups_round and groups_round.is_locked:
        messages.warning(request, 'Las predicciones de la Fase de Grupos ya están cerradas.')
        return redirect('tournament:groups')

    existing = GroupPrediction.objects.filter(user=request.user, group=group).first()
    teams = group.teams.order_by('fifa_ranking')
    user_credits = request.user.profile.credits

    # Calcular multiplicadores por equipo para mostrar en el formulario
    teams_data = [
        {'team': t, 'net_mult': get_group_team_multiplier(t)}
        for t in teams
    ]

    if request.method == 'POST':
        first_id = request.POST.get('first_place')
        second_id = request.POST.get('second_place')
        bet_credits = max(0, int(request.POST.get('bet_credits', 0) or 0))

        if not first_id or not second_id:
            messages.error(request, 'Debes seleccionar 1° y 2° lugar.')
            return render(request, 'tournament/group_predict.html', {
                'group': group, 'teams_data': teams_data,
                'existing': existing, 'user_credits': user_credits})

        if first_id == second_id:
            messages.error(request, 'No puedes elegir el mismo equipo para 1° y 2° lugar.')
            return render(request, 'tournament/group_predict.html', {
                'group': group, 'teams_data': teams_data,
                'existing': existing, 'user_credits': user_credits})

        if bet_credits > user_credits:
            messages.error(request, f'No tienes suficientes créditos. Tienes {user_credits}.')
            return render(request, 'tournament/group_predict.html', {
                'group': group, 'teams_data': teams_data,
                'existing': existing, 'user_credits': user_credits})

        try:
            first_team = group.teams.get(id=first_id)
            second_team = group.teams.get(id=second_id)
        except Team.DoesNotExist:
            messages.error(request, 'Equipo no válido.')
            return render(request, 'tournament/group_predict.html', {
                'group': group, 'teams_data': teams_data,
                'existing': existing, 'user_credits': user_credits})

        if existing:
            existing.predicted_first = first_team
            existing.predicted_second = second_team
            existing.bet_credits = bet_credits
            existing.points_earned = 0
            existing.credits_won = 0
            existing.is_scored = False
            existing.save()
            messages.success(request, f'Predicción del Grupo {group.name} actualizada.')
        else:
            GroupPrediction.objects.create(
                user=request.user,
                group=group,
                predicted_first=first_team,
                predicted_second=second_team,
                bet_credits=bet_credits,
            )
            messages.success(request, f'Predicción del Grupo {group.name} guardada.')

        return redirect('tournament:groups')

    return render(request, 'tournament/group_predict.html', {
        'group': group,
        'teams_data': teams_data,
        'existing': existing,
        'user_credits': user_credits,
    })


def bracket_view(request):
    rounds = Round.objects.exclude(slug='groups').order_by('order')
    rounds_data = []
    user_preds = set()

    if request.user.is_authenticated:
        preds = KnockoutPrediction.objects.filter(user=request.user).values_list('match_id', flat=True)
        user_preds = set(preds)

    for round_obj in rounds:
        matches = round_obj.matches.select_related('team1', 'team2', 'winner').order_by('match_number')
        rounds_data.append({'round': round_obj, 'matches': matches})

    context = {'rounds_data': rounds_data, 'user_preds': user_preds}
    return render(request, 'tournament/bracket.html', context)


@login_required
def round_predict_view(request, round_slug):
    round_obj = get_object_or_404(Round, slug=round_slug)

    if round_obj.is_locked:
        messages.warning(request, f'Las predicciones de {round_obj.name} ya están cerradas.')
        return redirect('tournament:bracket')

    matches = round_obj.matches.select_related('team1', 'team2', 'winner').order_by('match_number')
    available_matches = [m for m in matches if m.team1 and m.team2]

    existing_preds = {
        p.match_id: p for p in KnockoutPrediction.objects.filter(
            user=request.user, match__in=available_matches)
    }

    user_credits = request.user.profile.credits

    # Preparar datos por partido con multiplicadores
    matches_data = []
    for match in available_matches:
        m1 = get_knockout_net_multiplier(
            round_obj.slug, match.team1.fifa_ranking, match.team2.fifa_ranking)
        m2 = get_knockout_net_multiplier(
            round_obj.slug, match.team2.fifa_ranking, match.team1.fifa_ranking)
        matches_data.append({
            'match': match,
            'mult1': m1,
            'mult2': m2,
            'existing': existing_preds.get(match.id),
        })

    if request.method == 'POST':
        saved = 0
        for md in matches_data:
            match = md['match']
            winner_id = request.POST.get(f'winner_{match.id}')
            bet = max(0, int(request.POST.get(f'bet_{match.id}', 0) or 0))

            if not winner_id:
                continue
            if str(match.team1.id) != winner_id and str(match.team2.id) != winner_id:
                continue

            try:
                winner_team = Team.objects.get(id=winner_id)
            except Team.DoesNotExist:
                continue

            if bet > user_credits:
                bet = 0  # no apostar si no hay créditos

            pred = existing_preds.get(match.id)
            if pred:
                pred.predicted_winner = winner_team
                pred.bet_credits = bet
                pred.points_earned = 0
                pred.credits_won = 0
                pred.is_correct = None
                pred.save()
            else:
                KnockoutPrediction.objects.create(
                    user=request.user, match=match,
                    predicted_winner=winner_team, bet_credits=bet)
            saved += 1

        messages.success(request, f'{saved} predicción(es) guardada(s) para {round_obj.name}.')
        return redirect('tournament:bracket')

    context = {
        'round': round_obj,
        'matches_data': matches_data,
        'user_credits': user_credits,
    }
    return render(request, 'tournament/round_predict.html', context)


def leaderboard_view(request):
    from django.core.paginator import Paginator

    users = (
        User.objects.filter(is_active=True)
        .select_related('profile')
        .order_by('-profile__total_points')
    )

    paginator = Paginator(users, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    user_rank = None
    if request.user.is_authenticated:
        better_count = User.objects.filter(
            profile__total_points__gt=request.user.profile.total_points
        ).count()
        user_rank = better_count + 1

    return render(request, 'tournament/leaderboard.html', {
        'page_obj': page_obj,
        'user_rank': user_rank,
    })


@login_required
def credits_view(request):
    profile = request.user.profile

    # Apuestas activas (sin resultado aún)
    active_group_bets = GroupPrediction.objects.filter(
        user=request.user, bet_credits__gt=0, is_scored=False
    ).select_related('group', 'predicted_first', 'predicted_second')

    active_knockout_bets = KnockoutPrediction.objects.filter(
        user=request.user, bet_credits__gt=0, is_correct__isnull=True
    ).select_related('match__round', 'predicted_winner', 'match__team1', 'match__team2')

    # Historial de apuestas resueltas
    history_group = GroupPrediction.objects.filter(
        user=request.user, is_scored=True, bet_credits__gt=0
    ).select_related('group', 'predicted_first', 'predicted_second').order_by('-id')

    history_knockout = KnockoutPrediction.objects.filter(
        user=request.user, is_correct__isnull=False, bet_credits__gt=0
    ).select_related('match__round', 'predicted_winner').order_by('-id')

    # Créditos totales apostados en apuestas activas
    active_group_sum = active_group_bets.aggregate(t=Sum('bet_credits'))['t'] or 0
    active_knockout_sum = active_knockout_bets.aggregate(t=Sum('bet_credits'))['t'] or 0
    total_in_play = active_group_sum + active_knockout_sum

    context = {
        'profile': profile,
        'active_group_bets': active_group_bets,
        'active_knockout_bets': active_knockout_bets,
        'history_group': history_group,
        'history_knockout': history_knockout,
        'total_in_play': total_in_play,
    }
    return render(request, 'tournament/credits.html', context)



def home_view(request):
    groups = Group.objects.prefetch_related('teams').all()
    active_round = Round.objects.filter(is_active=True).order_by('order').first()
    top_users = (
        User.objects.filter(profile__total_points__gt=0)
        .select_related('profile')
        .order_by('-profile__total_points')[:5]
    )

    user_group_preds = {}
    if request.user.is_authenticated:
        preds = GroupPrediction.objects.filter(user=request.user).values_list('group_id', flat=True)
        user_group_preds = set(preds)

    context = {
        'groups': groups,
        'active_round': active_round,
        'top_users': top_users,
        'user_group_preds': user_group_preds,
    }
    return render(request, 'tournament/home.html', context)


def groups_view(request):
    groups = Group.objects.prefetch_related('teams', 'results__team').all()
    context = {'groups': groups}
    return render(request, 'tournament/groups.html', context)


@login_required
def group_predict_view(request, group_name):
    group = get_object_or_404(Group, name=group_name.upper())
    groups_round = Round.objects.filter(slug='groups').first()

    if groups_round and groups_round.is_locked:
        messages.warning(request, 'Las predicciones de la Fase de Grupos ya están cerradas.')
        return redirect('tournament:groups')

    existing = GroupPrediction.objects.filter(user=request.user, group=group).first()
    teams = group.teams.order_by('fifa_ranking')

    if request.method == 'POST':
        first_id = request.POST.get('first_place')
        second_id = request.POST.get('second_place')

        if not first_id or not second_id:
            messages.error(request, 'Debes seleccionar 1° y 2° lugar.')
            return render(request, 'tournament/group_predict.html', {
                'group': group, 'teams': teams, 'existing': existing})

        if first_id == second_id:
            messages.error(request, 'No puedes elegir el mismo equipo para 1° y 2° lugar.')
            return render(request, 'tournament/group_predict.html', {
                'group': group, 'teams': teams, 'existing': existing})

        try:
            first_team = group.teams.get(id=first_id)
            second_team = group.teams.get(id=second_id)
        except Team.DoesNotExist:
            messages.error(request, 'Equipo no válido.')
            return render(request, 'tournament/group_predict.html', {
                'group': group, 'teams': teams, 'existing': existing})

        if existing:
            existing.predicted_first = first_team
            existing.predicted_second = second_team
            existing.points_earned = 0
            existing.is_scored = False
            existing.save()
            messages.success(request, f'Predicción del Grupo {group.name} actualizada.')
        else:
            GroupPrediction.objects.create(
                user=request.user,
                group=group,
                predicted_first=first_team,
                predicted_second=second_team,
            )
            messages.success(request, f'Predicción del Grupo {group.name} guardada.')

        return redirect('tournament:groups')

    return render(request, 'tournament/group_predict.html', {
        'group': group,
        'teams': teams,
        'existing': existing,
    })


def bracket_view(request):
    rounds = Round.objects.exclude(slug='groups').order_by('order')
    rounds_data = []
    user_preds = {}

    if request.user.is_authenticated:
        preds = KnockoutPrediction.objects.filter(user=request.user).values_list('match_id', flat=True)
        user_preds = set(preds)

    for round_obj in rounds:
        matches = round_obj.matches.select_related('team1', 'team2', 'winner').order_by('match_number')
        rounds_data.append({
            'round': round_obj,
            'matches': matches,
        })

    context = {
        'rounds_data': rounds_data,
        'user_preds': user_preds,
    }
    return render(request, 'tournament/bracket.html', context)


@login_required
def round_predict_view(request, round_slug):
    round_obj = get_object_or_404(Round, slug=round_slug)

    if round_obj.is_locked:
        messages.warning(request, f'Las predicciones de {round_obj.name} ya están cerradas.')
        return redirect('tournament:bracket')

    matches = round_obj.matches.select_related('team1', 'team2', 'winner').order_by('match_number')

    # Solo partidos con ambos equipos definidos
    available_matches = [m for m in matches if m.team1 and m.team2]

    existing_preds = {
        p.match_id: p for p in KnockoutPrediction.objects.filter(
            user=request.user, match__in=available_matches)
    }

    if request.method == 'POST':
        saved = 0
        for match in available_matches:
            winner_id = request.POST.get(f'winner_{match.id}')
            if not winner_id:
                continue

            # Validar que el equipo elegido pertenece al partido
            if str(match.team1.id) != winner_id and str(match.team2.id) != winner_id:
                continue

            try:
                winner_team = Team.objects.get(id=winner_id)
            except Team.DoesNotExist:
                continue

            pred = existing_preds.get(match.id)
            if pred:
                pred.predicted_winner = winner_team
                pred.points_earned = 0
                pred.is_correct = None
                pred.save()
            else:
                KnockoutPrediction.objects.create(
                    user=request.user,
                    match=match,
                    predicted_winner=winner_team,
                )
            saved += 1

        messages.success(request, f'{saved} predicción(es) guardada(s) para {round_obj.name}.')
        return redirect('tournament:bracket')

    context = {
        'round': round_obj,
        'available_matches': available_matches,
        'existing_preds': existing_preds,
    }
    return render(request, 'tournament/round_predict.html', context)


def leaderboard_view(request):
    from django.core.paginator import Paginator

    users = (
        User.objects.filter(is_active=True)
        .select_related('profile')
        .order_by('-profile__total_points')
    )

    paginator = Paginator(users, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    user_rank = None
    if request.user.is_authenticated:
        # Calcular posición del usuario actual
        better_count = User.objects.filter(
            profile__total_points__gt=request.user.profile.total_points
        ).count()
        user_rank = better_count + 1

    context = {
        'page_obj': page_obj,
        'user_rank': user_rank,
    }
    return render(request, 'tournament/leaderboard.html', context)
