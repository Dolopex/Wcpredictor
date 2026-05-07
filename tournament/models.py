from django.db import models
from django.contrib.auth.models import User


class Team(models.Model):
    CONFEDERATION_CHOICES = [
        ('UEFA', 'UEFA - Europa'),
        ('CONMEBOL', 'CONMEBOL - Sudamérica'),
        ('AFC', 'AFC - Asia'),
        ('CAF', 'CAF - África'),
        ('CONCACAF', 'CONCACAF - Norte/Centro América'),
        ('OFC', 'OFC - Oceanía'),
    ]
    name = models.CharField(max_length=100, verbose_name='Nombre')
    code = models.CharField(max_length=3, unique=True, verbose_name='Código')
    confederation = models.CharField(max_length=10, choices=CONFEDERATION_CHOICES, verbose_name='Confederación')
    fifa_ranking = models.IntegerField(verbose_name='Ranking FIFA')
    flag_emoji = models.CharField(max_length=10, blank=True, verbose_name='Emoji bandera')
    iso2_code = models.CharField(max_length=10, blank=True, verbose_name='Código ISO2 (bandera)')

    @property
    def flag_url(self):
        if self.iso2_code:
            return f'https://flagcdn.com/w80/{self.iso2_code.lower()}.png'
        return ''

    @property
    def flag_url_sm(self):
        if self.iso2_code:
            return f'https://flagcdn.com/w40/{self.iso2_code.lower()}.png'
        return ''

    class Meta:
        ordering = ['fifa_ranking']
        verbose_name = 'Selección'
        verbose_name_plural = 'Selecciones'

    def __str__(self):
        return f'{self.flag_emoji} {self.name} (#{self.fifa_ranking})'


class Group(models.Model):
    GROUP_CHOICES = [(c, c) for c in 'ABCDEFGHIJKL']
    name = models.CharField(max_length=1, choices=GROUP_CHOICES, unique=True, verbose_name='Grupo')
    teams = models.ManyToManyField(Team, related_name='groups', verbose_name='Equipos')

    class Meta:
        ordering = ['name']
        verbose_name = 'Grupo'
        verbose_name_plural = 'Grupos'

    def __str__(self):
        return f'Grupo {self.name}'


class Round(models.Model):
    ROUND_CHOICES = [
        ('groups', 'Fase de Grupos'),
        ('r32', 'Ronda de 32'),
        ('r16', 'Ronda de 16'),
        ('qf', 'Cuartos de Final'),
        ('sf', 'Semifinales'),
        ('final', 'Final'),
    ]
    slug = models.CharField(max_length=10, choices=ROUND_CHOICES, unique=True, verbose_name='Código de ronda')
    name = models.CharField(max_length=50, verbose_name='Nombre')
    order = models.PositiveSmallIntegerField(verbose_name='Orden')
    base_points = models.IntegerField(default=10, verbose_name='Puntos base por acierto')
    is_active = models.BooleanField(default=False, verbose_name='Ronda activa (visible para predicciones)')
    is_locked = models.BooleanField(default=False, verbose_name='Predicciones cerradas')

    class Meta:
        ordering = ['order']
        verbose_name = 'Ronda'
        verbose_name_plural = 'Rondas'

    def __str__(self):
        return self.name


class Match(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='matches', verbose_name='Ronda')
    match_number = models.PositiveIntegerField(verbose_name='Número de partido')
    team1 = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='matches_as_team1', verbose_name='Equipo 1')
    team2 = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='matches_as_team2', verbose_name='Equipo 2')
    winner = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='matches_won', verbose_name='Ganador real')
    match_date = models.DateTimeField(null=True, blank=True, verbose_name='Fecha del partido')
    description = models.CharField(max_length=100, blank=True, verbose_name='Descripción (ej: Ganador Grupo A)')

    class Meta:
        ordering = ['round__order', 'match_number']
        verbose_name = 'Partido'
        verbose_name_plural = 'Partidos'

    def __str__(self):
        t1 = self.team1.name if self.team1 else '?'
        t2 = self.team2.name if self.team2 else '?'
        return f'{self.round.name} - Partido {self.match_number}: {t1} vs {t2}'


class GroupResult(models.Model):
    """Resultado real de la fase de grupos — lo ingresa el admin."""
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='results', verbose_name='Grupo')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='group_results', verbose_name='Equipo')
    position = models.PositiveSmallIntegerField(verbose_name='Posición final (1-4)')
    is_advancing = models.BooleanField(default=False, verbose_name='¿Avanza a siguiente ronda?')

    class Meta:
        unique_together = ('group', 'team')
        ordering = ['group__name', 'position']
        verbose_name = 'Resultado de grupo'
        verbose_name_plural = 'Resultados de grupos'

    def __str__(self):
        return f'{self.group} - {self.position}° {self.team.name}'


class GroupPrediction(models.Model):
    """El usuario predice qué 2 equipos avanzan de un grupo (y cuál queda 1°)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_predictions')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='predictions')
    predicted_first = models.ForeignKey(Team, on_delete=models.CASCADE,
                                         related_name='predicted_first', verbose_name='Predicción 1° lugar')
    predicted_second = models.ForeignKey(Team, on_delete=models.CASCADE,
                                          related_name='predicted_second', verbose_name='Predicción 2° lugar')
    points_earned = models.IntegerField(default=0, verbose_name='Puntos ganados')
    is_scored = models.BooleanField(default=False, verbose_name='Ya se calcularon puntos')
    bet_credits = models.IntegerField(default=0, verbose_name='Créditos apostados')
    credits_won = models.IntegerField(default=0, verbose_name='Créditos ganados/perdidos')

    class Meta:
        unique_together = ('user', 'group')
        verbose_name = 'Predicción de grupo'
        verbose_name_plural = 'Predicciones de grupos'

    def __str__(self):
        return f'{self.user.username} - {self.group}: {self.predicted_first.name} / {self.predicted_second.name}'


class KnockoutPrediction(models.Model):
    """El usuario predice el ganador de un partido de fase eliminatoria."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='knockout_predictions')
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='predictions')
    predicted_winner = models.ForeignKey(Team, on_delete=models.CASCADE,
                                          related_name='predicted_wins', verbose_name='Ganador predicho')
    points_earned = models.IntegerField(default=0, verbose_name='Puntos ganados')
    is_correct = models.BooleanField(null=True, blank=True, verbose_name='¿Acertó?')
    bet_credits = models.IntegerField(default=0, verbose_name='Créditos apostados')
    credits_won = models.IntegerField(default=0, verbose_name='Créditos ganados/perdidos')

    class Meta:
        unique_together = ('user', 'match')
        verbose_name = 'Predicción eliminatoria'
        verbose_name_plural = 'Predicciones eliminatorias'

    def __str__(self):
        return f'{self.user.username} - {self.match}: predice {self.predicted_winner.name}'
