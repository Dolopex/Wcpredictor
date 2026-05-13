"""
Panel de administración personalizado para CopaBet 26.
Solo accesible para staff/superusuarios.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count, Q

from .models import (
    Team, Group, Round, Match, GroupResult,
    GroupPrediction, KnockoutPrediction,
    CreditPackage, CreditPurchase, SandboxLog,
)
from .sandbox import generate_test_data, reset_test_data, sandbox_stats
from .signals import score_group_predictions, score_knockout_predictions
from accounts.models import UserProfile


def staff_required(view_func):
    return user_passes_test(lambda u: u.is_active and u.is_staff)(view_func)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def panel_home(request):
    total_users   = User.objects.filter(is_active=True).count()
    total_credits = UserProfile.objects.aggregate(t=Sum('credits'))['t'] or 0
    total_points  = UserProfile.objects.aggregate(t=Sum('total_points'))['t'] or 0
    total_purchases = CreditPurchase.objects.filter(status='completed').aggregate(
        cop=Sum('cop_paid'), crd=Sum('credits_applied'))
    total_group_preds   = GroupPrediction.objects.count()
    total_knockout_preds = KnockoutPrediction.objects.count()

    rounds = Round.objects.all().order_by('order')
    groups = Group.objects.all().order_by('name')

    # Top 5 usuarios
    top_users = User.objects.filter(is_active=True).select_related('profile')\
        .order_by('-profile__total_points')[:5]

    context = {
        'total_users': total_users,
        'total_credits': total_credits,
        'total_points': total_points,
        'total_cop': total_purchases['cop'] or 0,
        'total_crd_sold': total_purchases['crd'] or 0,
        'total_group_preds': total_group_preds,
        'total_knockout_preds': total_knockout_preds,
        'rounds': rounds,
        'groups': groups,
        'top_users': top_users,
    }
    return render(request, 'admin_panel/home.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Usuarios
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def panel_users(request):
    q = request.GET.get('q', '').strip()
    users = User.objects.filter(is_active=True).select_related('profile').order_by(
        '-profile__total_points')
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(email__icontains=q) |
            Q(profile__full_name__icontains=q)
        )
    return render(request, 'admin_panel/users.html', {'users': users, 'q': q})


@staff_required
def panel_user_detail(request, user_id):
    user = get_object_or_404(User, id=user_id)
    profile = user.profile
    group_preds = GroupPrediction.objects.filter(user=user).select_related(
        'group', 'predicted_first', 'predicted_second', 'predicted_third')
    knockout_preds = KnockoutPrediction.objects.filter(user=user).select_related(
        'match__round', 'predicted_winner', 'match__team1', 'match__team2')
    purchases = CreditPurchase.objects.filter(user=user).select_related('package').order_by('-created_at')[:10]

    if request.method == 'POST':
        action = request.POST.get('action')
        with transaction.atomic():
            prof = UserProfile.objects.select_for_update().get(user=user)
            if action == 'set_credits':
                try:
                    new_val = int(request.POST.get('credits', prof.credits))
                except (ValueError, TypeError):
                    messages.error(request, 'Valor de créditos inválido.')
                    return redirect('tournament:panel_user_detail', user_id=user_id)
                prof.credits = max(0, new_val)
                prof.save(update_fields=['credits'])
                messages.success(request, f'Créditos de {user.username} ajustados a {prof.credits:,}.')
            elif action == 'add_credits':
                try:
                    amount = int(request.POST.get('amount', 0))
                except (ValueError, TypeError):
                    messages.error(request, 'Cantidad de créditos inválida.')
                    return redirect('tournament:panel_user_detail', user_id=user_id)
                prof.credits += amount
                prof.save(update_fields=['credits'])
                messages.success(request, f'+{amount:,} créditos agregados a {user.username}.')
            elif action == 'set_staff':
                user.is_staff = request.POST.get('is_staff') == '1'
                user.save(update_fields=['is_staff'])
                messages.success(request, 'Permisos actualizados.')
        return redirect('tournament:panel_user_detail', user_id=user_id)

    return render(request, 'admin_panel/user_detail.html', {
        'target_user': user, 'profile': profile,
        'group_preds': group_preds, 'knockout_preds': knockout_preds,
        'purchases': purchases,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Rondas
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def panel_rounds(request):
    rounds = Round.objects.all().order_by('order')

    if request.method == 'POST':
        round_id = request.POST.get('round_id')
        action   = request.POST.get('action')
        round_obj = get_object_or_404(Round, id=round_id)

        if action == 'toggle_active':
            round_obj.is_active = not round_obj.is_active
            round_obj.save(update_fields=['is_active'])
            estado = 'activada' if round_obj.is_active else 'desactivada'
            messages.success(request, f'{round_obj.name} {estado}.')
        elif action == 'toggle_lock':
            round_obj.is_locked = not round_obj.is_locked
            round_obj.save(update_fields=['is_locked'])
            estado = 'bloqueada' if round_obj.is_locked else 'desbloqueada'
            messages.success(request, f'{round_obj.name} {estado}.')

        return redirect('tournament:panel_rounds')

    return render(request, 'admin_panel/rounds.html', {'rounds': rounds})


# ─────────────────────────────────────────────────────────────────────────────
# Partidos — crear / editar
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def panel_matches(request):
    rounds = Round.objects.exclude(slug='groups').order_by('order')
    round_slug = request.GET.get('round', rounds.first().slug if rounds.exists() else '')
    current_round = get_object_or_404(Round, slug=round_slug) if round_slug else None
    matches = current_round.matches.select_related('team1', 'team2', 'winner').order_by('match_number') if current_round else []
    teams = Team.objects.all().order_by('fifa_ranking')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_match':
            rnd = get_object_or_404(Round, id=request.POST.get('round_id'))
            try:
                match_number = int(request.POST.get('match_number', 1))
            except (ValueError, TypeError):
                match_number = 1
            Match.objects.create(
                round=rnd,
                match_number=match_number,
                team1_id=request.POST.get('team1_id') or None,
                team2_id=request.POST.get('team2_id') or None,
                description=request.POST.get('description', ''),
            )
            messages.success(request, 'Partido creado.')

        elif action == 'set_winner':
            match = get_object_or_404(Match, id=request.POST.get('match_id'))
            winner_id = request.POST.get('winner_id')
            match.winner_id = winner_id if winner_id else None
            match.save(update_fields=['winner_id'])
            if match.winner:
                score_knockout_predictions(match)
                messages.success(request, f'Ganador registrado y predicciones puntuadas para Partido {match.match_number}.')
            else:
                messages.success(request, 'Ganador eliminado.')

        elif action == 'delete_match':
            match = get_object_or_404(Match, id=request.POST.get('match_id'))
            match.delete()
            messages.success(request, 'Partido eliminado.')

        return redirect(f"{request.path}?round={request.POST.get('round_slug', round_slug)}")

    return render(request, 'admin_panel/matches.html', {
        'rounds': rounds,
        'current_round': current_round,
        'matches': matches,
        'teams': teams,
        'round_slug': round_slug,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Grupos — resultados y puntaje
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def panel_groups(request):
    groups = Group.objects.prefetch_related('teams', 'results__team').order_by('name')

    if request.method == 'POST':
        action = request.POST.get('action')
        group  = get_object_or_404(Group, id=request.POST.get('group_id'))

        if action == 'set_results':
            teams = list(group.teams.all())
            with transaction.atomic():
                GroupResult.objects.filter(group=group).delete()
                for pos in range(1, 5):
                    team_id = request.POST.get(f'pos_{pos}')
                    advances = pos in (1, 2)  # 1° y 2° siempre avanzan
                    # 3° avanza si se marca el checkbox
                    if pos == 3:
                        advances = request.POST.get('third_advances') == '1'
                    if team_id:
                        GroupResult.objects.create(
                            group=group,
                            team_id=team_id,
                            position=pos,
                            is_advancing=advances,
                        )
                # Puntuar predicciones
                score_group_predictions(group)
            messages.success(request, f'Resultados del Grupo {group.name} guardados y predicciones puntuadas.')

        elif action == 'clear_results':
            GroupResult.objects.filter(group=group).delete()
            GroupPrediction.objects.filter(group=group).update(
                points_earned=0, credits_won=0, is_scored=False)
            messages.success(request, f'Resultados del Grupo {group.name} eliminados.')

        return redirect('tournament:panel_groups')

    groups_data = []
    for group in groups:
        # Use string keys so Django template filter get_item:pos works with "1","2","3","4"
        results = {str(r.position): r for r in group.results.all()}
        # Add third_advances flag for template checkbox pre-fill
        r3 = results.get('3')
        results['third_advances'] = r3.is_advancing if r3 else False
        pred_count = GroupPrediction.objects.filter(group=group).count()
        groups_data.append({'group': group, 'results': results, 'pred_count': pred_count})

    return render(request, 'admin_panel/groups.html', {
        'groups_data': groups_data,
        'teams': Team.objects.all().order_by('fifa_ranking'),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Simulador
# ─────────────────────────────────────────────────────────────────────────────

@staff_required
def panel_simulate(request):
    """Simula resultados aleatorios para probar la puntuación."""
    import random

    groups  = Group.objects.prefetch_related('teams').order_by('name')
    rounds  = Round.objects.exclude(slug='groups').order_by('order')
    matches = Match.objects.filter(team1__isnull=False, team2__isnull=False, winner__isnull=True)\
        .select_related('round', 'team1', 'team2').order_by('round__order', 'match_number')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'sim_group':
            group = get_object_or_404(Group, id=request.POST.get('group_id'))
            teams = list(group.teams.all())
            if len(teams) < 4:
                messages.error(request, 'El grupo necesita 4 equipos.')
                return redirect('tournament:panel_simulate')
            random.shuffle(teams)
            with transaction.atomic():
                GroupResult.objects.filter(group=group).delete()
                for pos, team in enumerate(teams[:4], 1):
                    advances = pos in (1, 2) or (pos == 3 and random.random() > 0.4)
                    GroupResult.objects.create(group=group, team=team, position=pos, is_advancing=advances)
                score_group_predictions(group)
            messages.success(request, f'Grupo {group.name} simulado: {" > ".join(t.name for t in teams[:4])}')

        elif action == 'sim_all_groups':
            with transaction.atomic():
                for group in groups:
                    teams = list(group.teams.all())
                    if len(teams) < 4:
                        continue
                    random.shuffle(teams)
                    GroupResult.objects.filter(group=group).delete()
                    for pos, team in enumerate(teams[:4], 1):
                        advances = pos in (1, 2) or (pos == 3 and random.random() > 0.4)
                        GroupResult.objects.create(group=group, team=team, position=pos, is_advancing=advances)
                    score_group_predictions(group)
            messages.success(request, 'Todos los grupos simulados y puntuados.')

        elif action == 'sim_match':
            match = get_object_or_404(Match, id=request.POST.get('match_id'))
            winner = random.choice([match.team1, match.team2])
            match.winner = winner
            match.save(update_fields=['winner_id'])
            score_knockout_predictions(match)
            messages.success(request, f'Partido {match.match_number} simulado: gana {winner.name}.')

        elif action == 'sim_all_matches':
            pending = Match.objects.filter(
                team1__isnull=False, team2__isnull=False, winner__isnull=True)
            count = 0
            for match in pending:
                winner = random.choice([match.team1, match.team2])
                match.winner = winner
                match.save(update_fields=['winner_id'])
                score_knockout_predictions(match)
                count += 1
            messages.success(request, f'{count} partidos simulados.')

        elif action == 'reset_all_scores':
            # Resetear todos los puntajes (para empezar pruebas desde cero)
            with transaction.atomic():
                GroupPrediction.objects.all().update(points_earned=0, credits_won=0, is_scored=False)
                KnockoutPrediction.objects.all().update(points_earned=0, credits_won=0, is_correct=None)
                GroupResult.objects.all().delete()
                Match.objects.all().update(winner=None)
                UserProfile.objects.all().update(total_points=0)
            messages.success(request, 'Todos los resultados y puntajes reseteados.')

        elif action == 'sandbox_generate':
            try:
                n = max(1, min(50, int(request.POST.get('n_users', 10))))
            except (ValueError, TypeError):
                n = 10
            try:
                result = generate_test_data(n)
                SandboxLog.objects.create(
                    action='generate',
                    n_users=n,
                    notes=f"Bots: {result['n_users']} | Grupos: {result['n_group_preds']} | Eliminatorias: {result['n_knockout_preds']}",
                )
                messages.success(request, f"Sandbox: {n} bots generados con {result['n_group_preds']} pred. de grupos y {result['n_knockout_preds']} pred. de eliminatorias.")
            except Exception as exc:
                messages.error(request, f'Error al generar sandbox: {exc}')

        elif action == 'sandbox_reset':
            try:
                result = reset_test_data()
                SandboxLog.objects.create(
                    action='reset',
                    notes=f"Bots: {result['deleted_users']} | Matches: {result['deleted_matches']} | Resultados: {result['deleted_results']}",
                )
                messages.success(request, f"Sandbox reseteado: {result['deleted_users']} bots, {result['deleted_matches']} matches y {result['deleted_results']} resultados eliminados.")
            except Exception as exc:
                messages.error(request, f'Error al resetear sandbox: {exc}')

        elif action == 'recalc_underdogs':
            from .utils import assign_underdog_multipliers
            result = assign_underdog_multipliers()
            messages.success(request, f"Underdogs recalculados: {result['underdogs']} usuarios con bonus (promedio: {result['avg_points']} pts).")

        return redirect('tournament:panel_simulate')

    return render(request, 'admin_panel/simulate.html', {
        'groups': groups,
        'matches': matches,
        'sandbox': sandbox_stats(),
    })
