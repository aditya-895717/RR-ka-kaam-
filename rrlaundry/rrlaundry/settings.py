import sys
from pathlib import Path

import dj_database_url
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-before-production')

DEBUG = config('DEBUG', default=True, cast=bool)

# Vercel injects the deployment host as VERCEL_URL (no scheme, no port).
# Preview deploys get a fresh subdomain per push, so '.vercel.app' is matched
# as a suffix rather than pinning individual hostnames.
_allowed_hosts = config(
    'DJANGO_ALLOWED_HOSTS',
    default='.vercel.app,localhost,127.0.0.1',
)
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(',') if h.strip()]

_vercel_url = config('VERCEL_URL', default='')
if _vercel_url and _vercel_url not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_vercel_url)

# CSRF needs scheme-qualified origins. Wildcard subdomains are supported by
# Django >= 4.0, which covers every *.vercel.app preview deployment.
_csrf_origins = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.vercel.app',
)
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]
if _vercel_url:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_vercel_url}')

# Vercel terminates TLS at the edge and forwards over HTTP.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third-party
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'rest_framework',
    'corsheaders',
    # Local apps
    'core.apps.CoreConfig',
    'accounts.apps.AccountsConfig',
    'hospital.apps.HospitalConfig',
    'laundry.apps.LaundryConfig',
    'delivery.apps.DeliveryConfig',
    'rfid.apps.RfidConfig',
    'billing.apps.BillingConfig',
    'notifications.apps.NotificationsConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'accounts.middleware.OnboardingRedirectMiddleware',
]

ROOT_URLCONF = 'rrlaundry.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.jinja2.Jinja2',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': False,
        'OPTIONS': {
            'environment': 'rrlaundry.jinja2.environment',
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'rrlaundry.wsgi.application'

# ─────────────────────────────────────────────────────────────────────────────
# Database — Neon (managed Postgres) in every deployed environment.
#
# Neon exposes TWO endpoints for the same database, and they are not
# interchangeable:
#
#   DATABASE_URL         POOLED   host contains '-pooler'.  PgBouncer in
#                                 transaction mode. Correct for the serverless
#                                 runtime — many short-lived lambda connections.
#
#   DIRECT_DATABASE_URL  DIRECT   same host without '-pooler'. Required for
#                                 schema and admin work, because PgBouncer holds
#                                 sessions open. Observed failures when routing
#                                 admin commands through the pooler:
#                                   migrate -> OperationalError: server closed
#                                              the connection unexpectedly
#                                   test    -> OperationalError: database
#                                              "test_neondb" is being accessed
#                                              by other users (the blocking
#                                              session is 'pgbouncer' itself)
#
# The swap below is automatic: any management command in _DIRECT_COMMANDS uses
# the direct endpoint when DIRECT_DATABASE_URL is set. Everything else — i.e.
# the actual WSGI runtime — uses the pooled endpoint.
#
# Two pooler-driven settings apply to the runtime connection:
#
#   conn_max_age=0              Each Vercel invocation is a separate short-lived
#                               process. Persistent connections are never reused
#                               across invocations, so keeping them open only
#                               exhausts the pool. Close on every request.
#
#   DISABLE_SERVER_SIDE_CURSORS Transaction-mode pooling does not guarantee the
#                               same backend connection across statements, so
#                               server-side cursors (used by .iterator()) break.
#
# Falls back to local SQLite when DATABASE_URL is unset so local dev still runs.
# ─────────────────────────────────────────────────────────────────────────────

# Management commands that perform schema changes, bulk loads, or create/drop
# databases. These must not go through PgBouncer.
_DIRECT_COMMANDS = {
    'migrate', 'makemigrations', 'sqlmigrate', 'showmigrations',
    'test', 'flush', 'loaddata', 'dumpdata', 'createsuperuser',
    'squashmigrations', 'seed_demo',
}
_running_direct_command = len(sys.argv) > 1 and sys.argv[1] in _DIRECT_COMMANDS

# Resolved through decouple (reads .env and os.environ) rather than
# dj_database_url.config(), which looks up the env var itself and therefore
# returns an empty config — not the default — when DATABASE_URL is set but
# blank. parse() takes the already-resolved string, so the fallback is honoured.
_pooled_url = config('DATABASE_URL', default='')
_direct_url = config('DIRECT_DATABASE_URL', default='')

# If DIRECT_DATABASE_URL is not set explicitly, derive it: on Neon the direct
# endpoint is the pooled hostname with the '-pooler' suffix removed. Guarded to
# neon.tech so a non-Neon DATABASE_URL is never silently rewritten. An explicit
# DIRECT_DATABASE_URL always wins.
if not _direct_url and '-pooler.' in _pooled_url and 'neon.tech' in _pooled_url:
    _direct_url = _pooled_url.replace('-pooler.', '.')

if _running_direct_command and _direct_url:
    _database_url = _direct_url
else:
    _database_url = _pooled_url

_database_url = _database_url or f'sqlite:///{BASE_DIR / "db.sqlite3"}'
_is_postgres = _database_url.startswith(('postgres://', 'postgresql://'))

DATABASES = {
    'default': dj_database_url.parse(
        _database_url,
        # Admin commands run as one long-lived local process, so recycling the
        # connection per-operation buys nothing there; only the runtime needs 0.
        conn_max_age=0,
        ssl_require=_is_postgres,
    )
}

DISABLE_SERVER_SIDE_CURSORS = _is_postgres

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static_collected'
STATICFILES_DIRS = [BASE_DIR / 'static']

# NOT CompressedManifestStaticFilesStorage. That variant resolves {{ static(...) }}
# through a staticfiles.json manifest written by collectstatic. On Vercel,
# collectstatic runs in the @vercel/static-build container, so the manifest never
# exists inside the Python lambda and every static() call would raise at runtime.
# The non-manifest variant resolves URLs by plain path, which the CDN route in
# vercel.json serves directly. Trade-off: no content-hash cache-busting.
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/accounts/redirect/'

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# django-allauth (allauth 65+ API)
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_USER_MODEL_USERNAME_FIELD = None   # custom user has no 'username' field
SOCIALACCOUNT_AUTO_SIGNUP = True           # skip allauth's own signup form for social logins

ACCOUNT_ADAPTER = 'allauth.account.adapter.DefaultAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'accounts.adapters.CustomSocialAccountAdapter'

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': config('GOOGLE_CLIENT_ID', default=''),
            'secret': config('GOOGLE_CLIENT_SECRET', default=''),
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'FETCH_USERINFO': True,
    }
}

# Email — sender identity for Brevo transactional emails
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@dubeyitsolution.tech')

# CORS
CORS_ALLOW_ALL_ORIGINS = DEBUG

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Background work
#
# django-q2 / Q_CLUSTER was removed here: Vercel's Python runtime is serverless
# and offers no long-lived process type, so `manage.py qcluster` can never run.
# Leaving the config in place would have registered schedule rows in the DB
# that nothing consumes — a silent failure.
#
# The 1-hour missing-item sweep is now an HTTP-triggered endpoint
# (/api/notifications/sweep/) driven by an external pinger every 5 minutes.
# Consequence: alert detection is no longer continuous. Worst-case latency to
# raise an alert is the 60-minute threshold plus one full sweep interval.
# ─────────────────────────────────────────────────────────────────────────────
SWEEP_TOKEN = config('SWEEP_TOKEN', default='')

# Brevo (email)
BREVO_API_KEY = config('BREVO_API_KEY', default='')

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
