"""
Data migration: zero out bonus_credits on all CreditPackage rows.
The referral system replaces automatic bonus credits.
"""
from django.db import migrations


def zero_bonus_credits(apps, schema_editor):
    CreditPackage = apps.get_model('tournament', 'CreditPackage')
    CreditPackage.objects.all().update(bonus_credits=0)


class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0008_knockoutprediction_boost_applied'),
    ]

    operations = [
        migrations.RunPython(
            zero_bonus_credits,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
