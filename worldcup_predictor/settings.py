"""
Django settings for worldcup_predictor project.
"""

from pathlib import Path
from decouple import config
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-solo-para-desarrollo-local')
DEBUG = config('DEBUG', default=False, cast=bool)

# Seguridad: impedir inicio en producción con clave insegura
if not DEBUG and 'insecure' in SECRET_KEY:
    raise RuntimeError(
        'SECRET_KEY no está configurada de forma segura. '
        'Agrega SECRET_KEY=<clave-larga-aleatoria> en el archivo .env antes de publicar.'
    )
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost').split(',')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'tournament',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Sirve estáticos en producción
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'worldcup_predictor.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'worldcup_predictor.wsgi.application'


# Database
# En producción usa DATABASE_URL (Neon/PostgreSQL). En local puede seguir siendo SQLite.
DATABASE_URL = config('DATABASE_URL', default='')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 30,
            },
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'es'

TIME_ZONE = 'America/Bogota'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ── Mercado Pago ──────────────────────────────────────────────────────────────
MERCADOPAGO_ACCESS_TOKEN = config('MERCADOPAGO_ACCESS_TOKEN', default='')
MERCADOPAGO_WEBHOOK_SECRET = config('MERCADOPAGO_WEBHOOK_SECRET', default='')

# ── Seguridad ─────────────────────────────────────────────────────────────────
# Cabeceras aplicadas en todos los entornos
SECURE_CONTENT_TYPE_NOSNIFF = True   # Evita que el navegador adivine el tipo de archivo
X_FRAME_OPTIONS = 'DENY'             # Evita que la app se muestre dentro de un iframe
CSRF_COOKIE_HTTPONLY = False         # Debe ser False para compatibilidad con JS (Django default)
SESSION_COOKIE_HTTPONLY = True       # La cookie de sesión no es accesible desde JavaScript

# Cabeceras adicionales solo en producción (cuando DEBUG=False)
if not DEBUG:
    SECURE_SSL_REDIRECT = True                 # Redirige HTTP → HTTPS automáticamente
    SESSION_COOKIE_SECURE = True               # Cookie de sesión solo por HTTPS
    CSRF_COOKIE_SECURE = True                  # Cookie CSRF solo por HTTPS
    SECURE_HSTS_SECONDS = 31536000             # HSTS: fuerza HTTPS por 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True      # Incluye subdominios en HSTS
    SECURE_HSTS_PRELOAD = True                 # Permite inclusión en lista HSTS preload

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
