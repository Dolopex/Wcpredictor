import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'worldcup_predictor.settings')

import django
django.setup()

# Aplicar migraciones pendientes en cada cold start (Vercel serverless)
from django.core.management import call_command
try:
    call_command('migrate', '--no-input', verbosity=0)
except Exception as _e:
    import logging
    logging.getLogger(__name__).error('migrate falló en startup: %s', _e)

from django.core.wsgi import get_wsgi_application
app = get_wsgi_application()
