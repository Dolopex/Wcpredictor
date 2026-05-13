"""
Señales del torneo: cuando se ingresan resultados reales en el admin,
se dispara automáticamente el cálculo de puntos y créditos.
"""

from .models import GroupPrediction, KnockoutPrediction
from .utils import (
    calculate_group_prediction_points,
    calculate_group_bet_credits,
    calculate_knockout_prediction_points,
    calculate_knockout_bet_credits,
    update_user_total_points,
    update_user_credits,
    assign_underdog_multipliers,
)
# Nota: update_user_credits ya no modifica el saldo (los créditos se gestionan en views).


def score_group_predictions(group):
    predictions = GroupPrediction.objects.filter(group=group).select_related(
        'user', 'predicted_first', 'predicted_second')

    affected_users = set()
    for prediction in predictions:
        calculate_group_prediction_points(prediction)
        calculate_group_bet_credits(prediction)
        affected_users.add(prediction.user)

    for user in affected_users:
        update_user_total_points(user)
        update_user_credits(user)

    assign_underdog_multipliers()


def score_knockout_predictions(match):
    predictions = KnockoutPrediction.objects.filter(match=match).select_related(
        'user', 'predicted_winner')

    affected_users = set()
    for prediction in predictions:
        calculate_knockout_prediction_points(prediction)
        calculate_knockout_bet_credits(prediction)
        affected_users.add(prediction.user)

    for user in affected_users:
        update_user_total_points(user)
        update_user_credits(user)

    assign_underdog_multipliers()

