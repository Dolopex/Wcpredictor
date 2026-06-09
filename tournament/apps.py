from django.apps import AppConfig


class TournamentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tournament'

    def ready(self):
        # Temporalmente desactivado mientras la migración se ejecuta en Vercel
        # import tournament.signals  # noqa: F401
        pass
