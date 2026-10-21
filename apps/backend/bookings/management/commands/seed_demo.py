"""`manage.py seed_demo`: regenerate the demo bookings for today. Real bookings are never touched.

Refuses to run unless ALLOW_DEMO_SEED=1, so it can't reseed a database by accident.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from bookings import demo


class Command(BaseCommand):
    help = "Regenerate the demo bookings (today - 30 to today + 6). Needs ALLOW_DEMO_SEED=1."

    def handle(self, *args, **options):
        if os.environ.get("ALLOW_DEMO_SEED") != "1":
            raise CommandError(
                "Refusing to seed demo data: set ALLOW_DEMO_SEED=1 to allow it.", returncode=2
            )
        count = demo.seed(now=timezone.now())
        self.stdout.write(f"Demo bookings created: {count}")
