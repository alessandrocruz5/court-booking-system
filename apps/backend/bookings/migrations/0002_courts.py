"""Seed Kalaro Courts' 18 courts. Must stay in step with `bookings.rules.COURT_COUNTS` (tested)."""

from django.db import migrations

COURTS = [
    *((f"bb-{n}", f"Basketball Court {n}", "basketball", 9 + n) for n in range(1, 3)),
    *((f"tn-{n}", f"Tennis Court {n}", "tennis", 19 + n) for n in range(1, 5)),
    *((f"mp-{n:02d}", f"Court {n}", "multi", 29 + n) for n in range(1, 13)),
]


def create_courts(apps, schema_editor):
    Court = apps.get_model("bookings", "Court")
    Court.objects.bulk_create(
        Court(code=code, name=name, kind=kind, sort_order=sort_order)
        for code, name, kind, sort_order in COURTS
    )


def delete_courts(apps, schema_editor):
    Court = apps.get_model("bookings", "Court")
    Court.objects.filter(code__in=[code for code, *_ in COURTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_courts, delete_courts),
    ]
