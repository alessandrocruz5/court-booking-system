"""Environment helpers.

Settings must import with an empty environment: the Docker build runs `collectstatic` with no
variables set. So the `env_*` helpers only read, with defaults, and never raise. Required keys
are checked once, when the server starts (`validate_runtime_env`, called from gunicorn's
`on_starting` hook).
"""

import os
from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured

# Every key the service needs at runtime. PayMongo and demo keys are validated where they are used.
REQUIRED_RUNTIME_ENV = (
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "ALLOWED_HOSTS",
    "CSRF_TRUSTED_ORIGINS",
    "SITE_URL",
    "INTERNAL_API_TOKEN",
)

MIN_LENGTHS = {
    "DJANGO_SECRET_KEY": 50,
    "INTERNAL_API_TOKEN": 32,
}

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def env_str(name: str, default: str = "") -> str:
    """The variable's value with surrounding whitespace removed, or `default` when unset."""
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    """True for `1`, `true`, `yes` or `on` (any case). Unset or blank gives `default`."""
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in _TRUTHY


def env_list(name: str) -> list[str]:
    """A comma-separated variable as a list, with items trimmed and blank items dropped."""
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def validate_runtime_env(environ: Mapping[str, str] = os.environ) -> None:
    """Raise `ImproperlyConfigured` naming every missing, blank or too-short key.

    The message holds key names only, never a value, because it ends up in the logs.
    """
    missing = [name for name in REQUIRED_RUNTIME_ENV if not environ.get(name, "").strip()]
    too_short = [
        f"{name} (at least {length} characters)"
        for name, length in MIN_LENGTHS.items()
        if name not in missing and len(environ.get(name, "").strip()) < length
    ]

    problems = []
    if missing:
        problems.append("missing or blank: " + ", ".join(missing))
    if too_short:
        problems.append("too short: " + ", ".join(too_short))
    if problems:
        raise ImproperlyConfigured("Invalid runtime environment; " + "; ".join(problems))
