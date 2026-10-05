import os
import secrets
import hashlib
import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
os.umask(0o077)
HOSTED = os.environ.get('AUDIT_MODE', 'hosted' if os.environ.get('RENDER') else 'local') == 'hosted'
if os.environ.get('AUDIT_MODE', 'local') not in ('local', 'hosted'):
    raise ImproperlyConfigured('AUDIT_MODE must be local or hosted.')
if os.environ.get('RENDER') and not HOSTED:
    raise ImproperlyConfigured('Render requires hosted mode.')
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(mode=0o700, exist_ok=True)
SECRET_KEY = os.environ.get('AUDIT_SECRET_KEY')
if HOSTED and (not SECRET_KEY or len(SECRET_KEY) < 32):
    raise ImproperlyConfigured('Hosted mode requires AUDIT_SECRET_KEY of at least 32 random characters.')
if not SECRET_KEY:
    key_file = DATA_DIR / 'secret.key'
    try:
        with key_file.open('x') as stream:
            stream.write(secrets.token_urlsafe(64))
    except FileExistsError:
        pass
    SECRET_KEY = key_file.read_text().strip()
# Render generates 256-bit base64 secrets. Normalize to Django's expected length.
if HOSTED:
    SECRET_KEY = hashlib.sha256(SECRET_KEY.encode()).hexdigest()
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('AUDIT_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',') if host.strip()]
render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if HOSTED and render_host:
    ALLOWED_HOSTS.append(render_host)
if HOSTED and '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Wildcard hosts are not permitted in hosted mode.')
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.sessions',
                  'django.contrib.contenttypes', 'django.contrib.staticfiles', 'ledger']
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'ledger.middleware.AccessMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates',
              'DIRS': [], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': [
                  'django.template.context_processors.request',
                  'django.contrib.auth.context_processors.auth',
                  'ledger.views.common_context',
              ]}}]
WSGI_APPLICATION = 'config.wsgi.application'
database_url = os.environ.get('DATABASE_URL')
if HOSTED and not database_url:
    raise ImproperlyConfigured('Hosted mode requires a PostgreSQL DATABASE_URL.')
if database_url:
    DATABASES = {'default': dj_database_url.parse(database_url, conn_max_age=60, conn_health_checks=True)}
    if DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
        raise ImproperlyConfigured('DATABASE_URL must use PostgreSQL; use AUDIT_DB_PATH for local SQLite.')
    DATABASES['default'].setdefault('OPTIONS', {})['sslmode'] = os.environ.get('AUDIT_DB_SSLMODE', 'require' if HOSTED else 'prefer')
else:
    db_path = Path(os.environ.get('AUDIT_DB_PATH', DATA_DIR / 'audit.sqlite3'))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': db_path,
                             'OPTIONS': {'timeout': 15, 'transaction_mode': 'IMMEDIATE'}}}
LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.environ.get('AUDIT_TIME_ZONE', 'UTC')
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage' if HOSTED else 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
WHITENOISE_USE_FINDERS = not HOSTED
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = LOGIN_URL
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = HOSTED
SESSION_COOKIE_AGE = 28800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SECURE = HOSTED
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.environ.get('AUDIT_CSRF_TRUSTED_ORIGINS', '').split(',') if v.strip()]
SECURE_SSL_REDIRECT = HOSTED
SECURE_REDIRECT_EXEMPT = [r'^healthz/$']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if HOSTED else None
SECURE_HSTS_SECONDS = 31536000 if HOSTED else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = HOSTED
SECURE_HSTS_PRELOAD = HOSTED
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.' + name} for name in (
    'UserAttributeSimilarityValidator', 'MinimumLengthValidator', 'CommonPasswordValidator', 'NumericPasswordValidator')]
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
APP_VERSION = '1.0.0'
# Avoid recording local register searches and audit locations in access logs.
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'loggers': {'django.server': {'handlers': [], 'level': 'WARNING', 'propagate': False}}}
