import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import REQUIRED_RUNTIME_ENV, env_bool, env_list, validate_runtime_env

BACKEND_DIR = Path(__file__).resolve().parents[2]
SENTINEL = "SENTINEL-VALUE-must-never-appear"


def _valid_env(**overrides):
    env = {
        "DJANGO_SECRET_KEY": "s" * 50,
        "DATABASE_URL": "postgres://u:p@localhost:5432/db",
        "ALLOWED_HOSTS": "example.com",
        "CSRF_TRUSTED_ORIGINS": "https://example.com",
        "SITE_URL": "https://example.com",
        "INTERNAL_API_TOKEN": "t" * 32,
    }
    env.update(overrides)
    return env


def test_valid_env_passes():
    validate_runtime_env(_valid_env())


def test_empty_env_names_every_required_key():
    with pytest.raises(ImproperlyConfigured) as excinfo:
        validate_runtime_env({})

    message = str(excinfo.value)
    assert len(REQUIRED_RUNTIME_ENV) == 6
    for name in REQUIRED_RUNTIME_ENV:
        assert name in message


def test_blank_values_count_as_missing():
    with pytest.raises(ImproperlyConfigured, match="SITE_URL"):
        validate_runtime_env(_valid_env(SITE_URL="   "))


@pytest.mark.parametrize(
    ("name", "short_value"),
    [
        ("DJANGO_SECRET_KEY", SENTINEL[:20] + "x" * 29),
        ("INTERNAL_API_TOKEN", SENTINEL[:20] + "x" * 11),
    ],
)
def test_short_secrets_fail_without_leaking_the_value(name, short_value):
    with pytest.raises(ImproperlyConfigured) as excinfo:
        validate_runtime_env(_valid_env(**{name: short_value}))

    message = str(excinfo.value)
    assert name in message
    assert SENTINEL[:20] not in message


def test_message_never_contains_a_value():
    env = {name: SENTINEL for name in REQUIRED_RUNTIME_ENV}
    del env["DATABASE_URL"]

    with pytest.raises(ImproperlyConfigured) as excinfo:
        validate_runtime_env(env)

    message = str(excinfo.value)
    assert "DATABASE_URL" in message
    assert SENTINEL not in message


def test_env_list_trims_and_drops_blanks(monkeypatch):
    monkeypatch.setenv("CB_TEST_LIST", " a.example.com, ,b.example.com ,, ")

    assert env_list("CB_TEST_LIST") == ["a.example.com", "b.example.com"]


def test_env_list_unset_is_empty(monkeypatch):
    monkeypatch.delenv("CB_TEST_LIST", raising=False)

    assert env_list("CB_TEST_LIST") == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", True), ("true", True), ("YES", True), (" on ", True), ("0", False), ("no", False)],
)
def test_env_bool(monkeypatch, raw, expected):
    monkeypatch.setenv("CB_TEST_BOOL", raw)

    assert env_bool("CB_TEST_BOOL") is expected


def test_env_bool_unset_uses_default(monkeypatch):
    monkeypatch.delenv("CB_TEST_BOOL", raising=False)

    assert env_bool("CB_TEST_BOOL") is False
    assert env_bool("CB_TEST_BOOL", default=True) is True


def test_settings_import_with_an_empty_environment():
    """The Docker build runs collectstatic with no env: settings must import and set up."""
    code = (
        "import django, os; "
        "os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'; "
        "django.setup()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env={"PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
