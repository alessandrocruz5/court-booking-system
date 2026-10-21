"""`manage.py nightly`: the daily maintenance run of the Cloud Run Job `cb-nightly`.

Steps, each logged with counts only (never row contents) under `cb.nightly`:

1. Expire stale payment holds.
2. Anonymize visitor bookings RETENTION_DAYS after they end (RA 10173; `/privacy` promises it).
3. Prune rate-limit counters whose window has ended (`/privacy` promises within a day).
4. Clear expired sessions.
5. Regenerate the demo bookings, only when ALLOW_DEMO_SEED=1.

A failing step is logged by exception class name and doesn't stop the others; the command exits 1
if any step failed. Every step is safe to repeat, so a job retry re-running all of them is fine.
"""

import logging
import os
from collections.abc import Callable
from datetime import datetime, timedelta

from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from bookings import demo
from bookings.holds import expire_stale_holds
from bookings.models import Booking
from core import ratelimit

logger = logging.getLogger("cb.nightly")

# Must match RETENTION_DAYS in apps/web/src/content/site.ts, which /privacy states.
RETENTION_DAYS = 7
# The longest rate-limit window (storefront WINDOW_SECONDS): only a window still open at run time
# survives to the next run, so every counter is gone within a day and a few minutes.
RATE_LIMIT_MAX_AGE = timedelta(minutes=10)


def anonymize(*, now: datetime) -> int:
    """Strip personal data from non-demo bookings that ended RETENTION_DAYS ago. The financial
    and slot data stay. Demo rows are skipped: they are regenerated instead."""
    return Booking.objects.filter(
        is_demo=False,
        anonymized_at__isnull=True,
        ends_at__lt=now - timedelta(days=RETENTION_DAYS),
    ).update(
        customer_name="",
        customer_email=None,
        customer_mobile=None,
        anonymized_at=now,
        updated_at=now,
    )


def clear_sessions() -> int:
    expired = Session.objects.filter(expire_date__lt=timezone.now()).count()
    call_command("clearsessions")
    return expired


def run(*, now: datetime) -> int:
    """Run every step. Returns the number of steps that failed."""
    steps: list[tuple[str, Callable[[], int]]] = [
        ("expire_holds", lambda: expire_stale_holds(now=now)),
        ("anonymize", lambda: anonymize(now=now)),
        ("prune_ratelimit", lambda: ratelimit.prune(older_than=RATE_LIMIT_MAX_AGE, now=now)),
        ("clear_sessions", clear_sessions),
    ]
    if os.environ.get("ALLOW_DEMO_SEED") == "1":
        steps.append(("reseed_demo", lambda: demo.seed(now=now)))
    else:
        logger.info("nightly.reseed_demo skipped")

    failed = 0
    for name, step in steps:
        try:
            count = step()
        except Exception as exc:  # one failing step must not stop the others
            failed += 1
            # The class name only: a database error's message can quote row contents.
            logger.error("nightly.%s failed error=%s", name, type(exc).__name__)
            # Drop a connection the error may have left unusable, so the next step reconnects.
            # Never inside a transaction (a caller's, or a test's): closing would break it.
            if not connection.in_atomic_block:
                connection.close_if_unusable_or_obsolete()
            continue
        logger.info("nightly.%s count=%d", name, count)
    return failed


class Command(BaseCommand):
    help = "Expire holds, anonymize old visitor data, prune rate limits and sessions, reseed."

    def handle(self, *args, **options):
        failed = run(now=timezone.now())
        if failed:
            raise CommandError(f"nightly: {failed} step(s) failed", returncode=1)
        logger.info("nightly.done")
