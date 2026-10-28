"""Staff check-in of a confirmed booking on its day.

The booking is judged on its row re-read under a lock, never on the caller's copy, so a booking
cancelled meanwhile is refused. A checked-in booking stays cancellable (`holds.release` frees it
and leaves `checked_in_at` as it was). Logs carry the booking reference only (RA 10173).
"""

import logging
from datetime import datetime

from django.db import transaction

from bookings.models import Booking
from bookings.rules import TIME_ZONE, Source, Status, local_today

logger = logging.getLogger("cb.bookings")


class CheckInError(Exception):
    """A booking that can't be checked in. `code` is a stable, user-safe identifier:
    `not_confirmed`, `is_block`, `not_today` or `ended`."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def check_in(booking: Booking, *, by, now: datetime) -> bool:
    """Mark `booking` as checked in by staff user `by`. True when it checked in, False when it
    was already checked in (changing nothing); raises `CheckInError` otherwise."""
    with transaction.atomic():
        locked = Booking.objects.select_for_update().get(pk=booking.pk)
        if locked.status != Status.CONFIRMED:
            raise CheckInError("not_confirmed")
        if locked.source == Source.BLOCK:
            raise CheckInError("is_block")
        if locked.checked_in_at is not None:
            return False
        if locked.starts_at.astimezone(TIME_ZONE).date() != local_today(now):
            raise CheckInError("not_today")
        if locked.ends_at <= now:
            raise CheckInError("ended")
        locked.checked_in_at = now
        locked.checked_in_by = by
        locked.save(update_fields=["checked_in_at", "checked_in_by", "updated_at"])
    booking.checked_in_at = locked.checked_in_at
    booking.checked_in_by = locked.checked_in_by
    logger.info("booking.checked_in ref=%s", locked.reference)
    return True
