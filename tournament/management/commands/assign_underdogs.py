"""
Comando de gestión: assign_underdogs
=====================================
Asigna multiplicadores underdog automáticos a los usuarios según su posición
en el ranking al finalizar la fase de grupos.

Uso:
    python manage.py assign_underdogs

Correr DESPUÉS de que todos los GroupResult estén ingresados y las predicciones
de grupos hayan sido puntuadas (score_group_predictions).

Tiers de multiplicador:
  ≥ promedio      →  ×1.0  (sin bonus)
  75%–99%         →  ×1.5
  50%–74%         →  ×2.0
  25%–49%         →  ×2.5
   0%–24%         →  ×3.0
"""

from django.core.management.base import BaseCommand
from tournament.utils import assign_underdog_multipliers


class Command(BaseCommand):
    help = 'Asigna multiplicadores underdog a usuarios bajo el promedio de puntos en grupos.'

    def handle(self, *args, **options):
        self.stdout.write('Calculando multiplicadores underdog...')
        result = assign_underdog_multipliers()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Operación completada:"
                f"\n  • Promedio de puntos: {result['avg_points']} pts"
                f"\n  • Usuarios procesados: {result['updated']}"
                f"\n  • Underdogs (bonus > ×1.0): {result['underdogs']}"
            )
        )
