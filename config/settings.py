import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
os.umask(0o077)
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(mode=0o700, exist_ok=True)
SECRET_KEY = os.environ.get('AUDIT_SECRET_KEY')
if not SECRET_KEY:
    key_file = DATA_DIR / 'secret.key'
    try:
        with key_file.open('x') as stream:
            stream.write(secrets.token_urlsafe(64))
    except FileExistsError:
        pass
    SECRET_KEY = key_file.read_text().strip()
DEBUG = False
ALLOWED_HOSTS = os.environ.get('AUDIT_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',')
INSTALLED_APPS = ['django.contrib.contenttypes', 'django.contrib.staticfiles', 'ledger']
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'ledger.middleware.LocalOnlyMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates',
              'DIRS': [], 'APP_DIRS': True,
              'OPTIONS': {'context_processors': [
                  'django.template.context_processors.request',
                  'ledger.views.common_context',
              ]}}]
WSGI_APPLICATION = 'config.wsgi.application'
db_path = Path(os.environ.get('AUDIT_DB_PATH', DATA_DIR / 'audit.sqlite3'))
if not db_path.is_absolute():
    db_path = BASE_DIR / db_path
db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': db_path,
                         'OPTIONS': {'timeout': 15, 'transaction_mode': 'IMMEDIATE'}}}
LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.environ.get('AUDIT_TIME_ZONE', 'UTC')
USE_TZ = True
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
APP_VERSION = '1.0.0'
# Avoid recording local register searches and audit locations in access logs.
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'loggers': {'django.server': {'handlers': [], 'level': 'WARNING', 'propagate': False}}}
