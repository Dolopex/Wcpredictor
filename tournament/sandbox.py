"""
Módulo Sandbox: genera y resetea datos de prueba para el torneo.

Los usuarios bot se identifican con el prefijo 'bot_'.
Los matches de sandbox se identifican con '[SANDBOX]' en su descripción.
"""
import random

from django.contrib.auth.models import User
from django.db import transaction

from .models import Group, GroupPrediction, GroupResult, Round, Match, KnockoutPrediction, Team
from .utils import (
    calculate_group_prediction_points,
    calculate_knockout_prediction_points,
    update_user_total_points,
)

BOT_PREFIX = 'bot_'
SANDBOX_TAG = '[SANDBOX]'

# Rondas eliminatorias y cantidad de partidos en cada una
KNOCKOUT_ROUNDS = [
    ('r32', 16),
    ('r16', 8),
    ('qf', 4),
    ('sf', 2),
    ('final', 1),
]


# ── Consultas de estado ───────────────────────────────────────────────────────

def get_bot_users():
    return User.objects.filter(username__startswith=BOT_PREFIX)


def sandbox_stats():
    """Retorna estadísticas actuales de los datos de prueba."""
    bot_qs = get_bot_users()
    return {
        'n_users': bot_qs.count(),
        'n_group_preds': GroupPrediction.objects.filter(
            user__username__startswith=BOT_PREFIX
        ).count(),
        'n_group_results': GroupResult.objects.count(),
        'n_knockout_preds': KnockoutPrediction.objects.filter(
            user__username__startswith=BOT_PREFIX
        ).count(),
        'n_sandbox_matches': Match.objects.filter(
            description__startswith=SANDBOX_TAG
        ).count(),
    }


# ── Generación ────────────────────────────────────────────────────────────────

def generate_test_data(n_users=10):
    """
    Genera n_users usuarios bot con predicciones aleatorias en todas las fases
    del torneo (grupos + r32 → final) y resultados aleatorios.
    Retorna las estadísticas resultantes.
    """
    # Transacciones separadas para evitar que SQLite quede bloqueado
    # por una sola transacción larga que acumule muchas escrituras.
    with transaction.atomic():
        users = _create_bot_users(n_users)

    with transaction.atomic():
        _ensure_group_results()

    with transaction.atomic():
        _create_group_predictions(users)

    with transaction.atomic():
        _create_knockout_data(users)

    with transaction.atomic():
        for user in users:
            update_user_total_points(user)

    return sandbox_stats()


def _create_bot_users(n):
    """Crea n usuarios bot con créditos de prueba."""
    existing_usernames = set(get_bot_users().values_list('username', flat=True))
    users = []
    counter = 1
    while len(users) < n:
        username = f'{BOT_PREFIX}{counter}'
        if username not in existing_usernames:
            user = User.objects.create_user(
                username=username,
                password='sandbox_test_pw',
                email=f'{username}@sandbox.test',
            )
            profile = user.profile
            profile.credits = 50_000
            profile.full_name = f'Bot Tester {counter}'
            profile.save(update_fields=['credits', 'full_name'])
            users.append(user)
        counter += 1
    return users


def _ensure_group_results():
    """
    Crea GroupResult aleatorios para todos los grupos que aún no los tienen.
    Puestos 1 y 2 avanzan siempre; 8 de los 12 terceros también avanzan.
    Luego puntúa las predicciones existentes (usuarios reales o bot anteriores).
    """
    from .signals import score_group_predictions

    groups = list(Group.objects.prefetch_related('teams').all())

    # Decidir cuáles grupos tendrán su 3° como "mejor tercero" (8 de 12)
    group_letters = [g.name for g in groups]
    random.shuffle(group_letters)
    best_thirds = set(group_letters[:8])

    for group in groups:
        if GroupResult.objects.filter(group=group).exists():
            continue  # Ya tiene resultado → no sobreescribir
        teams = list(group.teams.all())
        random.shuffle(teams)
        for pos, team in enumerate(teams, start=1):
            is_advancing = pos <= 2 or (pos == 3 and group.name in best_thirds)
            GroupResult.objects.create(
                group=group,
                team=team,
                position=pos,
                is_advancing=is_advancing,
            )
        score_group_predictions(group)


def _create_group_predictions(users):
    """Crea predicciones de grupos aleatorias para cada usuario bot."""
    groups = list(Group.objects.prefetch_related('teams').all())
    results_by_group = {}
    for gr in GroupResult.objects.select_related('team', 'group').all():
        results_by_group.setdefault(gr.group_id, []).append(gr)

    for user in users:
        for group in groups:
            if GroupPrediction.objects.filter(user=user, group=group).exists():
                continue
            teams = list(group.teams.all())
            random.shuffle(teams)
            pred = GroupPrediction.objects.create(
                user=user,
                group=group,
                predicted_first=teams[0],
                predicted_second=teams[1],
                predicted_third=teams[2],
                predicted_third_advances=random.choice([True, False]),
                bet_credits=1000,
            )
            # Puntuar inmediatamente si ya hay resultados
            if group.id in {gr.group_id for gr in results_by_group.get(group.id, [])}:
                calculate_group_prediction_points(pred)


def _create_knockout_data(users):
    """
    Por cada ronda eliminatoria: asegura que existan matches sandbox,
    crea predicciones aleatorias para los usuarios nuevos y asigna ganadores.
    """
    all_teams = list(Team.objects.all())

    for round_slug, n_matches in KNOCKOUT_ROUNDS:
        try:
            rnd = Round.objects.get(slug=round_slug)
        except Round.DoesNotExist:
            continue

        # Obtener o crear matches sandbox de esta ronda
        existing = list(Match.objects.filter(
            round=rnd,
            description__startswith=SANDBOX_TAG,
        ).select_related('team1', 'team2', 'winner'))

        if len(existing) < n_matches:
            # Crear los que faltan
            already = len(existing)
            pool = random.sample(all_teams, min((n_matches - already) * 2, len(all_teams)))
            for i in range(already, n_matches):
                idx = (i - already) * 2
                t1 = pool[idx] if idx < len(pool) else random.choice(all_teams)
                t2 = pool[idx + 1] if idx + 1 < len(pool) else random.choice(all_teams)
                if t1 == t2:
                    t2 = random.choice([t for t in all_teams if t != t1])
                winner = random.choice([t1, t2])
                match = Match.objects.create(
                    round=rnd,
                    match_number=900 + i + 1,
                    team1=t1,
                    team2=t2,
                    winner=winner,
                    description=f'{SANDBOX_TAG} {round_slug} #{i + 1}',
                )
                existing.append(match)

        # Crear predicciones para usuarios que no las tienen aún
        for match in existing:
            for user in users:
                if KnockoutPrediction.objects.filter(user=user, match=match).exists():
                    continue
                if match.team1 is None or match.team2 is None:
                    continue
                predicted = random.choice([match.team1, match.team2])
                pred = KnockoutPrediction.objects.create(
                    user=user,
                    match=match,
                    predicted_winner=predicted,
                )
                if match.winner:
                    calculate_knockout_prediction_points(pred)


# ── Reset ─────────────────────────────────────────────────────────────────────

def reset_test_data():
    """
    Elimina todos los datos de prueba:
    - Usuarios bot (y sus predicciones en cascada)
    - Matches de sandbox (y sus predicciones en cascada)
    - Resultados de todos los grupos
    Retorna un dict con lo eliminado.
    """
    with transaction.atomic():
        deleted_users, _ = get_bot_users().delete()
        deleted_matches, _ = Match.objects.filter(
            description__startswith=SANDBOX_TAG
        ).delete()
        deleted_results, _ = GroupResult.objects.all().delete()

    return {
        'deleted_users': deleted_users,
        'deleted_matches': deleted_matches,
        'deleted_results': deleted_results,
    }
