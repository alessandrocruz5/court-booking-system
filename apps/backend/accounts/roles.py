"""The staff dashboard's two roles, stored as Django Groups of the same names.

`owner` sees everything. `viewer` is the public demo: personal data masked, and it may cancel only
demo bookings or ones staff made, and only before they end; never a real visitor's online booking.
Neither role has `is_staff` or `is_superuser`, and accounts come only from `manage.py seed_staff`.
Permissions are checked on the server; templates only reflect them.
"""

from datetime import datetime
from enum import StrEnum

from bookings.rules import Source, Status


class Role(StrEnum):
    OWNER = "owner"
    VIEWER = "viewer"


_CANCELLABLE = frozenset({Status.PENDING, Status.CONFIRMED})


def role_of(user) -> Role | None:
    """The user's role, or None for an anonymous or inactive user, or one in no role group. A user
    in both groups is the owner."""
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    names = set(user.groups.filter(name__in=list(Role)).values_list("name", flat=True))
    if Role.OWNER in names:
        return Role.OWNER
    if Role.VIEWER in names:
        return Role.VIEWER
    return None


def can_see_personal_data(role: Role | None) -> bool:
    return role == Role.OWNER


def can_create_staff_booking(role: Role | None) -> bool:
    # Both roles: the demo is meant to be hands-on.
    return role in (Role.OWNER, Role.VIEWER)


def can_cancel(role: Role | None, booking, *, now: datetime) -> bool:
    """Whether `role` may cancel `booking` at `now`. Only a pending or confirmed booking can be
    cancelled; the viewer only when it's demo data or not an online booking, and only while it
    hasn't ended. `now` comes from the caller, so this never reads the clock."""
    if booking.status not in _CANCELLABLE:
        return False
    if role == Role.OWNER:
        return True
    if role == Role.VIEWER:
        return (booking.is_demo or booking.source != Source.ONLINE) and booking.ends_at > now
    return False
