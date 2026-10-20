import threading
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection

from core import ratelimit
from core.models import RateLimit

NOW = datetime(2026, 11, 2, 9, 0, 30, tzinfo=UTC)
IP = "203.0.113.7"


@pytest.mark.django_db
def test_allows_up_to_limit_then_refuses():
    results = [ratelimit.hit("signin", IP, limit=3, window_seconds=60, now=NOW) for _ in range(4)]

    assert results == [True, True, True, False]


@pytest.mark.django_db
def test_new_window_resets_count():
    for _ in range(3):
        ratelimit.hit("signin", IP, limit=2, window_seconds=60, now=NOW)
    assert not ratelimit.hit("signin", IP, limit=2, window_seconds=60, now=NOW)

    next_window = NOW + timedelta(seconds=60)
    assert ratelimit.hit("signin", IP, limit=2, window_seconds=60, now=next_window)
    assert RateLimit.objects.get().count == 1


@pytest.mark.django_db
def test_window_is_floored_to_epoch_multiple():
    ratelimit.hit("signin", IP, limit=1, window_seconds=60, now=NOW)

    assert RateLimit.objects.get().window_start == datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    # 59 seconds later is still the same window.
    later = datetime(2026, 11, 2, 9, 0, 59, tzinfo=UTC)
    assert not ratelimit.hit("signin", IP, limit=1, window_seconds=60, now=later)


@pytest.mark.django_db
def test_scopes_and_idents_are_independent():
    assert ratelimit.hit("signin", IP, limit=1, window_seconds=60, now=NOW)
    assert not ratelimit.hit("signin", IP, limit=1, window_seconds=60, now=NOW)

    assert ratelimit.hit("booking", IP, limit=1, window_seconds=60, now=NOW)
    assert ratelimit.hit("signin", "198.51.100.9", limit=1, window_seconds=60, now=NOW)
    assert RateLimit.objects.count() == 3


@pytest.mark.django_db
def test_stored_key_never_contains_raw_ident():
    email = "juan.delacruz@example.com"
    ratelimit.hit("signin", IP, limit=5, window_seconds=60, now=NOW)
    ratelimit.hit("signin-email", email, limit=5, window_seconds=60, now=NOW)

    keys = list(RateLimit.objects.values_list("key", flat=True))
    assert len(keys) == 2
    for key in keys:
        assert IP not in key
        assert email not in key
        assert "juan" not in key
        scope, digest = key.split(":")
        assert scope in {"signin", "signin-email"}
        assert len(digest) == 40


@pytest.mark.django_db
def test_prune_deletes_old_rows():
    old = NOW - timedelta(days=2)
    ratelimit.hit("signin", "old-ident", limit=5, window_seconds=60, now=old)
    ratelimit.hit("signin", "new-ident", limit=5, window_seconds=60, now=NOW)

    assert ratelimit.prune(now=NOW) == 1
    assert RateLimit.objects.count() == 1
    assert ratelimit.prune(now=NOW) == 0


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_hits_allow_exactly_limit():
    threads_n, limit = 10, 5
    barrier = threading.Barrier(threads_n)
    results: list[bool] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        try:
            barrier.wait()
            allowed = ratelimit.hit("signin", IP, limit=limit, window_seconds=60, now=NOW)
            with lock:
                results.append(allowed)
        except BaseException as exc:  # surfaced in the main thread below
            with lock:
                errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(threads_n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(results) == threads_n
    assert results.count(True) == limit
    assert RateLimit.objects.get().count == threads_n
