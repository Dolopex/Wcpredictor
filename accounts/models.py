from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


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

    class Meta:
        verbose_name = 'Perfil de usuario'
        verbose_name_plural = 'Perfiles de usuarios'

    def __str__(self):
        return f'Perfil de {self.user.username}'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
