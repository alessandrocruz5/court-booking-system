"""Booking references: "KC-" plus 6 Crockford base32 characters (no I, L, O or U).

The reference column is unique; callers retry on a clash, up to 5 times.
"""

import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
PREFIX = "KC-"
LENGTH = 6


def new_reference() -> str:
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
