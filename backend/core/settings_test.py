"""Settings for the automated test suite.

Production settings deliberately refuse to start without a secret key, an
allowed-hosts list, a CORS allowlist, Postgres and Redis. Tests should not need
that ceremony, and they must never be able to reach a real database -- so this
module supplies safe local values before importing the real settings.

`manage.py test` selects this module automatically.
"""

import os

os.environ.setdefault("DJANGO_DEBUG", "False")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-not-used-outside-the-test-suite")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,localhost")
os.environ.setdefault("DJANGO_CORS_ALLOWED_ORIGINS", "http://testserver")
os.environ.setdefault("DJANGO_ALLOW_INMEMORY_CHANNELS", "true")
os.environ.setdefault("DJANGO_ALLOW_UNCONFIGURED_BILLING", "true")
os.environ.setdefault("DJANGO_SECURE_SSL_REDIRECT", "false")
os.environ.setdefault("DJANGO_ALLOW_SQLITE", "true")

# Never inherit a real database from the developer's shell or .env file.
os.environ["DATABASE_URL"] = ""
for _var in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST"):
    os.environ[_var] = ""

from core.settings import *  # noqa: E402,F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Fast, deterministic hashing; Argon2 makes the suite an order of magnitude slower.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Throttles are asserted explicitly by the tests that care about them.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {  # noqa: F405
    "login": "1000/min",
    "signup": "1000/min",
    "password_reset": "1000/min",
    "billing": "1000/min",
    "export": "1000/min",
}}

LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"handlers": []}}
