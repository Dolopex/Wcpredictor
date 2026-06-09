# Generated migration for adding credits_disbursed field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0009_zero_bonus_credits'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditpurchase',
            name='credits_disbursed',
            field=models.BooleanField(default=False, verbose_name='Créditos desembolsados'),
        ),
    ]
