"""Settings for the DCLD study data management system (Muhimbili National Hospital).

Everything that differs between a laptop and the Hostinger server comes from environment variables (.env).
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-only-insecure-key')
DEBUG = env_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:8000').rstrip('/')
SITE_NAME = os.environ.get('SITE_NAME', 'DCLD Study')

if not DEBUG and SECRET_KEY == 'dev-only-insecure-key' and not os.environ.get('ALLOW_INSECURE_KEY'):
    raise RuntimeError('Set DJANGO_SECRET_KEY (or DJANGO_DEBUG=true for local development).')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'simple_history',
    'django_celery_beat',
    'accounts',
    'crf',
    'quality',
    'exports',
    'reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    'accounts.middleware.ApprovedUserMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'accounts.context_processors.site',
    ]},
}]

WSGI_APPLICATION = 'config.wsgi.application'

# --- Database: MySQL (Docker service cld-db). DB_ENGINE=sqlite is only for quick local tests. ---
if os.environ.get('DB_ENGINE', 'mysql') == 'sqlite':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
else:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'cld_study'),
        'USER': os.environ.get('DB_USER', 'cld_study'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'cld-db'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {'charset': 'utf8mb4', 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"},
        'TEST': {'CHARSET': 'utf8mb4', 'COLLATION': 'utf8mb4_unicode_ci'},
    }}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'
# Lets the login form tell an unconfirmed or deactivated person why they cannot log in.
AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.AllowAllUsersModelBackend']
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24  # reset and verification links work for 24 hours
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

LANGUAGE_CODE = 'en-gb'
TIME_ZONE = os.environ.get('DJANGO_TIME_ZONE', 'Africa/Dar_es_Salaam')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'
                    if not DEBUG else 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

# --- Email: file-based until SMTP is configured (nothing is sent). ---
EMAIL_BACKEND = os.environ.get('DJANGO_EMAIL_BACKEND', 'django.core.mail.backends.filebased.EmailBackend')
EMAIL_FILE_PATH = str(BASE_DIR / os.environ.get('EMAIL_FILE_PATH', 'sent_emails'))
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '15'))
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'DCLD Study <no-reply@example.org>')

# --- Study ---
STUDY_START_DATE = os.environ.get('STUDY_START_DATE', '')  # YYYY-MM-DD; interviews before it are flagged
STUDY_ID_PREFIX = os.environ.get('STUDY_ID_PREFIX', 'CLD')
STUDY_TARGET = int(os.environ.get('STUDY_TARGET', '0') or 0)  # planned sample size; 0 = not set

# --- Background jobs (Celery worker + beat, Redis broker). Schedules live in the database (Django admin). ---
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://cld-redis:6379/0')
CELERY_TASK_IGNORE_RESULT = True  # progress of exports is tracked in the database, not in Celery results
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'
if TESTING or env_bool('CELERY_TASK_ALWAYS_EAGER', False):
    CELERY_TASK_ALWAYS_EAGER = True  # run tasks immediately (tests, or a laptop without Redis)
    CELERY_TASK_EAGER_PROPAGATES = True
    CELERY_BROKER_URL = 'memory://'

EXPORT_FILE_HOURS = int(os.environ.get('EXPORT_FILE_HOURS', '24'))  # finished exports are deleted after this
PENDING_REMINDER_DAYS = int(os.environ.get('PENDING_REMINDER_DAYS', '2'))  # remind about records older than this

# --- HTTPS (server). Behind the host nginx, which sets X-Forwarded-Proto. ---
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '0'))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
