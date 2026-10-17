"""
Django settings for BikeAble.

Every value that differs between machines (secrets, debug, hosts, AI config) comes from
environment variables. A `.env` file in the repo root is loaded automatically; see
`.env.example`. With no `.env` at all the app still starts with safe dev defaults.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from config.ai_mode import resolve_ai_mode

BASE_DIR = Path(__file__).resolve().parent.parent

# Real environment variables win over values in .env (override=False is the default).
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


# --- Core -------------------------------------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", default=True)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")
    # Local development only: never used when DEBUG is off (see check above).
    SECRET_KEY = "django-insecure-local-dev-only"  # nosec B105

# localhost always works; add LAN IPs (e.g. 192.168.1.23) via DJANGO_ALLOWED_HOSTS so a
# phone on the same Wi-Fi can open `runserver 0.0.0.0:8000`.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", *env_list("DJANGO_ALLOWED_HOSTS")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "reports",
    "ai",
    "routes",
    "web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],  # templates live in each app's templates/ folder (APP_DIRS)
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Skopje"
USE_I18N = True
USE_TZ = True

# --- Static files and uploads -----------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # filled by `collectstatic`, not committed

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"  # user-uploaded hazard photos, not committed

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Django REST framework --------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        # Clickable HTML view of the API, only while developing.
        *(["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    ],
    # Every API error -> {"error": {"code", "message", "fields"}} (see API_CONTRACT.md).
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
}

# --- AI (Google Gemini via a free-tier Google AI Studio key) ----------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "")
# "mock" unless explicitly set to "live" AND a key + model are present.
AI_MODE = resolve_ai_mode(os.getenv("AI_MODE", "mock"), GEMINI_API_KEY, GEMINI_MODEL)
# Mock mode only: "rate_limited" or "unavailable" makes every analysis fail that way, to try
# the error screens without a key. Empty = normal mock answers.
AI_MOCK_FORCE = os.getenv("AI_MOCK_FORCE", "").strip().lower()
