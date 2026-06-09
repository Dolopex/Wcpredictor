"""
Señales del torneo: cuando se ingresan resultados reales en el admin,
se dispara automáticamente el cálculo de puntos y créditos.
También automáticamente desembolsa créditos cuando una compra es completada.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import GroupPrediction, KnockoutPrediction, CreditPurchase
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


# ─────────────────────────────────────────────────────────────────────────────
# Signal: Desembolso automático de créditos cuando se completa una compra
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=CreditPurchase)
def disburse_credits_on_purchase_completion(sender, instance, created, **kwargs):
    """
    Cuando una compra de créditos se marca como 'completed', automáticamente
    desembolsa los créditos al usuario sin necesidad de verificación manual.
    
    Idempotente: solo desembolsa si credits_disbursed no está marcado.
    Defensivo: funciona aunque el campo credits_disbursed no exista en la BD aún.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if instance.status != 'completed':
        return
    
    # Verificar si ya fue desembolsado (si el campo existe)
    try:
        if hasattr(instance, 'credits_disbursed') and instance.credits_disbursed:
            return  # Ya desembolsado
    except Exception:
        pass  # Continuar si hay error al acceder al campo
    
    try:
        with transaction.atomic():
            # Sumar créditos al profile del usuario
            profile = instance.user.profile
            profile.credits += instance.credits_applied
            profile.save(update_fields=['credits'])
            
            # Marcar como desembolsado (si el campo existe)
            try:
                if hasattr(instance, 'credits_disbursed'):
                    instance.credits_disbursed = True
                    instance.save(update_fields=['credits_disbursed'])
            except Exception as e:
                logger.debug(f"No se pudo marcar credits_disbursed en compra {instance.id}: {e}")
            
            logger.info(f"Créditos desembolsados automáticamente: {instance.user.username} ← +{instance.credits_applied} crd")
    except Exception as e:
        logger.exception(f"Error desembolsando créditos para compra {instance.id}: {e}")

