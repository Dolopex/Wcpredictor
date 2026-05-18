"""
Sistema de referidos — flujo simplificado.

Flujo:
  Cuando alguien se registra con un código de invitación:
    -> El nuevo usuario recibe 1.000 creditos de bienvenida
    -> El referidor recibe 1.000 creditos

Limites:
  - Maximo 4 referidos recompensados por usuario
  - No se puede usar el propio codigo
  - Un usuario solo puede tener un referidor (OneToOne en Referral)
"""

import logging
from django.db import transaction

logger = logging.getLogger(__name__)

# Constantes
MAX_REFERRALS = 4
REWARD_EACH   = 1_000   # Ambos reciben 1.000 crd al registrarse


def process_referral_signup(new_user, promo_code: str):
    """
    Llamar justo despues de crear el usuario si uso un codigo.
    Otorga 1.000 crd al nuevo usuario y 1.000 crd al referidor.
    Retorna (ok: bool, mensaje: str).
    """
    from .models import UserProfile, Referral

    code = promo_code.strip().upper()
    if not code:
        return False, 'Codigo vacio.'

    try:
        referrer_profile = UserProfile.objects.select_related('user').get(promo_code=code)
    except UserProfile.DoesNotExist:
        return False, 'Codigo promocional invalido.'

    referrer = referrer_profile.user

    if referrer == new_user:
        return False, 'No puedes usar tu propio codigo.'

    if Referral.objects.filter(referred=new_user).exists():
        return False, 'Ya tienes un referido registrado.'

    rewarded_count = Referral.objects.filter(
        referrer=referrer, signup_reward_given=True
    ).count()
    if rewarded_count >= MAX_REFERRALS:
        return False, 'Este codigo ya alcanzo su limite de referidos.'

    with transaction.atomic():
        referral = Referral.objects.create(referrer=referrer, referred=new_user)

        new_profile = UserProfile.objects.select_for_update().get(user=new_user)
        new_profile.credits += REWARD_EACH
        new_profile.save(update_fields=['credits'])
        referral.referred_signup_reward_given = True

        ref_profile = UserProfile.objects.select_for_update().get(user=referrer)
        ref_profile.credits += REWARD_EACH
        ref_profile.save(update_fields=['credits'])
        referral.signup_reward_given = True

        referral.save()

    logger.info(
        'Referral: %s uso codigo de %s -> +%d crd a cada uno.',
        new_user.username, referrer.username, REWARD_EACH,
    )
    return True, f'Codigo aplicado! +{REWARD_EACH:,} creditos de bienvenida.'


def get_referral_progress(user):
    """
    Devuelve un dict con el progreso del sistema de referidos para el frontend.
    """
    from .models import Referral

    referrals_made = list(
        Referral.objects.filter(referrer=user, signup_reward_given=True)
        .select_related('referred')
        .order_by('-created_at')
    )

    total_earned = len(referrals_made) * REWARD_EACH

    own_referral = None
    try:
        own_referral = Referral.objects.select_related('referrer').get(referred=user)
    except Referral.DoesNotExist:
        pass

    return {
        'referrals_made': referrals_made,
        'referrals_count': len(referrals_made),
        'max_referrals': MAX_REFERRALS,
        'slots_remaining': max(0, MAX_REFERRALS - len(referrals_made)),
        'total_earned_as_referrer': total_earned,
        'own_referral': own_referral,
        'C_REWARD_EACH': REWARD_EACH,
    }
