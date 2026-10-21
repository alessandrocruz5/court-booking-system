"""Django settings for the court booking backend (Cloud Run + Neon Postgres).

This module must import with an EMPTY environment: the Docker build runs `collectstatic` with no
variables set. Read env only through `config.env` helpers (they never raise) and never connect to
the database here. Required keys are validated at server start (`config/gunicorn.conf.py`).
"""

from pathlib import Path

import dj_database_url
from django.utils.csp import CSP

from config.env import env_bool, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

# Empty at build time; Django refuses an empty key on first use.
SECRET_KEY = env_str("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
if DEBUG:
    ALLOWED_HOSTS += [host for host in ("localhost", "127.0.0.1") if host not in ALLOWED_HOSTS]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Public storefront origin (Next.js), no trailing slash.
SITE_URL = env_str("SITE_URL").rstrip("/")
# Bearer token the storefront's server sends on /api/v1/*.
INTERNAL_API_TOKEN = env_str("INTERNAL_API_TOKEN")

# No Django admin app: the staff dashboard replaces it (review constraint).
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "accounts",
    "dashboard",
    "bookings",
    "payments",
    "storefront",
]

MIDDLEWARE = [
    # Outermost, so it sees the final response, error pages included.
    "core.middleware.NoStoreMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Redirect only; `@staff_required` on each dashboard view is the access check.
    "accounts.middleware.DashboardLoginRedirectMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
            ],
        },
    },
]

# Neon's pooler is PgBouncer in transaction mode: no persistent connections, no server-side
# cursors, and client-side binding (no `server_side_binding`) so no prepared statements.
# The fallback URL only lets the build import settings; nothing connects at import.
DATABASES = {
    "default": dj_database_url.parse(
        env_str("DATABASE_URL") or "postgres://build:build@127.0.0.1:5432/build",
        conn_max_age=0,
    )
}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Staff sign in with their email as the username; accounts come only from `manage.py seed_staff`.
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LOGIN_URL = "/dashboard/login/"
LOGIN_REDIRECT_URL = "/dashboard/"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Cloud Run terminates TLS and forwards the scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000

SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "object-src": [CSP.NONE],
}

# One stdout handler. Never log request bodies, query strings or personal data; exception text is
# redacted by core.logging.RedactingFormatter (psycopg messages carry row contents).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "redacted": {
            "()": "core.logging.RedactingFormatter",
            "format": "%(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "redacted",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "cb": {"level": "INFO"},
        "django.request": {"level": "ERROR"},
    },
}
