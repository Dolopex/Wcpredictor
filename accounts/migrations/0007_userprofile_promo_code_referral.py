from django.db import migrations, models
import django.db.models.deletion
import accounts.models


def generate_codes_for_existing_profiles(apps, schema_editor):
    """Genera promo_code para perfiles existentes."""
    import secrets, string
    UserProfile = apps.get_model('accounts', 'UserProfile')
    chars = string.ascii_uppercase + string.digits
    used = set()
    for profile in UserProfile.objects.filter(promo_code=''):
        while True:
            code = ''.join(secrets.choice(chars) for _ in range(7))
            if code not in used:
                used.add(code)
                break
        profile.promo_code = code
        profile.save(update_fields=['promo_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_userprofile_underdog_boost_uses_and_more'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='promo_code',
            field=models.CharField(
                blank=True, default='', max_length=10,
                verbose_name='Código promocional',
                help_text='Código único para invitar amigos.',
            ),
            preserve_default=False,
        ),
        migrations.RunPython(
            generate_codes_for_existing_profiles,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='promo_code',
            field=models.CharField(
                max_length=10, unique=True, blank=True,
                verbose_name='Código promocional',
                help_text='Código único para invitar amigos.',
            ),
        ),
        migrations.CreateModel(
            name='Referral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('signup_reward_given', models.BooleanField(default=False, verbose_name='3.000 crd referidor (registro)')),
                ('purchase_reward_given', models.BooleanField(default=False, verbose_name='1.000 crd referidor (compra propia)')),
                ('referred_signup_reward_given', models.BooleanField(default=False, verbose_name='1.000 crd referido (registro)')),
                ('referred_friend_reward_given', models.BooleanField(default=False, verbose_name='2.000 crd referido (invita a alguien)')),
                ('referred_purchase_reward_given', models.BooleanField(default=False, verbose_name='1.000 crd referido (compra propia)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('referrer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='referrals_made',
                    to='auth.user',
                    verbose_name='Referidor',
                )),
                ('referred', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='referral',
                    to='auth.user',
                    verbose_name='Referido',
                )),
            ],
            options={
                'verbose_name': 'Referido',
                'verbose_name_plural': 'Referidos',
            },
        ),
    ]
