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
    first_place = GroupResult.objects.filter(group=group, position=1).first()

    points = 0
    if prediction.predicted_first.id in advancing_teams:
        points += points_for_team_advancing(prediction.predicted_first)
    if prediction.predicted_second.id in advancing_teams:
        points += points_for_team_advancing(prediction.predicted_second)
    if first_place and prediction.predicted_first.id == first_place.team_id:
        points += 3

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

    total = match.round.base_points + int(upset_bonus)
    prediction.points_earned = total
    prediction.is_correct = True
    prediction.save(update_fields=['points_earned', 'is_correct'])
    return total


# ── Cálculo de créditos ───────────────────────────────────────────────────────

def calculate_group_bet_credits(prediction):
    """
    Resuelve la apuesta de créditos de una predicción de grupo.
    Se llama después de calculate_group_prediction_points (cuando is_scored=True).
    """
    if prediction.bet_credits <= 0:
        return 0

    group = prediction.group
    advancing_ids = set(
        GroupResult.objects.filter(group=group, is_advancing=True).values_list('team_id', flat=True)
    )
    if not advancing_ids:
        return 0

    first_place = GroupResult.objects.filter(group=group, position=1).first()
    first_correct = prediction.predicted_first.id in advancing_ids
    second_correct = prediction.predicted_second.id in advancing_ids

    bet = prediction.bet_credits
    credits_won = 0

    if first_correct:
        m = get_group_team_multiplier(prediction.predicted_first)
        if first_place and prediction.predicted_first.id == first_place.team_id:
            m += 0.30  # bonus por acertar posición exacta
        credits_won += int(bet * m)
    else:
        credits_won -= bet // 2

    if second_correct:
        m = get_group_team_multiplier(prediction.predicted_second)
        credits_won += int(bet * m)
    else:
        credits_won -= bet - (bet // 2)

    prediction.credits_won = credits_won
    prediction.save(update_fields=['credits_won'])
    return credits_won


def calculate_knockout_bet_credits(prediction):
    """
    Resuelve la apuesta de créditos de una predicción knockout.
    Se llama después de calculate_knockout_prediction_points (cuando is_correct != None).
    """
    if prediction.bet_credits <= 0:
        return 0

    match = prediction.match
    if not match.winner:
        return 0

    is_correct = prediction.predicted_winner_id == match.winner_id
    if not is_correct:
        prediction.credits_won = -prediction.bet_credits
        prediction.save(update_fields=['credits_won'])
        return -prediction.bet_credits

    loser = match.team2 if match.team1_id == match.winner_id else match.team1
    loser_rank = loser.fifa_ranking if loser else None
    mult = get_knockout_net_multiplier(match.round.slug, match.winner.fifa_ranking, loser_rank)
    credits_won = int(prediction.bet_credits * mult)
    prediction.credits_won = credits_won
    prediction.save(update_fields=['credits_won'])
    return credits_won


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
    from django.db.models import Sum
    group_delta = GroupPrediction.objects.filter(
        user=user, is_scored=True, bet_credits__gt=0
    ).aggregate(total=Sum('credits_won'))['total'] or 0
    knockout_delta = KnockoutPrediction.objects.filter(
        user=user, is_correct__isnull=False, bet_credits__gt=0
    ).aggregate(total=Sum('credits_won'))['total'] or 0
    user.profile.credits = 1000 + group_delta + knockout_delta
    user.profile.save(update_fields=['credits'])

