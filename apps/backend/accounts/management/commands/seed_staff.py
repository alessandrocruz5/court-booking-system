"""`manage.py seed_staff`: create or update the dashboard's two accounts, `owner` and `viewer`.

There is no sign-up, so this is the only way a staff account exists. Run it from a laptop with
STAFF_OWNER_EMAIL, STAFF_OWNER_PASSWORD, DEMO_VIEWER_EMAIL and DEMO_VIEWER_PASSWORD set. Re-running
it resets both passwords, deactivates any other member of either role group (an account left behind
by a changed email) and signs everyone out everywhere. It prints role names and counts only: the
emails are personal data and the passwords are secrets.
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from accounts.roles import Role

MIN_PASSWORD_LENGTH = 16

_ACCOUNTS = (
    (Role.OWNER, "STAFF_OWNER_EMAIL", "STAFF_OWNER_PASSWORD"),
    (Role.VIEWER, "DEMO_VIEWER_EMAIL", "DEMO_VIEWER_PASSWORD"),
)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise CommandError(f"{name} is not set.", returncode=2)
    return value


class Command(BaseCommand):
    help = (
        "Create or update the owner and viewer accounts from env, deactivate any other member of "
        "their groups, and sign everyone out everywhere."
    )

    def handle(self, *args, **options):
        accounts = []
        for role, email_var, password_var in _ACCOUNTS:
            email = _require(email_var).lower()
            try:
                validate_email(email)
            except ValidationError:
                # Name the variable, never the value: the email is personal data.
                raise CommandError(
                    f"{email_var} is not a valid email address.", returncode=2
                ) from None
            password = _require(password_var)
            if len(password) < MIN_PASSWORD_LENGTH:
                raise CommandError(
                    f"{password_var} must be at least {MIN_PASSWORD_LENGTH} characters.",
                    returncode=2,
                )
            accounts.append((role, email, password))
        if accounts[0][1] == accounts[1][1]:
            raise CommandError(
                "DEMO_VIEWER_EMAIL must differ from STAFF_OWNER_EMAIL.", returncode=2
            )

        with transaction.atomic():
            seeded = {role: self._upsert(role, email, pw) for role, email, pw in accounts}
            deactivated = self._retire_others(seeded)
            signed_out = self._delete_sessions()
        roles = ", ".join(role for role, _, _ in accounts)
        self.stdout.write(
            f"Staff accounts ready: {roles}. Accounts deactivated: {deactivated}. "
            f"Sessions signed out: {signed_out}"
        )

    def _upsert(self, role: Role, email: str, password: str) -> int:
        group, _ = Group.objects.get_or_create(name=role)
        user, _ = get_user_model().objects.update_or_create(
            username=email,
            defaults={
                "email": email,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )
        user.set_password(password)
        user.save(update_fields=["password"])
        user.groups.set([group])
        return user.pk

    def _retire_others(self, seeded: dict[Role, int]) -> int:
        """Remove everyone but the seeded user from each role group and deactivate them, so an
        account left behind by a changed email stops working. Users are never deleted: bookings
        may reference them (`created_by`). Returns how many accounts were deactivated."""
        retired: set[int] = set()
        for role, user_id in seeded.items():
            group = Group.objects.get(name=role)
            others = list(group.user_set.exclude(pk=user_id).values_list("pk", flat=True))
            group.user_set.remove(*others)
            retired.update(others)
        retired -= set(seeded.values())
        users = get_user_model().objects.filter(pk__in=retired, is_active=True)
        return users.update(is_active=False, is_staff=False, is_superuser=False)

    def _delete_sessions(self) -> int:
        # Delete every session. Decoding them to find the staff ones doesn't work: each session is
        # signed with the server's DJANGO_SECRET_KEY, which differs from the laptop's this runs on,
        # so in production every session would decode to {} and none would be deleted. Only staff
        # use Django sessions on this backend (the storefront calls /api/v1/* with a bearer token,
        # CSRF is cookie-based, and messages are cookie-first and added only by staff views), so
        # this signs out exactly staff.
        # Second line of defence: `set_password` rotates the session auth hash, so a session that
        # somehow survived is still rejected on its next request.
        deleted, _ = Session.objects.all().delete()
        return deleted
