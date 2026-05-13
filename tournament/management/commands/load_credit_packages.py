from django.core.management.base import BaseCommand
from tournament.models import CreditPackage


# ── Cálculo de referencia ─────────────────────────────────────────────────────
#  Grupos:            2 equipos × 12 grupos  = 24 × $500   = $12.000
#  Mejores terceros:  8 apuestas             = 8  × $500   = $4.000 (regalo)
#  R32 dieciseisavos: 16 partidos            = 16 × $500   = $8.000
#  Octavos (R16):     8 partidos             = 8  × $1.000 = $8.000
#  Cuartos (QF):      4 partidos             = 4  × $1.000 = $4.000
#  Semis (SF):        2 partidos             = 2  × $2.000 = $4.000
#  Gran Final:        1 partido              = 1  × $2.000 = $2.000
#  ─────────────────────────────────────────────────────────────────────────────
#  Total eliminatorias:             8+8+4+4+2 = 26.000 crd
#  Comprando por fases:   $12.000 + $22.000  = $34.000
#  Pase Completo:                              $30.000  (ahorra $4.000)
# ─────────────────────────────────────────────────────────────────────────────

PACKAGES = [
    {
        # Grupos: 24 apuestas × 500 = 12.000 + regalo 4.000 (mejores terceros)
        'name': 'Fase de Grupos',
        'cop_price': 12_000,
        'credits_amount': 12_000,
        'bonus_credits': 4_000,
        'is_featured': False,
        'order': 1,
    },
    {
        # R32 (8.000) + R16 (8.000) + QF (4.000) + SF (4.000) + Final (2.000) = 26.000
        'name': 'Pase Eliminatorias',
        'cop_price': 22_000,
        'credits_amount': 26_000,
        'bonus_credits': 0,
        'is_featured': False,
        'order': 2,
    },
    {
        # Grupos (12.000) + Eliminatorias (26.000) + regalo terceros (4.000) = 42.000
        # Comprando por separado: $12.000 + $22.000 = $34.000 → aquí $30.000 (ahorras $4.000)
        'name': 'Pase Completo',
        'cop_price': 30_000,
        'credits_amount': 38_000,
        'bonus_credits': 4_000,
        'is_featured': True,
        'order': 3,
    },
]


class Command(BaseCommand):
    help = 'Carga/actualiza los paquetes de créditos por fase del torneo.'

    def handle(self, *args, **options):
        # Desactivar paquetes viejos que ya no existen en la lista
        new_names = {p['name'] for p in PACKAGES}
        deactivated = CreditPackage.objects.exclude(name__in=new_names).update(is_active=False)
        if deactivated:
            self.stdout.write(self.style.WARNING(
                f'{deactivated} paquete(s) antiguo(s) desactivado(s).'
            ))

        created = updated = 0
        for data in PACKAGES:
            obj, was_created = CreditPackage.objects.update_or_create(
                name=data['name'],
                defaults={**data, 'is_active': True},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Paquetes: {created} creados, {updated} actualizados.'
        ))
        self.stdout.write('')
        for p in PACKAGES:
            total = p['credits_amount'] + p['bonus_credits']
            self.stdout.write(
                f"  {p['name']:20s}  ${p['cop_price']:>7,} COP  →  {total:>6,} créditos"
            )
