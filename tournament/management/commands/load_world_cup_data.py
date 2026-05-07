"""
Management command para cargar todos los datos del Mundial 2026:
- 48 selecciones con ranking FIFA real
- 12 grupos (A-L) con su composición exacta
- 6 rondas del torneo con puntos base
"""

from django.core.management.base import BaseCommand
from tournament.models import Team, Group, Round


TEAMS = [
    # (name, code, confederation, fifa_ranking, flag_emoji, iso2_code)

    # UEFA — 16 equipos
    ('España', 'ESP', 'UEFA', 1, '🇪🇸', 'es'),
    ('Francia', 'FRA', 'UEFA', 3, '🇫🇷', 'fr'),
    ('Inglaterra', 'ENG', 'UEFA', 4, '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'gb-eng'),
    ('Portugal', 'POR', 'UEFA', 6, '🇵🇹', 'pt'),
    ('Países Bajos', 'NED', 'UEFA', 7, '🇳🇱', 'nl'),
    ('Bélgica', 'BEL', 'UEFA', 8, '🇧🇪', 'be'),
    ('Alemania', 'GER', 'UEFA', 9, '🇩🇪', 'de'),
    ('Croacia', 'CRO', 'UEFA', 10, '🇭🇷', 'hr'),
    ('Suiza', 'SUI', 'UEFA', 17, '🇨🇭', 'ch'),
    ('Austria', 'AUT', 'UEFA', 24, '🇦🇹', 'at'),
    ('Suecia', 'SWE', 'UEFA', 25, '🇸🇪', 'se'),
    ('Turquía', 'TUR', 'UEFA', 28, '🇹🇷', 'tr'),
    ('Noruega', 'NOR', 'UEFA', 29, '🇳🇴', 'no'),
    ('Escocia', 'SCO', 'UEFA', 36, '🏴󠁧󠁢󠁳󠁣󠁴󠁿', 'gb-sct'),
    ('República Checa', 'CZE', 'UEFA', 37, '🇨🇿', 'cz'),
    ('Bosnia y Herzegovina', 'BIH', 'UEFA', 44, '🇧🇦', 'ba'),

    # CONMEBOL — 6 equipos
    ('Argentina', 'ARG', 'CONMEBOL', 2, '🇦🇷', 'ar'),
    ('Brasil', 'BRA', 'CONMEBOL', 5, '🇧🇷', 'br'),
    ('Colombia', 'COL', 'CONMEBOL', 13, '🇨🇴', 'co'),
    ('Uruguay', 'URU', 'CONMEBOL', 16, '🇺🇾', 'uy'),
    ('Ecuador', 'ECU', 'CONMEBOL', 23, '🇪🇨', 'ec'),
    ('Paraguay', 'PAR', 'CONMEBOL', 39, '🇵🇾', 'py'),

    # CONCACAF — 6 equipos
    ('Estados Unidos', 'USA', 'CONCACAF', 14, '🇺🇸', 'us'),
    ('México', 'MEX', 'CONCACAF', 15, '🇲🇽', 'mx'),
    ('Canadá', 'CAN', 'CONCACAF', 27, '🇨🇦', 'ca'),
    ('Panamá', 'PAN', 'CONCACAF', 30, '🇵🇦', 'pa'),
    ('Curazao', 'CUW', 'CONCACAF', 76, '🇨🇼', 'cw'),
    ('Haití', 'HAI', 'CONCACAF', 83, '🇭🇹', 'ht'),

    # AFC — 8 equipos
    ('Irán', 'IRN', 'AFC', 20, '🇮🇷', 'ir'),
    ('Japón', 'JPN', 'AFC', 18, '🇯🇵', 'jp'),
    ('Corea del Sur', 'KOR', 'AFC', 22, '🇰🇷', 'kr'),
    ('Australia', 'AUS', 'AFC', 26, '🇦🇺', 'au'),
    ('Qatar', 'QAT', 'AFC', 51, '🇶🇦', 'qa'),
    ('Uzbekistán', 'UZB', 'AFC', 50, '🇺🇿', 'uz'),
    ('Irak', 'IRQ', 'AFC', 58, '🇮🇶', 'iq'),
    ('Arabia Saudita', 'KSA', 'AFC', 57, '🇸🇦', 'sa'),
    ('Jordania', 'JOR', 'AFC', 61, '🇯🇴', 'jo'),

    # CAF — 10 equipos
    ('Marruecos', 'MAR', 'CAF', 11, '🇲🇦', 'ma'),
    ('Senegal', 'SEN', 'CAF', 19, '🇸🇳', 'sn'),
    ('Egipto', 'EGY', 'CAF', 34, '🇪🇬', 'eg'),
    ('Argelia', 'ALG', 'CAF', 35, '🇩🇿', 'dz'),
    ('Túnez', 'TUN', 'CAF', 40, '🇹🇳', 'tn'),
    ('Costa de Marfil', 'CIV', 'CAF', 42, '🇨🇮', 'ci'),
    ('República Democrática del Congo', 'COD', 'CAF', 56, '🇨🇩', 'cd'),
    ('Ghana', 'GHA', 'CAF', 60, '🇬🇭', 'gh'),
    ('Sudáfrica', 'RSA', 'CAF', 62, '🇿🇦', 'za'),
    ('Cabo Verde', 'CPV', 'CAF', 70, '🇨🇻', 'cv'),

    # OFC — 1 equipo
    ('Nueva Zelanda', 'NZL', 'OFC', 85, '🇳🇿', 'nz'),
]

# Composición de grupos (código del equipo)
GROUPS = {
    'A': ['MEX', 'RSA', 'KOR', 'CZE'],
    'B': ['CAN', 'BIH', 'QAT', 'SUI'],
    'C': ['BRA', 'MAR', 'HAI', 'SCO'],
    'D': ['USA', 'PAR', 'AUS', 'TUR'],
    'E': ['GER', 'CUW', 'CIV', 'ECU'],
    'F': ['NED', 'JPN', 'SWE', 'TUN'],
    'G': ['BEL', 'EGY', 'IRN', 'NZL'],
    'H': ['ESP', 'CPV', 'KSA', 'URU'],
    'I': ['FRA', 'SEN', 'IRQ', 'NOR'],
    'J': ['ARG', 'ALG', 'AUT', 'JOR'],
    'K': ['POR', 'COD', 'UZB', 'COL'],
    'L': ['ENG', 'CRO', 'GHA', 'PAN'],
}

# Rondas: (slug, name, order, base_points)
ROUNDS = [
    ('groups', 'Fase de Grupos', 1, 0),      # puntos se calculan por avance, no por ronda
    ('r32', 'Ronda de 32', 2, 10),
    ('r16', 'Ronda de 16', 3, 15),
    ('qf', 'Cuartos de Final', 4, 20),
    ('sf', 'Semifinales', 5, 25),
    ('final', 'Final', 6, 35),
]


class Command(BaseCommand):
    help = 'Carga todos los datos del Mundial 2026: equipos, grupos y rondas'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Cargando datos del Mundial 2026...'))

        # ── Equipos ──────────────────────────────────────────────────────────
        teams_created = 0
        team_map = {}
        for name, code, confederation, ranking, flag, iso2 in TEAMS:
            team, created = Team.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'confederation': confederation,
                    'fifa_ranking': ranking,
                    'flag_emoji': flag,
                    'iso2_code': iso2,
                }
            )
            if not created:
                # Actualizar datos en caso de que ya existan
                team.name = name
                team.confederation = confederation
                team.fifa_ranking = ranking
                team.flag_emoji = flag
                team.iso2_code = iso2
                team.save()
            team_map[code] = team
            if created:
                teams_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ {teams_created} equipos creados ({len(TEAMS) - teams_created} ya existían)'
        ))

        # ── Grupos ────────────────────────────────────────────────────────────
        groups_created = 0
        for group_name, team_codes in GROUPS.items():
            group, created = Group.objects.get_or_create(name=group_name)
            group.teams.clear()
            for code in team_codes:
                if code in team_map:
                    group.teams.add(team_map[code])
                else:
                    self.stdout.write(self.style.WARNING(f'  ⚠ Código desconocido: {code}'))
            if created:
                groups_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ {groups_created} grupos creados ({len(GROUPS) - groups_created} ya existían y se actualizaron)'
        ))

        # ── Rondas ────────────────────────────────────────────────────────────
        rounds_created = 0
        for slug, name, order, base_pts in ROUNDS:
            round_obj, created = Round.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'order': order,
                    'base_points': base_pts,
                }
            )
            if not created:
                round_obj.name = name
                round_obj.order = order
                round_obj.base_points = base_pts
                round_obj.save()
            if created:
                rounds_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ {rounds_created} rondas creadas ({len(ROUNDS) - rounds_created} ya existían)'
        ))

        self.stdout.write(self.style.SUCCESS(
            '\n¡Datos cargados exitosamente! Total: '
            f'{len(TEAMS)} equipos, {len(GROUPS)} grupos, {len(ROUNDS)} rondas.'
        ))
        self.stdout.write(self.style.NOTICE(
            'Próximo paso: python manage.py createsuperuser'
        ))
