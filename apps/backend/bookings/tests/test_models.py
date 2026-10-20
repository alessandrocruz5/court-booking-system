from datetime import datetime, timedelta

import pytest
from django.db import IntegrityError, transaction

from bookings import rules
from bookings.models import Booking, Court, SlotLock
from bookings.rules import Coverage, Half, Source, Sport, Status

START = datetime(2026, 11, 2, 9, tzinfo=rules.TIME_ZONE)
_refs = iter(range(1, 10_000))


def booking_kwargs(court: Court, **overrides) -> dict:
    """A valid confirmed online booking; override fields to break exactly one constraint."""
    kwargs = {
        "reference": f"KC-{next(_refs):06d}",
        "court": court,
        "sport": Sport.TENNIS,
        "coverage": Coverage.FULL,
        "half": None,
        "starts_at": START,
        "ends_at": START + timedelta(hours=1),
        "hours": 1,
        "source": Source.ONLINE,
        "status": Status.CONFIRMED,
        "price_centavos": 50000,
    }
    kwargs.update(overrides)
    return kwargs


@pytest.fixture
def tennis() -> Court:
    return Court.objects.get(code="tn-1")


@pytest.fixture
def basketball() -> Court:
    return Court.objects.get(code="bb-1")


def assert_rejected(**kwargs) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(**kwargs)


@pytest.mark.django_db
def test_courts_migration_seeds_18_courts_matching_rules():
    courts = Court.objects.all()

    assert courts.count() == 18
    assert {kind: courts.filter(kind=kind).count() for kind in rules.COURT_COUNTS} == {
        "basketball": 2,
        "tennis": 4,
        "multi": 12,
    }
    assert sum(rules.COURT_COUNTS.values()) == 18
    for kind, count in rules.COURT_COUNTS.items():
        assert courts.filter(kind=kind).count() == count
    assert list(courts.values_list("code", flat=True)[:3]) == ["bb-1", "bb-2", "tn-1"]
    assert str(Court.objects.get(code="mp-12")) == "Court 12"
    assert all(courts.values_list("is_active", flat=True))


@pytest.mark.django_db
def test_valid_bookings_save(tennis, basketball):
    Booking.objects.create(**booking_kwargs(tennis))
    Booking.objects.create(
        **booking_kwargs(basketball, sport=Sport.BASKETBALL, coverage=Coverage.HALF, half=Half.A)
    )
    Booking.objects.create(
        **booking_kwargs(tennis, source=Source.BLOCK, sport=None, price_centavos=0)
    )
    Booking.objects.create(
        **booking_kwargs(tennis, status=Status.PENDING, hold_expires_at=START - timedelta(hours=1))
    )

    assert Booking.objects.count() == 4


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"hours": 0}, id="hours_below_1"),
        pytest.param({"hours": 4, "ends_at": START + timedelta(hours=4)}, id="hours_above_3"),
        pytest.param({"ends_at": START}, id="ends_equal_starts"),
        pytest.param({"ends_at": START - timedelta(hours=1)}, id="ends_before_starts"),
        pytest.param({"coverage": Coverage.FULL, "half": Half.A}, id="full_with_half"),
        pytest.param({"coverage": Coverage.HALF, "half": None}, id="half_without_half"),
        pytest.param({"coverage": Coverage.HALF, "half": "C"}, id="half_invalid"),
        pytest.param(
            {"source": Source.BLOCK, "sport": Sport.TENNIS, "price_centavos": 0},
            id="block_with_sport",
        ),
        pytest.param(
            {"source": Source.BLOCK, "sport": None, "price_centavos": 100}, id="block_with_price"
        ),
        pytest.param({"source": Source.ONLINE, "sport": None}, id="online_without_sport"),
        pytest.param({"source": Source.WALK_IN, "sport": None}, id="walk_in_without_sport"),
        pytest.param(
            {"status": Status.PENDING, "hold_expires_at": None}, id="pending_without_hold"
        ),
    ],
)
def test_check_constraints_reject_invalid_rows(tennis, overrides):
    assert_rejected(**booking_kwargs(tennis, **overrides))
    assert Booking.objects.count() == 0


@pytest.mark.django_db
def test_slotlock_rejects_same_court_space_hour(tennis):
    first = Booking.objects.create(**booking_kwargs(tennis))
    second = Booking.objects.create(**booking_kwargs(tennis))
    SlotLock.objects.create(booking=first, court=tennis, space="F", starts_at=START)

    with pytest.raises(IntegrityError), transaction.atomic():
        SlotLock.objects.create(booking=second, court=tennis, space="F", starts_at=START)

    assert SlotLock.objects.count() == 1


@pytest.mark.django_db
def test_slotlock_halves_coexist_but_full_conflicts_with_either(basketball):
    half = {"sport": Sport.BASKETBALL, "coverage": Coverage.HALF}
    a = Booking.objects.create(**booking_kwargs(basketball, half=Half.A, **half))
    b = Booking.objects.create(**booking_kwargs(basketball, half=Half.B, **half))
    full = Booking.objects.create(**booking_kwargs(basketball, sport=Sport.VOLLEYBALL))
    SlotLock.objects.create(booking=a, court=basketball, space="A", starts_at=START)
    SlotLock.objects.create(booking=b, court=basketball, space="B", starts_at=START)

    # A full court claims both halves, so it collides with whichever is already locked.
    with pytest.raises(IntegrityError), transaction.atomic():
        SlotLock.objects.create(booking=full, court=basketball, space="A", starts_at=START)

    assert SlotLock.objects.filter(court=basketball, starts_at=START).count() == 2


@pytest.mark.django_db
def test_slotlock_rejects_invalid_space(tennis):
    booking = Booking.objects.create(**booking_kwargs(tennis))

    with pytest.raises(IntegrityError), transaction.atomic():
        SlotLock.objects.create(booking=booking, court=tennis, space="X", starts_at=START)


@pytest.mark.django_db
def test_checkout_session_id_unique_but_nulls_coexist(tennis):
    Booking.objects.create(**booking_kwargs(tennis, checkout_session_id=None))
    Booking.objects.create(**booking_kwargs(tennis, checkout_session_id=None))
    Booking.objects.create(**booking_kwargs(tennis, checkout_session_id="cs_test_1"))

    assert_rejected(**booking_kwargs(tennis, checkout_session_id="cs_test_1"))
    assert Booking.objects.filter(checkout_session_id__isnull=True).count() == 2
