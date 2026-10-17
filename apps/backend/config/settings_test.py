"""Settings for pytest, `makemigrations --check` and `check --deploy` (local and CI).

The database is the Postgres 17 from `compose.yaml` (`docker compose up -d --wait db`); CI points
TEST_DATABASE_URL at its own service.
"""

import os

import dj_database_url

from .settings import *  # noqa: F403
from .settings import DATABASES, STORAGES

# Fixed, test-only key: 64 characters, low entropy on purpose. Never used outside tests.
SECRET_KEY = "testkey-testkey-testkey-testkey-testkey-testkey-testkey-testkey-"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
SECURE_SSL_REDIRECT = False

DATABASES["default"] = dj_database_url.parse(
    os.environ.get("TEST_DATABASE_URL", "postgres://postgres:postgres@localhost:54329/cb"),
    conn_max_age=0,
)
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

INTERNAL_API_TOKEN = "t" * 40
SITE_URL = "http://localhost:3000"
