import secrets
import string

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


def _generate_promo_code():
    """Genera un código único de 7 caracteres alfanuméricos en mayúsculas."""
    chars = string.ascii_uppercase + string.digits
    for _ in range(20):  # max 20 intentos
        code = ''.join(secrets.choice(chars) for _ in range(7))
        if not UserProfile.objects.filter(promo_code=code).exists():
            return code
    # Fallback con más entropía si colisión (muy improbable)
    return secrets.token_hex(4).upper()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    total_points = models.IntegerField(default=0)
    credits = models.IntegerField(default=0, verbose_name='Créditos')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    full_name = models.CharField(max_length=120, blank=True, verbose_name='Nombre completo')
    phone_number = models.CharField(max_length=20, blank=True, verbose_name='Teléfono')
    underdog_multiplier = models.FloatField(
        default=1.0,
        verbose_name='Multiplicador underdog',
        help_text='Multiplicador aplicable a partidos elegidos por el usuario.'
    )
    underdog_boost_uses = models.IntegerField(
        default=0,
        verbose_name='Usos de potenciador',
        help_text='Cantidad de partidos en los que puede activar el potenciador underdog.',
    )
    promo_code = models.CharField(
        max_length=10, unique=True, blank=True,
        verbose_name='Código promocional',
        help_text='Código único para invitar amigos.',
    )

    class Meta:
        verbose_name = 'Perfil de usuario'
        verbose_name_plural = 'Perfiles de usuarios'

    def __str__(self):
        return f'Perfil de {self.user.username}'

    def save(self, *args, **kwargs):
        if not self.promo_code:
            self.promo_code = _generate_promo_code()
        super().save(*args, **kwargs)


class Referral(models.Model):
    """Registro de una relación referidor → referido y el estado de sus recompensas."""
    referrer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='referrals_made',
        verbose_name='Referidor',
    )
    referred = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='referral',
        verbose_name='Referido',
    )
    # Recompensas para el referidor
    signup_reward_given = models.BooleanField(
        default=False, verbose_name='3.000 crd referidor (registro)')
    purchase_reward_given = models.BooleanField(
        default=False, verbose_name='1.000 crd referidor (compra propia)')
    # Recompensas para el referido
    referred_signup_reward_given = models.BooleanField(
        default=False, verbose_name='1.000 crd referido (registro)')
    referred_friend_reward_given = models.BooleanField(
        default=False, verbose_name='2.000 crd referido (invita a alguien)')
    referred_purchase_reward_given = models.BooleanField(
        default=False, verbose_name='1.000 crd referido (compra propia)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Referido'
        verbose_name_plural = 'Referidos'

    def __str__(self):
        return f'{self.referrer.username} → {self.referred.username}'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
