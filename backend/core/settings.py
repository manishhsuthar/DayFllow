"""Django settings for DayFlow.

Everything environment-specific is read from the environment. The defaults are
chosen to be safe in production: anything that would weaken security must be
switched on deliberately, never left on by accident.

See docs/CONFIGURATION.md for the full variable reference.
"""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default=None):
    raw = os.getenv(name, "")
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(default or [])


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer, got {raw!r}") from exc


# DEBUG defaults to False. The previous default was True, which also silently
# armed a hardcoded login backdoor (audit V-03, V-22).
DEBUG = env_bool("DJANGO_DEBUG", False)


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Ephemeral per-process key: usable for local work, useless to an attacker,
        # and it invalidates sessions on restart so it can never be mistaken for a
        # working production configuration.
        from django.core.management.utils import get_random_secret_key

        SECRET_KEY = get_random_secret_key()
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off. "
            "Generate one with: python -c "
            "'from django.core.management.utils import get_random_secret_key as g; print(g())'"
        )


# ---------------------------------------------------------------------------
# Hosts and origins
# ---------------------------------------------------------------------------

def _clean_host(host: str) -> str:
    host = host.strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    # Strip the port, but leave bracketed IPv6 literals intact.
    if not host.startswith("["):
        host = host.split(":", 1)[0]
    if host.startswith("*."):
        host = "." + host[2:]
    return host


ALLOWED_HOSTS = [h for h in (_clean_host(x) for x in env_list("DJANGO_ALLOWED_HOSTS")) if h]
if not ALLOWED_HOSTS:
    if DEBUG:
        ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
    else:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must list at least one host when DJANGO_DEBUG is off."
        )

# CORS is an explicit allowlist. It used to be CORS_ALLOW_ALL_ORIGINS = True,
# which let any site on the internet call the API (audit V-22).
CORS_ALLOWED_ORIGINS = env_list("DJANGO_CORS_ALLOWED_ORIGINS")
CORS_ALLOWED_ORIGIN_REGEXES = env_list("DJANGO_CORS_ALLOWED_ORIGIN_REGEXES")
CORS_ALLOW_CREDENTIALS = True
if not CORS_ALLOWED_ORIGINS and not CORS_ALLOWED_ORIGIN_REGEXES:
    if DEBUG:
        CORS_ALLOWED_ORIGINS = [
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:5173",
        ]
    else:
        raise ImproperlyConfigured(
            "DJANGO_CORS_ALLOWED_ORIGINS must be set when DJANGO_DEBUG is off. "
            "List the exact frontend origins, e.g. https://app.dayflow.com"
        )

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", CORS_ALLOWED_ORIGINS)

# The Electron desktop build loads from file:// and therefore sends Origin: null.
# Allowing it is opt-in because it widens CORS to any local HTML file.
if env_bool("DJANGO_ALLOW_DESKTOP_ORIGIN", False):
    CORS_ALLOWED_ORIGINS = list(CORS_ALLOWED_ORIGINS) + ["null"]


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "organizations",
    "accounts",
    "attendance",
    "leave",
    "dashboard",
    "payroll",
    "realtime",
]

AUTH_USER_MODEL = "accounts.CustomUser"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Postgres is the only supported production database. SQLite must be opted into
# explicitly so a missing DATABASE_URL can never quietly downgrade production to
# a local file (audit V-13).

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ALLOW_SQLITE = env_bool("DJANGO_ALLOW_SQLITE", False)

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=env_int("DJANGO_DB_CONN_MAX_AGE", 600),
            conn_health_checks=True,
            ssl_require=env_bool("DJANGO_DB_SSL_REQUIRE", not DEBUG),
        )
    }
elif all(os.getenv(k) for k in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST")):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": env_int("DJANGO_DB_CONN_MAX_AGE", 600),
        }
    }
elif DEBUG or ALLOW_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    raise ImproperlyConfigured(
        "No database configured. Set DATABASE_URL (recommended) or DB_NAME/DB_USER/"
        "DB_PASSWORD/DB_HOST. Set DJANGO_ALLOW_SQLITE=true only for local work."
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Realtime
# ---------------------------------------------------------------------------
# InMemoryChannelLayer only works in a single process: with more than one worker
# some clients silently stop receiving updates (audit V-22).

REDIS_URL = os.getenv("REDIS_URL", "").strip()
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
elif DEBUG or env_bool("DJANGO_ALLOW_INMEMORY_CHANNELS", False):
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
else:
    raise ImproperlyConfigured(
        "REDIS_URL must be set when DJANGO_DEBUG is off; the in-memory channel layer "
        "cannot work across processes. Set DJANGO_ALLOW_INMEMORY_CHANNELS=true only if "
        "you are certain you run exactly one worker."
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": env_int("DJANGO_PASSWORD_MIN_LENGTH", 10)},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# REST framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.authentication.DayFlowJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "PAGE_SIZE": env_int("DJANGO_PAGE_SIZE", 50),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "login": os.getenv("DJANGO_THROTTLE_LOGIN", "10/min"),
        "signup": os.getenv("DJANGO_THROTTLE_SIGNUP", "5/hour"),
        "password_reset": os.getenv("DJANGO_THROTTLE_PASSWORD_RESET", "5/hour"),
        "billing": os.getenv("DJANGO_THROTTLE_BILLING", "30/min"),
        "export": os.getenv("DJANGO_THROTTLE_EXPORT", "10/hour"),
    },
    "EXCEPTION_HANDLER": "core.exceptions.exception_handler",
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
}

SIMPLE_JWT = {
    # Was 1 day. Short-lived access tokens limit the blast radius of a leaked token.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("DJANGO_ACCESS_TOKEN_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("DJANGO_REFRESH_TOKEN_DAYS", 7)),
    # Rotation + blacklisting is what makes logout actually revoke a session (audit V-23).
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "SIGNING_KEY": os.getenv("DJANGO_JWT_SIGNING_KEY", SECRET_KEY),
}


# ---------------------------------------------------------------------------
# Billing (Stripe)
# ---------------------------------------------------------------------------

BILLING_CURRENCY = os.getenv("BILLING_CURRENCY", "usd").lower()
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_API_VERSION = os.getenv("STRIPE_API_VERSION", "2025-10-29.clover")
BILLING_SUCCESS_URL = os.getenv("BILLING_SUCCESS_URL", "http://localhost:8080/#/billing/success")
BILLING_CANCEL_URL = os.getenv("BILLING_CANCEL_URL", "http://localhost:8080/#/billing/cancelled")
BILLING_TRIAL_DAYS = env_int("BILLING_TRIAL_DAYS", 14)
# When Stripe is unconfigured the billing app runs in a clearly-labelled stub mode
# so the rest of the product is developable. It refuses to start in production.
BILLING_ENABLED = bool(STRIPE_SECRET_KEY)
if not BILLING_ENABLED and not DEBUG and not env_bool("DJANGO_ALLOW_UNCONFIGURED_BILLING", False):
    raise ImproperlyConfigured(
        "STRIPE_SECRET_KEY must be set when DJANGO_DEBUG is off. Set "
        "DJANGO_ALLOW_UNCONFIGURED_BILLING=true to run without billing deliberately."
    )


# Razorpay: DEPRECATED, replaced by the Stripe billing app. Retained only so the
# existing INR checkout keeps working until that lands. The previous values were
# live API keys committed in plaintext (audit V-34) and must be rotated.
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "DayFlow <no-reply@dayflow.app>")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:8080")
PASSWORD_RESET_TIMEOUT = env_int("DJANGO_PASSWORD_RESET_TIMEOUT", 60 * 60)  # seconds


# ---------------------------------------------------------------------------
# Transport security
# ---------------------------------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Render, Heroku and most PaaS proxies terminate TLS upstream.
    if env_bool("DJANGO_BEHIND_TLS_PROXY", True):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# ---------------------------------------------------------------------------
# I18N / static
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "DEBUG" if DEBUG else "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "dayflow.audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "dayflow.billing": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "dayflow.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
