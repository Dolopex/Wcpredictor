import logging
from django.db import transaction
from django.db.models import F

logger = logging.getLogger(__name__)

MAX_REFERRALS_BASE     = 4  # sin codigo de referido al registrarse
MAX_REFERRALS_REFERRED = 3  # con codigo de referido (ya recibio 1k extra)
REWARD_EACH            = 1000


def _max_referrals_for(user):
    """Usuarios que fueron referidos pueden invitar a 3 (1k+3k=4k total).
    Usuarios sin codigo pueden invitar a 4 (4k total)."""
    from .models import Referral
    was_referred = Referral.objects.filter(
        referred=user, referred_signup_reward_given=True
    ).exists()
    return MAX_REFERRALS_REFERRED if was_referred else MAX_REFERRALS_BASE


def process_referral_signup(new_user, promo_code):
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

    max_for_referrer = _max_referrals_for(referrer)
    rewarded_count = Referral.objects.filter(
        referrer=referrer, signup_reward_given=True
    ).count()
    if rewarded_count >= max_for_referrer:
        return False, 'Este codigo ya alcanzo su limite de referidos.'

    with transaction.atomic():
        referral = Referral.objects.create(referrer=referrer, referred=new_user)

        UserProfile.objects.filter(user=new_user).update(credits=F('credits') + REWARD_EACH)
        referral.referred_signup_reward_given = True

        UserProfile.objects.filter(user=referrer).update(credits=F('credits') + REWARD_EACH)
        referral.signup_reward_given = True

        referral.save()

    logger.info(
        'Referral: %s uso codigo de %s -> +%d crd a cada uno.',
        new_user.username, referrer.username, REWARD_EACH,
    )
    return True, 'Codigo aplicado! +{} creditos de bienvenida.'.format(REWARD_EACH)


def get_referral_progress(user):
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

    max_referrals = _max_referrals_for(user)

    return {
        'referrals_made': referrals_made,
        'referrals_count': len(referrals_made),
        'max_referrals': max_referrals,
        'slots_remaining': max(0, max_referrals - len(referrals_made)),
        'total_earned_as_referrer': total_earned,
        'own_referral': own_referral,
        'C_REWARD_EACH': REWARD_EACH,
    }