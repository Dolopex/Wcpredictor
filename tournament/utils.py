"""
Lógica de puntos y créditos para el predictor del Mundial 2026.

── PUNTOS ────────────────────────────────────────────────────────────────────
  Grupos: 10 + round(ranking * 0.3) por equipo que acierta avanzando.
          +3 bonus si aciertas el 1° exacto.
  Knockout: base_ronda + max(0, winner_rank - loser_rank) * 0.5  (upset bonus)

── CRÉDITOS ──────────────────────────────────────────────────────────────────
  El usuario apuesta X créditos en su predicción.
  Si gana → credits_won = int(bet * net_multiplier)  (ganancia neta)
  Si pierde → credits_won = -bet                     (pérdida)
  Saldo = 1000 + suma(credits_won de todas las apuestas resueltas)

  Multiplicadores netos:
    Grupos: 0.10 + (ranking - 1) * 0.022   (Spain 0.10x → NZ 1.95x)
    Knockout base: r32=0.40 | r16=0.60 | qf=0.90 | sf=1.30 | final=2.00
    Bonus upset (ganador con ranking > perdedor): +(winner_rank - loser_rank) * 0.008
"""

from .models import GroupPrediction, KnockoutPrediction, GroupResult


# ── Puntos helpers ────────────────────────────────────────────────────────────

def points_for_team_advancing(team):
    return 10 + round(team.fifa_ranking * 0.3)


# ── Créditos helpers ──────────────────────────────────────────────────────────

KNOCKOUT_BASE_MULT = {'r32': 0.40, 'r16': 0.60, 'qf': 0.90, 'sf': 1.30, 'final': 2.00}


def get_group_team_multiplier(team):
    """
    Multiplicador neto de créditos si este equipo avanza de grupos.
    España (1) → 0.10x   |   Nueva Zelanda (85) → 1.95x
    """
    return round(max(0.10, 0.10 + (team.fifa_ranking - 1) * 0.022), 2)


def get_knockout_net_multiplier(round_slug, winner_rank, loser_rank=None):
    """
    Multiplicador neto de créditos para ganar una apuesta knockout.
    """
    base = KNOCKOUT_BASE_MULT.get(round_slug, 0.40)
    if loser_rank is not None and winner_rank > loser_rank:
        base += (winner_rank - loser_rank) * 0.008
    return round(base, 2)


# ── Cálculo de puntos ─────────────────────────────────────────────────────────

def calculate_group_prediction_points(prediction):
    group = prediction.group
    results = GroupResult.objects.filter(group=group, is_advancing=True).select_related('team')
    advancing_teams = {r.team_id for r in results}
    first_place  = GroupResult.objects.filter(group=group, position=1).first()
    second_place = GroupResult.objects.filter(group=group, position=2).first()

    points = 0
    # Puntos por cada equipo que acierta avanzando
    if prediction.predicted_first.id in advancing_teams:
        points += points_for_team_advancing(prediction.predicted_first)
    if prediction.predicted_second.id in advancing_teams:
        points += points_for_team_advancing(prediction.predicted_second)

    # +3 bonus por acertar posición exacta del 1°
    if first_place and prediction.predicted_first.id == first_place.team_id:
        points += 3
    # +3 bonus por acertar posición exacta del 2°
    if second_place and prediction.predicted_second.id == second_place.team_id:
        points += 3

    # +5 bonus por acertar mejor tercero (si predijo que avanza y efectivamente avanzó como 3°)
    if prediction.predicted_third and prediction.predicted_third_advances:
        third_advancing = GroupResult.objects.filter(
            group=group, team=prediction.predicted_third, position=3, is_advancing=True
        ).exists()
        if third_advancing:
            points += 5

    prediction.points_earned = points
    prediction.is_scored = True
    prediction.save(update_fields=['points_earned', 'is_scored'])
    return points


def calculate_knockout_prediction_points(prediction):
    match = prediction.match
    if not match.winner:
        return 0

    is_correct = prediction.predicted_winner_id == match.winner_id
    if not is_correct:
        prediction.points_earned = 0
        prediction.is_correct = False
        prediction.save(update_fields=['points_earned', 'is_correct'])
        return 0

    winner = match.winner
    loser = match.team2 if match.team1_id == winner.id else match.team1
    upset_bonus = 0
    if loser:
        upset_bonus = max(0, (winner.fifa_ranking - loser.fifa_ranking) * 0.5)

    base_points = match.round.base_points + int(upset_bonus)

    # Aplicar multiplicador underdog SOLO si el usuario activó el boost en este partido
    mult = 1.0
    if prediction.boost_applied:
        profile = getattr(prediction.user, 'profile', None)
        if profile:
            mult = profile.underdog_multiplier
    total = int(base_points * mult)

    prediction.points_earned = total
    prediction.is_correct = True
    prediction.save(update_fields=['points_earned', 'is_correct', 'boost_applied'])
    return total


# ── Cálculo de créditos ───────────────────────────────────────────────────────

def calculate_group_bet_credits(prediction):
    """
    Las predicciones de grupo NO dan créditos al acertar.
    El costo (bet_credits) ya fue descontado al hacer la predicción.
    credits_won siempre queda en 0.
    """
    prediction.credits_won = 0
    prediction.save(update_fields=['credits_won'])
    return 0


def calculate_knockout_bet_credits(prediction):
    """
    Las predicciones knockout NO dan créditos al acertar.
    El costo (bet_credits) ya fue descontado al hacer la predicción.
    credits_won siempre queda en 0.
    """
    prediction.credits_won = 0
    prediction.save(update_fields=['credits_won'])
    return 0


# ── Actualizar totales del usuario ────────────────────────────────────────────

def update_user_total_points(user):
    from django.db.models import Sum
    group_pts = GroupPrediction.objects.filter(user=user, is_scored=True).aggregate(
        total=Sum('points_earned'))['total'] or 0
    knockout_pts = KnockoutPrediction.objects.filter(
        user=user, is_correct=True).aggregate(total=Sum('points_earned'))['total'] or 0
    user.profile.total_points = group_pts + knockout_pts
    user.profile.save(update_fields=['total_points'])


def update_user_credits(user):
    # Los créditos se descuentan al predecir (en la view, atómicamente).
    # Las predicciones acertadas no devuelven créditos.
    # Esta función no hace nada; se mantiene por compatibilidad con signals.py.
    pass


# ── Sistema underdog ──────────────────────────────────────────────────────────

def assign_underdog_multipliers():
    """
    Calcula el promedio de total_points de todos los usuarios activos y asigna
    un multiplicador escalonado a quienes estén por debajo del promedio.

    Tiers basados en el % del promedio que alcanza el usuario:
      ≥ 100% del promedio  →  ×1.0  (sin bonus)
      75%–99%              →  ×1.5
      50%–74%              →  ×2.0
      25%–49%              →  ×2.5
       0%–24%              →  ×3.0

    Devuelve un dict con estadísticas de la operación.
    """
    from django.contrib.auth.models import User
    from django.db.models import Avg

    profiles = list(
        User.objects.filter(is_active=True)
        .select_related('profile')
        .only('id', 'profile__total_points', 'profile__underdog_multiplier')
    )

    if not profiles:
        return {'updated': 0, 'avg_points': 0, 'underdogs': 0}

    avg_points = sum(u.profile.total_points for u in profiles) / len(profiles)

    def _tier(pts):
        if avg_points <= 0 or pts >= avg_points:
            return 1.0, 0
        ratio = pts / avg_points
        if ratio >= 0.75:
            return 1.5, 1
        elif ratio >= 0.50:
            return 1.5, 2
        elif ratio >= 0.25:
            return 2.5, 2
        else:
            return 2.5, 3

    updated = 0
    underdogs = 0
    for user in profiles:
        mult, uses = _tier(user.profile.total_points)
        user.profile.underdog_multiplier = mult
        user.profile.underdog_boost_uses = uses
        user.profile.save(update_fields=['underdog_multiplier', 'underdog_boost_uses'])
        updated += 1
        if mult > 1.0:
            underdogs += 1
        else:
            # Salió de la zona underdog: revocar boosts en partidos pendientes de puntuación
            from .models import KnockoutPrediction
            KnockoutPrediction.objects.filter(
                user=user,
                boost_applied=True,
                is_correct__isnull=True,  # aún no puntuado
            ).update(boost_applied=False)

    return {
        'updated': updated,
        'avg_points': round(avg_points, 1),
        'underdogs': underdogs,
    }

