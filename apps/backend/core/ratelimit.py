"""Fixed-window rate limiting in Postgres, safe across Cloud Run instances.

Each hit is one atomic upsert on `core_ratelimit`, so concurrent requests on any instance count
correctly; Django's cache framework is per-process and isn't atomic across instances. The row key
is the scope plus an HMAC of the identifier: the raw IP or email is never stored (RA 10173).

Database errors propagate: the caller decides whether to fail open or closed. Never log `ident`.
"""

import hmac
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from django.conf import settings
from django.db import connection
from django.utils import timezone

from .models import RateLimit

_HIT_SQL = """
INSERT INTO core_ratelimit (key, window_start, count) VALUES (%s, %s, 1)
ON CONFLICT (key) DO UPDATE SET
  count = CASE WHEN core_ratelimit.window_start = EXCLUDED.window_start
               THEN core_ratelimit.count + 1 ELSE 1 END,
  window_start = EXCLUDED.window_start
RETURNING count
"""


def _key(scope: str, ident: str) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode(), ident.encode(), sha256).hexdigest()[:40]
    return f"{scope}:{digest}"


def _window_start(now: datetime, window_seconds: int) -> datetime:
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % window_seconds, tz=UTC)


def hit(
    scope: str, ident: str, *, limit: int, window_seconds: int, now: datetime | None = None
) -> bool:
    """Count one request for `ident` in `scope`. True if it is within `limit` for this window."""
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    start = _window_start(now or timezone.now(), window_seconds)
    with connection.cursor() as cursor:
        cursor.execute(_HIT_SQL, [_key(scope, ident), start])
        (count,) = cursor.fetchone()
    return count <= limit


def prune(*, older_than: timedelta = timedelta(days=1), now: datetime | None = None) -> int:
    """Delete counters whose window started more than `older_than` ago. Returns the row count."""
    cutoff = (now or timezone.now()) - older_than
    deleted, _ = RateLimit.objects.filter(window_start__lt=cutoff).delete()
    return deleted
