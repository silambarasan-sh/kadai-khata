"""Django settings for kadai_khata project."""

import os
from decimal import Decimal
from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env
load_dotenv(BASE_DIR / ".env")

# DJANGO_DEBUG defaults to False for secure-by-default production
DEBUG = os.getenv("DJANGO_DEBUG", "False").strip().lower() in ("true", "1", "yes")

# DJANGO_SECRET_KEY required outside DEBUG (fail fast with a clear message)
secret_key_env = os.getenv("DJANGO_SECRET_KEY")
if not DEBUG:
    if not secret_key_env:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY environment variable is required when DJANGO_DEBUG is False."
        )
    SECRET_KEY = secret_key_env
else:
    SECRET_KEY = secret_key_env or "django-insecure-kadai-khata-hackathon-2026-indie-track-dev-key"

# ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS from env
allowed_hosts_str = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_str.split(",") if h.strip()]

csrf_trusted_str = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in csrf_trusted_str.split(",") if o.strip()]

# Admin route disabled unless DJANGO_ENABLE_ADMIN=1
DJANGO_ENABLE_ADMIN = os.getenv("DJANGO_ENABLE_ADMIN", "0").strip() in ("1", "true", "yes")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "ledger",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "kadai_khata.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "ledger.context_processors.demo_mode_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "kadai_khata.wsgi.application"

# Database - SQLite path from env DATABASE_PATH
db_path_env = os.getenv("DATABASE_PATH")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(db_path_env) if db_path_env else (BASE_DIR / "db.sqlite3"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images) with WhiteNoise
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Secure cookie & proxy flags when not DEBUG
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Business logic boundaries
MAX_ENTRY_AMOUNT = Decimal(os.getenv("MAX_ENTRY_AMOUNT", "100000.00"))

# Meta AI Integration settings (using OpenAI Python SDK)
META_PROVIDER = os.getenv("META_PROVIDER", "meta").strip().lower()
MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
META_BASE_URL = os.getenv("META_BASE_URL", "https://api.meta.ai/v1")
META_MODEL = os.getenv("META_MODEL", "muse-spark-1.3")
META_MODE = os.getenv("META_MODE", "mock").strip().lower()
META_TIMEOUT_SECONDS = float(os.getenv("META_TIMEOUT_SECONDS", "30.0"))
META_REASONING_EFFORT = os.getenv("META_REASONING_EFFORT", "").strip() or None
META_VISION_REASONING_EFFORT = os.getenv("META_VISION_REASONING_EFFORT", "").strip() or None
META_VISION_TIMEOUT_SECONDS = float(os.getenv("META_VISION_TIMEOUT_SECONDS", "90.0"))
MAX_INPUT_TEXT_LENGTH = int(os.getenv("MAX_INPUT_TEXT_LENGTH", "500"))

# Partner Backend Settings (Meta Muse Spark Open served by Baseten)
PARTNER_API_KEY = os.getenv("PARTNER_API_KEY", "")
PARTNER_BASE_URL = os.getenv("PARTNER_BASE_URL", "https://inference.baseten.co/v1")
PARTNER_MODEL = os.getenv("PARTNER_MODEL", "meta-models/muse-spark-open-1026")
PARTNER_TIMEOUT_SECONDS = float(os.getenv("PARTNER_TIMEOUT_SECONDS", "90.0"))

# Collections Agent settings
AGENT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "6"))
AGENT_MAX_TOOL_CALLS = int(os.getenv("AGENT_MAX_TOOL_CALLS", "12"))
AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "15000"))
AGENT_TIMEOUT_SECONDS = float(os.getenv("AGENT_TIMEOUT_SECONDS", "45.0"))

# DEMO_MODE settings & limits
DEMO_MODE = os.getenv("DEMO_MODE", "0").strip() in ("1", "true", "yes")
DEMO_DAILY_LIVE_CALLS = int(os.getenv("DEMO_DAILY_LIVE_CALLS", "300"))
DEMO_RATE_LIMIT_TEXT = int(os.getenv("DEMO_RATE_LIMIT_TEXT", os.getenv("DEMO_RATE_LIMIT_PARSE", "20")))
DEMO_RATE_LIMIT_ASK = int(os.getenv("DEMO_RATE_LIMIT_ASK", str(DEMO_RATE_LIMIT_TEXT)))
DEMO_RATE_LIMIT_PHOTO = int(os.getenv("DEMO_RATE_LIMIT_PHOTO", "5"))
DEMO_RATE_LIMIT_AGENT = int(os.getenv("DEMO_RATE_LIMIT_AGENT", "3"))
DEMO_RATE_LIMIT_REMINDER = int(os.getenv("DEMO_RATE_LIMIT_REMINDER", "20"))
DEMO_RATE_LIMIT_VOICE = int(os.getenv("DEMO_RATE_LIMIT_VOICE", "10"))

# Voice transcription settings (Meta Muse Voice Transcribe)
VOICE_LANGUAGE_BIAS = os.getenv("VOICE_LANGUAGE_BIAS", "Tamil,English")
VOICE_MAX_SECONDS = float(os.getenv("VOICE_MAX_SECONDS", "20"))
VOICE_MAX_BYTES = int(os.getenv("VOICE_MAX_BYTES", "2000000"))
META_VOICE_TIMEOUT_SECONDS = float(os.getenv("META_VOICE_TIMEOUT_SECONDS", "60.0"))
