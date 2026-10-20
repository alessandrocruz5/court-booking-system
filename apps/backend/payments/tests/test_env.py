import subprocess
import sys
from pathlib import Path

import pytest

from payments.env import PaymentsConfigError, get_secret_key, get_webhook_secret
from payments.paymongo import PayMongoClient

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Short enough not to look like a real key to secret scanners.
SECRET_VALUE = "s3cr3t"

NOT_TEST_KEYS = [
    "sk_live_abc123",
    "pk_test_abc123",
    "pk_live_abc123",
    "sk_test_",
    " sk_test_abc123",
    "sk_test_abc123\n",
    "SK_TEST_abc123",
    "",
    "   ",
]


def test_accepts_a_test_secret_key():
    assert get_secret_key({"PAYMONGO_SECRET_KEY": "sk_test_abc123"}) == "sk_test_abc123"


@pytest.mark.parametrize("key", NOT_TEST_KEYS)
def test_refuses_anything_but_a_test_secret_key(key):
    with pytest.raises(PaymentsConfigError) as excinfo:
        get_secret_key({"PAYMONGO_SECRET_KEY": key})
    assert excinfo.value.key == "PAYMONGO_SECRET_KEY"
    assert "PAYMONGO_SECRET_KEY" in str(excinfo.value)


def test_refuses_a_missing_secret_key():
    with pytest.raises(PaymentsConfigError, match="PAYMONGO_SECRET_KEY"):
        get_secret_key({})


@pytest.mark.parametrize("key", [f"sk_live_{SECRET_VALUE}", f"pk_test_{SECRET_VALUE}"])
def test_never_repeats_the_refused_key(key):
    with pytest.raises(PaymentsConfigError) as excinfo:
        get_secret_key({"PAYMONGO_SECRET_KEY": key})
    assert SECRET_VALUE not in str(excinfo.value)
    assert SECRET_VALUE not in repr(excinfo.value)


def test_reads_the_environment_per_call(monkeypatch):
    monkeypatch.setenv("PAYMONGO_SECRET_KEY", "sk_test_first")
    assert get_secret_key() == "sk_test_first"
    monkeypatch.setenv("PAYMONGO_SECRET_KEY", "sk_test_second")
    assert get_secret_key() == "sk_test_second"


@pytest.mark.parametrize("key", NOT_TEST_KEYS)
def test_client_refuses_anything_but_a_test_key_even_when_passed_directly(key):
    with pytest.raises(ValueError, match="test secret keys"):
        PayMongoClient(key)


def test_client_does_not_repeat_the_key_it_refused():
    with pytest.raises(ValueError) as excinfo:
        PayMongoClient(f"sk_live_{SECRET_VALUE}")
    assert SECRET_VALUE not in str(excinfo.value)


WEBHOOK_SECRET = "whsk_testsecret"


def test_accepts_the_webhooks_secret():
    assert get_webhook_secret({"PAYMONGO_WEBHOOK_SECRET": WEBHOOK_SECRET}) == WEBHOOK_SECRET


def test_webhook_secret_does_not_need_the_api_key():
    get_webhook_secret({"PAYMONGO_WEBHOOK_SECRET": WEBHOOK_SECRET})


@pytest.mark.parametrize(
    "secret",
    ["", "   ", "sk_test_abc123", "pk_test_abc123", "sk_live_abc123", " whsk_x", "whsk_x\n"],
)
def test_refuses_an_api_key_or_blank_as_the_webhook_secret(secret):
    with pytest.raises(PaymentsConfigError) as excinfo:
        get_webhook_secret({"PAYMONGO_WEBHOOK_SECRET": secret})
    assert excinfo.value.key == "PAYMONGO_WEBHOOK_SECRET"


def test_refuses_a_missing_webhook_secret_naming_the_key_but_not_a_value():
    with pytest.raises(PaymentsConfigError, match="PAYMONGO_WEBHOOK_SECRET"):
        get_webhook_secret({})
    with pytest.raises(PaymentsConfigError) as excinfo:
        get_webhook_secret({"PAYMONGO_WEBHOOK_SECRET": f"sk_test_{SECRET_VALUE}"})
    assert SECRET_VALUE not in str(excinfo.value)


def test_payments_modules_import_with_an_empty_environment():
    # The build reads no env: nothing in the app may read a key at import.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); "
            "import payments.env, payments.paymongo, payments.webhook",
        ],
        cwd=BACKEND_DIR,
        env={"DJANGO_SETTINGS_MODULE": "config.settings"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
