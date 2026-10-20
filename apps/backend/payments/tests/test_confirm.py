import logging
import threading
import time
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from django.db import connection, transaction

from bookings import holds, rules
from bookings.holds import Customer
from bookings.models import Booking, Court, SlotLock
from bookings.rules import Status
from payments import confirm
from payments.confirm import (
    CheckResult,
    ConfirmResult,
    check_checkout,
    confirm_payment,
    log_error,
    release_checkout,
)
from payments.env import PaymentsConfigError
from payments.paymongo import CheckoutSession, Payment, PayMongoError

# Monday 2 November 2026, 10:00 in Manila; the slots are tomorrow at 12:00.
NOW = datetime(2026, 11, 2, 10, tzinfo=rules.TIME_ZONE)
TOMORROW = date(2026, 11, 3)
LAPSED = NOW + timedelta(minutes=rules.HOLD_MINUTES)
PAID_AT = datetime(2026, 11, 2, 2, 5, tzinfo=UTC)
SESSION_ID = "cs_test1"
CUSTOMER = Customer(
    name="Juan Dela Cruz", email="juan.delacruz@example.com", mobile="+639000000001"
)
PII = (CUSTOMER.name, CUSTOMER.email, CUSTOMER.mobile, "juan")


def hold(code: str = "tn-1", *, session_id: str | None = SESSION_ID, now=NOW) -> Booking:
    booking = holds.create_hold(
        court=Court.objects.get(code=code),
        sport="tennis",
        coverage="full",
        day=TOMORROW,
        start_hour=12,
        hours=1,
        customer=CUSTOMER,
        now=now,
    )
    if session_id is not None:
        Booking.objects.filter(pk=booking.pk).update(checkout_session_id=session_id)
        booking.refresh_from_db()
    return booking


def paid(booking: Booking, **changes) -> Payment:
    payment = Payment(
        id="pay_test1",
        status="paid",
        amount_centavos=booking.price_centavos,
        currency="PHP",
        fee_centavos=1_250,
        net_centavos=booking.price_centavos - 1_250,
        method="gcash",
        paid_at=PAID_AT,
        livemode=False,
    )
    return replace(payment, **changes)


def session(booking: Booking, *payments: Payment, **changes) -> CheckoutSession:
    result = CheckoutSession(
        id=booking.checkout_session_id or SESSION_ID,
        checkout_url=f"https://checkout.paymongo.com/{SESSION_ID}",
        status="active",
        livemode=False,
        metadata={"booking_id": str(booking.id)},
        payments=payments if payments else (paid(booking),),
    )
    return replace(result, **changes)


def lock_keys(booking: Booking) -> set[tuple[str, int]]:
    return {
        (space, starts_at.astimezone(rules.TIME_ZONE).hour)
        for space, starts_at in SlotLock.objects.filter(booking=booking).values_list(
            "space", "starts_at"
        )
    }


def lock_ids(booking: Booking) -> set[int]:
    return set(SlotLock.objects.filter(booking=booking).values_list("pk", flat=True))


def assert_no_pii(text: str) -> None:
    for value in PII:
        assert value not in text


def mock_client(monkeypatch) -> tuple[MagicMock, MagicMock]:
    """Replace `get_client` with a mock usable as `with get_client() as client:`."""
    factory = MagicMock(name="get_client")
    client = factory.return_value.__enter__.return_value
    monkeypatch.setattr(confirm, "get_client", factory)
    return factory, client


# confirm_payment


@pytest.mark.django_db
def test_paid_session_confirms_and_records_the_payment(caplog):
    caplog.set_level(logging.INFO, logger="cb.payments")
    booking = hold()

    result = confirm_payment(session(booking), now=NOW)

    assert result.status == "confirmed"
    assert result.reason is None
    booking.refresh_from_db()
    assert result.booking.pk == booking.pk
    assert booking.status == Status.CONFIRMED
    assert booking.hold_expires_at is None
    assert (booking.payment_id, booking.payment_method) == ("pay_test1", "gcash")
    assert (booking.fee_centavos, booking.net_centavos) == (1_250, booking.price_centavos - 1_250)
    assert booking.paid_at == PAID_AT
    assert lock_keys(booking) == {("F", 12)}
    assert f"payment.confirmed ref={booking.reference}" in caplog.text
    assert_no_pii(caplog.text)


@pytest.mark.django_db
def test_paid_at_defaults_to_now():
    booking = hold()
    result = confirm_payment(session(booking, paid(booking, paid_at=None)), now=NOW)
    assert result.status == "confirmed"
    booking.refresh_from_db()
    assert booking.paid_at == NOW


@pytest.mark.django_db
def test_confirming_twice_writes_once():
    booking = hold()
    paid_session = session(booking)

    assert confirm_payment(paid_session, now=NOW).status == "confirmed"
    booking.refresh_from_db()
    first_write = booking.updated_at

    again = confirm_payment(paid_session, now=NOW)
    assert again.status == "confirmed"
    booking.refresh_from_db()
    assert booking.updated_at == first_write
    assert booking.status == Status.CONFIRMED


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("make", "reason"),
    [
        (lambda b: session(b, paid(b, amount_centavos=b.price_centavos + 1)), "amount_mismatch"),
        (lambda b: session(b, paid(b, amount_centavos=b.price_centavos - 1)), "amount_mismatch"),
        (lambda b: session(b, paid(b, currency="USD")), "amount_mismatch"),
        (lambda b: session(b, metadata={"booking_id": str(uuid.uuid4())}), "metadata_mismatch"),
        (lambda b: session(b, metadata={}), "metadata_mismatch"),
        (lambda b: session(b, livemode=True), "livemode"),
        (lambda b: session(b, paid(b, livemode=True)), "livemode"),
        (lambda b: session(b, id="cs_unknown"), "unknown_session"),
    ],
)
def test_rejections_change_nothing(make, reason, caplog):
    caplog.set_level(logging.INFO, logger="cb.payments")
    booking = hold()
    before = booking.updated_at

    result = confirm_payment(make(booking), now=NOW)

    assert result == ConfirmResult("rejected", reason=reason)
    booking.refresh_from_db()
    assert booking.status == Status.PENDING
    assert booking.updated_at == before
    assert booking.payment_id == ""
    (record,) = [r for r in caplog.records if r.getMessage().startswith("payment.rejected ")]
    if reason in ("amount_mismatch", "metadata_mismatch"):
        # Our booking's session holds a paid payment: an error with the payment ID, for a refund.
        assert record.levelno == logging.ERROR
        assert record.getMessage().endswith(f"reason={reason} payment=pay_test1")
    else:
        # An unknown or live session isn't ours to refund (the PayMongo account is shared).
        assert record.levelno == logging.WARNING
        assert record.getMessage().endswith(f"reason={reason}")
    assert_no_pii(caplog.text)


@pytest.mark.django_db
def test_rejection_without_a_paid_payment_is_a_warning(caplog):
    caplog.set_level(logging.INFO, logger="cb.payments")
    booking = hold()
    unpaid = session(booking, paid(booking, status="pending"), id="cs_unknown")

    assert confirm_payment(unpaid, now=NOW) == ConfirmResult("rejected", reason="unknown_session")
    (record,) = [r for r in caplog.records if r.getMessage().startswith("payment.rejected ")]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "payment.rejected session=cs_unknown reason=unknown_session"


@pytest.mark.django_db
@pytest.mark.parametrize("payment_status", ["pending", "failed", None])
def test_no_paid_payment_is_pending(payment_status):
    booking = hold()
    payments = () if payment_status is None else (paid(booking, status=payment_status),)
    paid_session = replace(session(booking), payments=payments)

    result = confirm_payment(paid_session, now=NOW)

    assert result.status == "pending"
    assert result.booking.pk == booking.pk
    booking.refresh_from_db()
    assert booking.status == Status.PENDING


@pytest.mark.django_db
def test_payment_made_in_time_but_delivered_after_the_hold_lapsed_keeps_its_locks():
    # A webhook retry: paid at 10:05, delivered after the hold lapsed at 10:20, nightly not run.
    booking = hold()
    before = lock_ids(booking)
    assert PAID_AT <= booking.hold_expires_at <= LAPSED

    assert confirm_payment(session(booking), now=LAPSED).status == "confirmed"
    booking.refresh_from_db()
    assert booking.status == Status.CONFIRMED
    assert lock_keys(booking) == {("F", 12)}
    # Kept, not dropped and re-claimed.
    assert lock_ids(booking) == before


@pytest.mark.django_db
def test_pending_hold_paid_after_it_lapsed_once_the_slot_started_needs_refund():
    booking = hold()
    late = paid(booking, paid_at=booking.hold_expires_at + timedelta(minutes=1))

    result = confirm_payment(session(booking, late), now=booking.starts_at)

    assert result.status == "needs_refund"
    booking.refresh_from_db()
    assert booking.status == Status.NEEDS_REFUND
    assert booking.payment_id == "pay_test1"
    assert lock_keys(booking) == set()


@pytest.mark.django_db
def test_pending_hold_paid_in_time_is_confirmed_even_once_the_slot_started():
    booking = hold()
    in_time = paid(booking, paid_at=booking.hold_expires_at - timedelta(minutes=1))

    result = confirm_payment(session(booking, in_time), now=booking.ends_at + timedelta(hours=1))

    assert result.status == "confirmed"
    booking.refresh_from_db()
    assert booking.status == Status.CONFIRMED
    assert lock_keys(booking) == {("F", 12)}


@pytest.mark.django_db
def test_pending_hold_paid_after_it_lapsed_is_reacquired_while_the_slot_is_free():
    booking = hold()
    before = lock_ids(booking)
    late = paid(booking, paid_at=booking.hold_expires_at + timedelta(minutes=1))

    result = confirm_payment(session(booking, late), now=LAPSED + timedelta(minutes=1))

    assert result.status == "confirmed"
    booking.refresh_from_db()
    assert booking.status == Status.CONFIRMED
    assert booking.hold_expires_at is None
    assert lock_keys(booking) == {("F", 12)}
    # Re-claimed: the old locks were dropped and inserted again.
    assert lock_ids(booking).isdisjoint(before)


@pytest.mark.django_db
def test_expired_hold_with_free_slots_is_reacquired_and_confirmed():
    booking = hold()
    assert holds.expire_stale_holds(now=LAPSED) == 1
    assert lock_keys(booking) == set()

    result = confirm_payment(session(booking), now=LAPSED)

    assert result.status == "confirmed"
    booking.refresh_from_db()
    assert booking.status == Status.CONFIRMED
    assert booking.hold_expires_at is None
    assert booking.payment_id == "pay_test1"
    assert lock_keys(booking) == {("F", 12)}


@pytest.mark.django_db
def test_expired_hold_whose_slot_was_taken_needs_refund(caplog):
    caplog.set_level(logging.INFO, logger="cb.payments")
    booking = hold()
    holds.expire_stale_holds(now=LAPSED)
    other = hold(session_id=None, now=LAPSED)

    result = confirm_payment(session(booking), now=LAPSED)

    assert result.status == "needs_refund"
    booking.refresh_from_db()
    assert booking.status == Status.NEEDS_REFUND
    # Recorded anyway, so staff can refund it.
    assert (booking.payment_id, booking.fee_centavos, booking.paid_at) == (
        "pay_test1",
        1_250,
        PAID_AT,
    )
    assert lock_keys(booking) == set()
    assert lock_keys(other) == {("F", 12)}
    assert f"payment.needs_refund ref={booking.reference}" in caplog.text
    assert_no_pii(caplog.text)


@pytest.mark.django_db
def test_payment_after_the_slot_started_needs_refund():
    booking = hold()
    holds.expire_stale_holds(now=LAPSED)
    booking.refresh_from_db()

    result = confirm_payment(session(booking), now=booking.starts_at)

    assert result.status == "needs_refund"
    booking.refresh_from_db()
    assert booking.status == Status.NEEDS_REFUND
    assert booking.payment_id == "pay_test1"
    assert SlotLock.objects.count() == 0


@pytest.mark.django_db
def test_pending_hold_without_locks_is_reacquired():
    booking = hold()
    SlotLock.objects.filter(booking=booking).delete()

    assert confirm_payment(session(booking), now=LAPSED).status == "confirmed"
    assert lock_keys(booking) == {("F", 12)}


@pytest.mark.django_db
def test_payment_on_a_cancelled_booking_needs_refund():
    booking = hold()
    holds.release(booking, status="cancelled", now=NOW)

    result = confirm_payment(session(booking), now=NOW)

    assert result.status == "needs_refund"
    booking.refresh_from_db()
    assert booking.status == Status.NEEDS_REFUND
    assert booking.payment_id == "pay_test1"
    assert lock_keys(booking) == set()


@pytest.mark.django_db
def test_needs_refund_is_idempotent():
    booking = hold()
    holds.release(booking, status="cancelled", now=NOW)
    paid_session = session(booking)
    assert confirm_payment(paid_session, now=NOW).status == "needs_refund"
    booking.refresh_from_db()
    first_write = booking.updated_at

    assert confirm_payment(paid_session, now=NOW).status == "needs_refund"
    booking.refresh_from_db()
    assert booking.updated_at == first_write


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_race_two_confirmations_one_write(caplog):
    caplog.set_level(logging.INFO, logger="cb.payments")
    booking = hold()
    paid_session = session(booking)
    barrier = threading.Barrier(2)
    results: list[ConfirmResult] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        try:
            barrier.wait()
            result = confirm_payment(paid_session, now=NOW)
            with lock:
                results.append(result)
        except BaseException as exc:  # surfaced in the main thread below
            with lock:
                errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert [r.status for r in results] == ["confirmed", "confirmed"]
    writes = [r for r in caplog.records if r.getMessage().startswith("payment.confirmed ")]
    assert len(writes) == 1
    booking.refresh_from_db()
    assert booking.status == Status.CONFIRMED
    assert lock_keys(booking) == {("F", 12)}


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_race_second_confirmation_waits_on_the_row_lock(caplog):
    """Deterministic: the other caller is held at the booking's row lock while this one records
    the payment, so it must re-check under the lock and see `confirmed`."""
    caplog.set_level(logging.INFO, logger="cb.payments")
    booking = hold()
    paid_session = session(booking)
    results: list[ConfirmResult] = []
    errors: list[BaseException] = []

    def worker():
        try:
            results.append(confirm_payment(paid_session, now=NOW))
        except BaseException as exc:  # surfaced in the main thread below
            errors.append(exc)
        finally:
            connection.close()

    other = threading.Thread(target=worker)
    with transaction.atomic():
        Booking.objects.select_for_update().get(pk=booking.pk)
        other.start()
        deadline = time.monotonic() + 10
        blocked = False
        with connection.cursor() as cursor:
            while not blocked and time.monotonic() < deadline:
                cursor.execute("select count(*) from pg_locks where not granted")
                blocked = cursor.fetchone()[0] > 0
                if not blocked:
                    time.sleep(0.01)
        mine = confirm_payment(paid_session, now=NOW)
    other.join(timeout=10)

    assert blocked, "the second confirmation never waited on the row lock"
    assert not other.is_alive()
    assert errors == []
    assert mine.status == "confirmed"
    assert [r.status for r in results] == ["confirmed"]
    writes = [r for r in caplog.records if r.getMessage().startswith("payment.confirmed ")]
    assert len(writes) == 1
    booking.refresh_from_db()
    assert booking.status == Status.CONFIRMED
    assert lock_keys(booking) == {("F", 12)}


# check_checkout: it refuses to run inside a transaction, and a plain `django_db` test runs in one,
# so these tests use real transactions.


@pytest.mark.django_db
def test_check_inside_a_transaction_raises_before_calling_paymongo(monkeypatch):
    factory, _ = mock_client(monkeypatch)
    hold()

    with transaction.atomic(), pytest.raises(RuntimeError, match="must not run inside"):
        check_checkout(SESSION_ID)
    factory.assert_not_called()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.parametrize("session_id", [None, "", "bad", "cs_", "cs_x/../y", "cs_unknown"])
def test_check_unknown_or_invalid_id_never_calls_paymongo(monkeypatch, session_id):
    factory, _ = mock_client(monkeypatch)
    hold()

    assert check_checkout(session_id) == CheckResult("not_found")
    factory.assert_not_called()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_check_confirms_through_paymongo(monkeypatch):
    factory, client = mock_client(monkeypatch)
    booking = hold()
    client.retrieve_checkout_session.return_value = session(booking)

    result = check_checkout(SESSION_ID)

    assert result.status == "confirmed"
    assert result.booking.pk == booking.pk
    client.retrieve_checkout_session.assert_called_once_with(SESSION_ID)
    # The client is closed after use.
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_check_unpaid_is_pending(monkeypatch):
    _, client = mock_client(monkeypatch)
    booking = hold()
    client.retrieve_checkout_session.return_value = replace(session(booking), payments=())

    assert check_checkout(SESSION_ID).status == "pending"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.parametrize("final", [Status.CONFIRMED, Status.NEEDS_REFUND])
def test_check_final_status_skips_paymongo(monkeypatch, final):
    factory, _ = mock_client(monkeypatch)
    booking = hold()
    Booking.objects.filter(pk=booking.pk).update(status=final)

    result = check_checkout(SESSION_ID)

    assert result.status == final
    assert result.booking.pk == booking.pk
    factory.assert_not_called()


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_check_rejected_is_not_found(monkeypatch):
    _, client = mock_client(monkeypatch)
    booking = hold()
    client.retrieve_checkout_session.return_value = session(
        booking, metadata={"booking_id": "someone-else"}
    )

    assert check_checkout(SESSION_ID) == CheckResult("not_found")
    booking.refresh_from_db()
    assert booking.status == Status.PENDING


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_check_paymongo_error_is_unavailable(monkeypatch, caplog):
    _, client = mock_client(monkeypatch)
    hold()
    client.retrieve_checkout_session.side_effect = PayMongoError(
        "PayMongo responded 503 juan.delacruz@example.com", 503, ("service_unavailable",)
    )

    assert check_checkout(SESSION_ID) == CheckResult("unavailable")
    assert (
        f"payment.check_failed session={SESSION_ID} error=PayMongoError status=503 "
        "codes=service_unavailable"
    ) in caplog.text
    assert_no_pii(caplog.text)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_check_missing_secret_key_is_unavailable(monkeypatch, caplog):
    monkeypatch.delenv("PAYMONGO_SECRET_KEY", raising=False)
    hold()

    assert check_checkout(SESSION_ID) == CheckResult("unavailable")
    assert "error=PaymentsConfigError key=PAYMONGO_SECRET_KEY" in caplog.text


# release_checkout


@pytest.mark.django_db
def test_release_pending_then_expires_the_session(monkeypatch, django_capture_on_commit_callbacks):
    _, client = mock_client(monkeypatch)
    booking = hold()

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert release_checkout(SESSION_ID) == "released"
        # Not before the release commits.
        client.expire_checkout_session.assert_not_called()

    assert len(callbacks) == 1
    client.expire_checkout_session.assert_called_once_with(SESSION_ID)
    booking.refresh_from_db()
    assert booking.status == Status.CANCELLED
    assert lock_keys(booking) == set()


@pytest.mark.django_db
def test_release_survives_an_expire_failure(
    monkeypatch, django_capture_on_commit_callbacks, caplog
):
    _, client = mock_client(monkeypatch)
    client.expire_checkout_session.side_effect = PayMongoError("PayMongo request failed")
    booking = hold()

    with django_capture_on_commit_callbacks(execute=True):
        assert release_checkout(SESSION_ID) == "released"

    booking.refresh_from_db()
    assert booking.status == Status.CANCELLED
    assert "payment.expire_failed" in caplog.text
    assert "error=PayMongoError status=0" in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (Status.CONFIRMED, "already_paid"),
        (Status.NEEDS_REFUND, "already_paid"),
        (Status.CANCELLED, "released"),
    ],
)
def test_release_of_a_final_booking_changes_nothing(
    monkeypatch, django_capture_on_commit_callbacks, status, outcome
):
    factory, _ = mock_client(monkeypatch)
    booking = hold()
    Booking.objects.filter(pk=booking.pk).update(status=status, hold_expires_at=None)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert release_checkout(SESSION_ID) == outcome

    assert callbacks == []
    factory.assert_not_called()
    booking.refresh_from_db()
    assert booking.status == status


@pytest.mark.django_db
def test_release_of_a_lapsed_hold_still_expires_the_session(
    monkeypatch, django_capture_on_commit_callbacks
):
    # The hold lapsed, but its checkout session could still take a payment.
    _, client = mock_client(monkeypatch)
    booking = hold()
    holds.expire_stale_holds(now=LAPSED)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert release_checkout(SESSION_ID) == "released"
        client.expire_checkout_session.assert_not_called()

    assert len(callbacks) == 1
    client.expire_checkout_session.assert_called_once_with(SESSION_ID)
    booking.refresh_from_db()
    assert booking.status == Status.EXPIRED
    assert lock_keys(booking) == set()


@pytest.mark.django_db
@pytest.mark.parametrize("session_id", [None, "nope", "cs_unknown"])
def test_release_unknown_is_not_found(monkeypatch, session_id):
    factory, _ = mock_client(monkeypatch)
    booking = hold()

    assert release_checkout(session_id) == "not_found"
    factory.assert_not_called()
    booking.refresh_from_db()
    assert booking.status == Status.PENDING


# log_error


def test_log_error_never_logs_the_message(caplog):
    class FakePsycopgError(Exception):
        sqlstate = "23514"

    class FakeDjangoError(Exception):
        pass

    wrapped = FakeDjangoError("Failing row contains (Juan Dela Cruz, juan.delacruz@example.com)")
    wrapped.__cause__ = FakePsycopgError("juan")

    log_error("db.failed", wrapped, ref="KC-ABC123")
    log_error("env.failed", PaymentsConfigError("PAYMONGO_SECRET_KEY", "is missing"))
    log_error("other.failed", ValueError("juan.delacruz@example.com"))

    assert "db.failed ref=KC-ABC123 error=FakeDjangoError sqlstate=23514" in caplog.text
    assert "env.failed error=PaymentsConfigError key=PAYMONGO_SECRET_KEY" in caplog.text
    assert "other.failed error=ValueError" in caplog.text
    assert_no_pii(caplog.text)
    assert all(r.name == "cb.payments" and r.levelno == logging.ERROR for r in caplog.records)
