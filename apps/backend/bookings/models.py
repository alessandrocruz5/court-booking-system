"""Courts, bookings and slot locks.

`SlotLock`'s unique (court, space, starts_at) constraint is the double-booking guarantee: every
claim inserts one row per space per hour, so a full basketball booking (A+B) conflicts with either
half while the two halves never conflict with each other.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from bookings.rules import CourtKind, Coverage, Half, Source, Sport, Status


class Court(models.Model):
    code = models.SlugField(max_length=8, unique=True)
    name = models.CharField(max_length=40)
    kind = models.CharField(max_length=10, choices=CourtKind.choices)
    sort_order = models.PositiveSmallIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.name


class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=9, unique=True)

    court = models.ForeignKey(Court, on_delete=models.PROTECT, related_name="bookings")
    # Null only for staff blocks (enforced by the booking_*_sport check constraints).
    sport = models.CharField(max_length=10, choices=Sport.choices, null=True)  # noqa: DJ001
    coverage = models.CharField(max_length=4, choices=Coverage.choices, default=Coverage.FULL)
    # Null for full-court bookings (booking_half_matches_coverage).
    half = models.CharField(max_length=1, choices=Half.choices, null=True)  # noqa: DJ001

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    hours = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=7, choices=Source.choices)
    status = models.CharField(max_length=12, choices=Status.choices)

    price_centavos = models.PositiveIntegerField()

    customer_name = models.CharField(max_length=80, blank=True, default="")
    # Nullable so the nightly job can anonymize visitor bookings (RA 10173).
    customer_email = models.EmailField(max_length=254, null=True, blank=True)  # noqa: DJ001
    customer_mobile = models.CharField(max_length=13, null=True, blank=True)  # noqa: DJ001

    consent_at = models.DateTimeField(null=True)
    note = models.CharField(max_length=120, blank=True, default="")
    hold_expires_at = models.DateTimeField(null=True)

    checkout_session_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    payment_id = models.CharField(max_length=64, blank=True, default="")
    payment_method = models.CharField(max_length=20, blank=True, default="")
    fee_centavos = models.PositiveIntegerField(null=True)
    net_centavos = models.IntegerField(null=True)
    paid_at = models.DateTimeField(null=True)

    is_demo = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True)
    anonymized_at = models.DateTimeField(null=True)

    class Meta:
        # A CHECK passes when it evaluates to NULL, so nullable columns are tested with IS [NOT]
        # NULL explicitly (`NULL IN ('A','B')` is NULL, not false).
        constraints = [
            models.CheckConstraint(
                condition=Q(hours__gte=1, hours__lte=3), name="booking_hours_1_to_3"
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="booking_ends_after_starts"
            ),
            models.CheckConstraint(
                condition=Q(coverage=Coverage.FULL, half__isnull=True)
                | Q(coverage=Coverage.HALF, half__isnull=False, half__in=[Half.A, Half.B]),
                name="booking_half_matches_coverage",
            ),
            models.CheckConstraint(
                condition=~Q(source=Source.BLOCK) | Q(sport__isnull=True, price_centavos=0),
                name="booking_block_has_no_sport_or_price",
            ),
            models.CheckConstraint(
                condition=Q(source=Source.BLOCK) | Q(sport__isnull=False),
                name="booking_non_block_has_sport",
            ),
            models.CheckConstraint(
                condition=~Q(status=Status.PENDING) | Q(hold_expires_at__isnull=False),
                name="booking_pending_has_hold",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "hold_expires_at"]),
            models.Index(fields=["starts_at"]),
            models.Index(fields=["court", "starts_at"]),
        ]

    def __str__(self) -> str:
        return self.reference


class SlotLock(models.Model):
    class Space(models.TextChoices):
        F = "F", "Full court"
        A = "A", "Half A"
        B = "B", "Half B"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="locks")
    court = models.ForeignKey(Court, on_delete=models.PROTECT)
    space = models.CharField(max_length=1, choices=Space.choices)
    # Start of the locked hour.
    starts_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["court", "space", "starts_at"], name="slotlock_one_booking_per_space_hour"
            ),
            models.CheckConstraint(
                condition=Q(space__in=["F", "A", "B"]), name="slotlock_space_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.court_id}/{self.space}@{self.starts_at.isoformat()}"
