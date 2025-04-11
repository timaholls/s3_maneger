import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-default-key-change-this')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['manager.bytegate.ru', 'localhost', '127.0.0.1']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # <-- ADD THIS LINE

    # Third party apps
    'storages',

    # Local apps
    's3app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Лимит по запросам в минуту
    's3app.rate_limit.RateLimitMiddleware',  # ИЛИ 'your_project_name.middleware.RateLimitMiddleware'

    # Проверка JS при входе
    's3app.middleware.BrowserChallengeMiddleware',
    # Проверка страницы админа
    's3app.middleware.AdminAccessMiddleware',  # <-- Укажите правильный путь к классу

    # Проверка документов для подписания
    's3app.middleware.DocumentSignatureCheckMiddleware',
]

# (Опционально) Настройки для RateLimitMiddleware
RATE_LIMIT_REQUESTS = 60  # Максимум 60 запросов
RATE_LIMIT_PERIOD = 60  # за 60 секунд (1 минута)

# Настройки блокировки IP при превышении лимита
IP_BLOCK_DURATION = 1800  # Блокировка на 30 минут (в секундах)
IP_BLOCK_THRESHOLD = 3  # Блокировка после 3 нарушений лимита запросов
TRUSTED_IPS = ['127.0.0.1']  # Список доверенных IP, которые не подлежат ограничениям

# Настройки для проверки браузера для BrowserChallengeMiddleware
BROWSER_CHALLENGE_COOKIE_NAME = 'browser_verified'
BROWSER_CHALLENGE_COOKIE_VALUE = 'passed_v1'  # Можно менять значение при обновлении логики
BROWSER_CHALLENGE_COOKIE_AGE = 60 * 60 * 24 * 7  # Срок жизни cookie (например, 1 неделя в секундах)
BROWSER_CHALLENGE_URL = '/browser-challenge/'  # Updated with /manager/ prefix
BROWSER_VALIDATION_URL = '/browser-challenge/validate/'  # Updated with /manager/ prefix

ROOT_URLCONF = 'S3_manager.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'S3_manager.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
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
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# S3 Storage Configuration
if os.environ.get('USE_S3', 'False') == 'True':
    # S3 additional settings
    AWS_DEFAULT_ACL = 'private'
    AWS_S3_CUSTOM_DOMAIN = None
    AWS_QUERYSTRING_AUTH = True
    AWS_S3_FILE_OVERWRITE = False

    # Make boto3 use the configured endpoint url
    AWS_S3_ADDRESSING_STYLE = 'virtual'
    AWS_S3_SIGNATURE_VERSION = 's3v4'

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Login & Logout URLs
LOGIN_URL = '/login/'  # Updated with /manager/ prefix
LOGIN_REDIRECT_URL = '/browser/'  # Updated to point to browser explicitly
LOGOUT_REDIRECT_URL = '/login/'  # Updated with /manager/ prefix
