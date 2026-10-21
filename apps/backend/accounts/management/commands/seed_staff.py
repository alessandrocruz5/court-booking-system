"""`manage.py seed_staff`: create or update the dashboard's two accounts, `owner` and `viewer`.

There is no sign-up, so this is the only way a staff account exists. Run it from a laptop with
STAFF_OWNER_EMAIL, STAFF_OWNER_PASSWORD, DEMO_VIEWER_EMAIL and DEMO_VIEWER_PASSWORD set. Re-running
it resets both passwords and signs both accounts out everywhere. It prints role names only: the
emails are personal data and the passwords are secrets.
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
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
    help = "Create or update the owner and viewer accounts from env, and sign both out everywhere."

    def handle(self, *args, **options):
        accounts = []
        for role, email_var, password_var in _ACCOUNTS:
            email = _require(email_var).lower()
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
            user_ids = {self._upsert(role, email, password) for role, email, password in accounts}
            signed_out = self._delete_sessions(user_ids)
        roles = ", ".join(role for role, _, _ in accounts)
        self.stdout.write(f"Staff accounts ready: {roles}. Sessions signed out: {signed_out}")

    def _upsert(self, role: Role, email: str, password: str) -> str:
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
        return str(user.pk)

    def _delete_sessions(self, user_ids: set[str]) -> int:
        # Sessions store the user id only inside the signed payload, so decode each one.
        stale = [
            session.pk
            for session in Session.objects.iterator()
            if session.get_decoded().get("_auth_user_id") in user_ids
        ]
        deleted, _ = Session.objects.filter(pk__in=stale).delete()
        return deleted
