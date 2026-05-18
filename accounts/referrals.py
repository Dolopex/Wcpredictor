"""
Lógica escalonada de recompensas por referidos.

Flujo:
  Referido (nuevo usuario):
    - 1.000 crd al registrarse con código
    - 2.000 crd adicionales cuando ese usuario invita a alguien válido
    - 1.000 crd cuando el MISMO usuario hace una compra

  Referidor (quien invitó):
    - 3.000 crd cuando el amigo se registra
    - 1.000 crd cuando el MISMO referidor hace una compra
      (se acumula por cada referido pendiente de ese bono)

Límites anti-abuso:
  - Máximo 5 referidos recompensados por usuario
  - No se puede usar el propio código
  - Una sola relación referidor→referido (OneToOne en Referral)
"""

import logging
from django.db import transaction

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
MAX_REFERRALS        = 5
REFERRER_SIGNUP      = 3_000   # referidor recibe al registrarse el referido
REFERRER_PURCHASE    = 1_000   # referidor recibe cuando ÉL mismo compra (por referido pendiente)
REFERRED_SIGNUP      = 1_000   # referido recibe al registrarse
REFERRED_FRIEND      = 2_000   # referido recibe cuando ÉL mismo invita a alguien
REFERRED_PURCHASE    = 1_000   # referido recibe cuando ÉL mismo compra


def process_referral_signup(new_user, promo_code: str):
    """
    Llamar justo después de crear el usuario si usó un código.
    Retorna (ok: bool, mensaje: str).
    """
    from .models import UserProfile, Referral

    code = promo_code.strip().upper()
    if not code:
        return False, 'Código vacío.'

    # Buscar referidor
    try:
        referrer_profile = UserProfile.objects.select_related('user').get(promo_code=code)
    except UserProfile.DoesNotExist:
        return False, 'Código promocional inválido.'

    referrer = referrer_profile.user

    # Validaciones
    if referrer == new_user:
        return False, 'No puedes usar tu propio código.'

    if Referral.objects.filter(referred=new_user).exists():
        return False, 'Ya tienes un referido registrado.'

    rewarded_count = Referral.objects.filter(
        referrer=referrer, signup_reward_given=True
    ).count()
    if rewarded_count >= MAX_REFERRALS:
        return False, 'Este código ya alcanzó su límite de referidos.'

    with transaction.atomic():
        # Crear relación
        referral = Referral.objects.create(referrer=referrer, referred=new_user)

        # 1.000 crd al nuevo usuario
        new_profile = UserProfile.objects.select_for_update().get(user=new_user)
        new_profile.credits += REFERRED_SIGNUP
        new_profile.save(update_fields=['credits'])
        referral.referred_signup_reward_given = True

        # 3.000 crd al referidor
        ref_profile = UserProfile.objects.select_for_update().get(user=referrer)
        ref_profile.credits += REFERRER_SIGNUP
        ref_profile.save(update_fields=['credits'])
        referral.signup_reward_given = True

        # Si el referidor ya compró, darle los 1.000 inmediatamente
        from tournament.models import CreditPurchase
        if CreditPurchase.objects.filter(user=referrer, status='completed').exists():
            ref_profile.refresh_from_db(fields=['credits'])
            ref_profile.credits += REFERRER_PURCHASE
            ref_profile.save(update_fields=['credits'])
            referral.purchase_reward_given = True

        referral.save()

    # Verificar si el nuevo referidor (new_user) era él mismo un referido que aún no cobró los 2.000
    _check_referred_friend_reward(new_user)

    logger.info(
        'Referral: %s usó código de %s → signup rewards entregadas.',
        new_user.username, referrer.username,
    )
    return True, f'¡Código aplicado! +{REFERRED_SIGNUP:,} créditos de bienvenida.'


def process_referral_on_purchase(user):
    """
    Llamar después de que un pago sea aprobado (en _apply_payment).
    Otorga los bonos de compra pendientes tanto al referidor como al referido.
    """
    from .models import UserProfile, Referral

    with transaction.atomic():
        # ── Bono de compra para el REFERIDOR ──────────────────────────────────
        # Por cada referido suyo cuyo signup_reward ya se dio pero el purchase_reward no
        pending = list(
            Referral.objects.select_for_update().filter(
                referrer=user,
                signup_reward_given=True,
                purchase_reward_given=False,
            )
        )
        if pending:
            bonus = len(pending) * REFERRER_PURCHASE
            profile = UserProfile.objects.select_for_update().get(user=user)
            profile.credits += bonus
            profile.save(update_fields=['credits'])
            for r in pending:
                r.purchase_reward_given = True
                r.save(update_fields=['purchase_reward_given'])
            logger.info(
                'Referral purchase bonus (referrer): +%d crd a %s (%d referidos).',
                bonus, user.username, len(pending),
            )

        # ── Bono de compra para el REFERIDO ───────────────────────────────────
        try:
            referral = Referral.objects.select_for_update().get(
                referred=user,
                referred_signup_reward_given=True,
                referred_purchase_reward_given=False,
            )
            profile = UserProfile.objects.select_for_update().get(user=user)
            profile.credits += REFERRED_PURCHASE
            profile.save(update_fields=['credits'])
            referral.referred_purchase_reward_given = True
            referral.save(update_fields=['referred_purchase_reward_given'])
            logger.info(
                'Referral purchase bonus (referred): +%d crd a %s.',
                REFERRED_PURCHASE, user.username,
            )
        except Referral.DoesNotExist:
            pass


def _check_referred_friend_reward(user):
    """
    Si el usuario era referido y aún no recibió sus 2.000 por invitar a alguien,
    y acaba de hacer su primer referido exitoso, entregarle el bono.
    """
    from .models import UserProfile, Referral

    try:
        own_referral = Referral.objects.get(
            referred=user,
            referred_signup_reward_given=True,
            referred_friend_reward_given=False,
        )
    except Referral.DoesNotExist:
        return  # No era referido o ya cobró el bono

    # Verificar que este usuario ya tiene al menos un referido propio exitoso
    has_made_referral = Referral.objects.filter(
        referrer=user, signup_reward_given=True
    ).exists()
    if not has_made_referral:
        return

    with transaction.atomic():
        own_referral = Referral.objects.select_for_update().get(pk=own_referral.pk)
        if own_referral.referred_friend_reward_given:
            return  # Ya fue dado (carrera de concurrencia)

        profile = UserProfile.objects.select_for_update().get(user=user)
        profile.credits += REFERRED_FRIEND
        profile.save(update_fields=['credits'])
        own_referral.referred_friend_reward_given = True
        own_referral.save(update_fields=['referred_friend_reward_given'])
        logger.info(
            'Referral friend bonus: +%d crd a %s.',
            REFERRED_FRIEND, user.username,
        )


def get_referral_progress(user):
    """
    Devuelve un dict con el progreso del sistema de referidos para mostrar en el frontend.
    """
    from .models import Referral

    referrals_made = list(
        Referral.objects.filter(referrer=user, signup_reward_given=True)
        .select_related('referred')
        .order_by('-created_at')
    )

    total_earned = 0
    for r in referrals_made:
        total_earned += REFERRER_SIGNUP  # siempre dado
        if r.purchase_reward_given:
            total_earned += REFERRER_PURCHASE

    pending_purchase_bonus = sum(
        REFERRER_PURCHASE for r in referrals_made if not r.purchase_reward_given
    )

    # Bono propio si era referido
    own_referral = None
    own_earned = 0
    own_pending = []
    try:
        own_referral = Referral.objects.select_related('referrer').get(referred=user)
        if own_referral.referred_signup_reward_given:
            own_earned += REFERRED_SIGNUP
        if own_referral.referred_friend_reward_given:
            own_earned += REFERRED_FRIEND
        if own_referral.referred_purchase_reward_given:
            own_earned += REFERRED_PURCHASE
        if not own_referral.referred_friend_reward_given:
            own_pending.append({'label': 'Invita a un amigo', 'amount': REFERRED_FRIEND})
        if not own_referral.referred_purchase_reward_given:
            own_pending.append({'label': 'Compra un paquete', 'amount': REFERRED_PURCHASE})
    except Referral.DoesNotExist:
        pass

    return {
        'referrals_made': referrals_made,
        'referrals_count': len(referrals_made),
        'max_referrals': MAX_REFERRALS,
        'slots_remaining': max(0, MAX_REFERRALS - len(referrals_made)),
        'total_earned_as_referrer': total_earned,
        'pending_purchase_bonus': pending_purchase_bonus,
        'own_referral': own_referral,
        'own_earned': own_earned,
        'own_pending': own_pending,
        # Constantes para mostrar en el template
        'C_REFERRER_SIGNUP': REFERRER_SIGNUP,
        'C_REFERRER_PURCHASE': REFERRER_PURCHASE,
        'C_REFERRED_SIGNUP': REFERRED_SIGNUP,
        'C_REFERRED_FRIEND': REFERRED_FRIEND,
        'C_REFERRED_PURCHASE': REFERRED_PURCHASE,
    }
