"""PayMongo keys, read per call and never at import: the build runs with no environment variables.

Test mode only: a live key (`sk_live_…`), a public key (`pk_…`) or anything else fails. Errors name
the variable, never its value, because they can end up in the logs.
"""

import os
import re
from collections.abc import Mapping

TEST_SECRET_KEY = re.compile(r"^sk_test_[A-Za-z0-9]+$")

# The webhook's own secret key, from the PayMongo dashboard's webhook page. An API key pasted by
# mistake (`sk_…`, `pk_…`) fails, and so does anything shorter than 24 characters, such as the
# runbook's public `pending` placeholder: with it, anyone could sign a paid event.
WEBHOOK_SECRET = re.compile(r"^(?![sp]k_)\S{24,}$")


class PaymentsConfigError(Exception):
    """A PayMongo variable is missing or invalid. `key` is the variable's name; the value is never
    part of the error."""

    def __init__(self, key: str, problem: str) -> None:
        super().__init__(f"{key} {problem}")
        self.key = key


def _read(environ: Mapping[str, str], key: str, pattern: re.Pattern[str], expected: str) -> str:
    value = environ.get(key)
    if not value:
        raise PaymentsConfigError(key, "is missing or blank")
    # fullmatch, not match: `$` alone also matches before a trailing newline.
    if not pattern.fullmatch(value):
        raise PaymentsConfigError(key, f"must be {expected}")
    return value


def get_secret_key(environ: Mapping[str, str] = os.environ) -> str:
    """`PAYMONGO_SECRET_KEY`, which must be a test secret key (`sk_test_…`)."""
    return _read(
        environ, "PAYMONGO_SECRET_KEY", TEST_SECRET_KEY, "a PayMongo test secret key (sk_test_…)"
    )


def get_webhook_secret(environ: Mapping[str, str] = os.environ) -> str:
    """`PAYMONGO_WEBHOOK_SECRET`, the webhook's signing secret. Separate from the API key so the
    checkout keeps working where no webhook is set up; only the webhook reads it."""
    return _read(
        environ,
        "PAYMONGO_WEBHOOK_SECRET",
        WEBHOOK_SECRET,
        "the PayMongo webhook's secret key (24+ characters), not an API key",
    )
