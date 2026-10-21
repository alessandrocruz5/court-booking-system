"""The schedule's add form: a walk-in or a block on one court.

The form only shapes the request; `bookings.holds.create_staff_booking` applies the booking rules
and claims the slots. A `BookingRuleError` it raises maps to a fixed message in `RULE_ERRORS`.
"""

from datetime import date

from django import forms

from bookings.models import Court
from bookings.rules import (
    CLOSE_HOUR,
    MAX_HOURS,
    OPEN_HOUR,
    SPORTS,
    CourtKind,
    Coverage,
    Half,
    Source,
    Sport,
)

from .schedule import VIEWER_DAYS_AHEAD, hour_label

SLOT_TAKEN = "That time was just taken."
DEMO_WINDOW = f"The demo takes bookings up to {VIEWER_DAYS_AHEAD} days ahead."
RULE_ERRORS = {
    "unknown_sport": "Pick a sport played on this court.",
    "wrong_court_for_sport": "That sport isn't played on this court.",
    "coverage_not_allowed": "That sport can't be booked on a half court.",
    "court_inactive": "That court isn't taking bookings.",
    "invalid_hours": f"A booking lasts 1 to {MAX_HOURS} hours.",
    "outside_hours": "A booking has to end by closing time (11 PM).",
    "outside_window": "Staff bookings run from today up to 30 days ahead.",
    "in_the_past": "That time has already passed.",
}
BLOCK_REASONS = ("Maintenance", "Resurfacing", "Coaching clinic", "League night", "Private event")
RULE_ERROR_DEFAULT = "That booking isn't allowed."
DEFAULT_SPORT = {
    CourtKind.BASKETBALL: Sport.BASKETBALL,
    CourtKind.TENNIS: Sport.TENNIS,
    CourtKind.MULTI: Sport.BADMINTON,
}


def sports_for(court: Court | None) -> list[tuple[str, str]]:
    return [
        (sport, Sport(sport).label)
        for sport, rule in SPORTS.items()
        if court is None or rule.court_kind == court.kind
    ]


class StaffBookingForm(forms.Form):
    kind = forms.ChoiceField(
        choices=[(Source.WALK_IN, "Walk-in"), (Source.BLOCK, "Block")],
        widget=forms.RadioSelect,
        initial=Source.WALK_IN,
    )
    court = forms.ModelChoiceField(
        queryset=Court.objects.filter(is_active=True),
        to_field_name="code",
        widget=forms.HiddenInput,
    )
    date = forms.DateField(widget=forms.HiddenInput)
    sport = forms.ChoiceField(choices=Sport.choices, required=False)
    coverage = forms.ChoiceField(
        choices=[(Coverage.FULL, "Full court"), (Coverage.HALF, "Half court")],
        required=False,
        initial=Coverage.FULL,
    )
    half = forms.ChoiceField(
        choices=[("", "—"), (Half.A, "Half A"), (Half.B, "Half B")], required=False
    )
    start_hour = forms.TypedChoiceField(
        coerce=int,
        choices=[(hour, hour_label(hour)) for hour in range(OPEN_HOUR, CLOSE_HOUR)],
        label="Starts",
    )
    hours = forms.TypedChoiceField(
        coerce=int,
        choices=[(n, f"{n} hour{'s' if n > 1 else ''}") for n in range(1, MAX_HOURS + 1)],
        initial=1,
        label="Length",
    )
    customer_name = forms.CharField(max_length=80, required=False, label="Customer name")
    note = forms.CharField(max_length=120, required=False)

    def __init__(
        self,
        *args,
        court: Court | None = None,
        demo_until: date | None = None,
        preset_notes: bool = False,
        **kw,
    ):
        """`court` narrows the sport choices to the court's kind; `demo_until` is the viewer's
        last bookable day (None for the owner); `preset_notes` limits a block's note to
        `BLOCK_REASONS`, since everyone sees it."""
        super().__init__(*args, **kw)
        if preset_notes:
            self.fields["note"] = forms.ChoiceField(
                choices=[("", "—"), *((r, r) for r in BLOCK_REASONS)],
                required=False,
                label="Reason",
            )
        self.demo_until = demo_until
        self.court_obj = court
        self.fields["sport"].choices = sports_for(court)

    @classmethod
    def for_cell(
        cls,
        *,
        court_code: str,
        space: str,
        hour: int,
        day: date,
        demo_until=None,
        preset_notes: bool = False,
    ):
        """An unbound form prefilled for a clicked grid cell, or None for an unknown court."""
        if "\x00" in court_code:  # Postgres refuses a NUL in a string, so it is a miss, not a 500.
            return None
        court = Court.objects.filter(code=court_code, is_active=True).first()
        if court is None:
            return None
        half = space if court.kind == CourtKind.BASKETBALL and space in (Half.A, Half.B) else ""
        initial = {
            "kind": Source.WALK_IN,
            "court": court.code,
            "date": day,
            "sport": DEFAULT_SPORT[court.kind],
            "coverage": Coverage.HALF if half else Coverage.FULL,
            "half": half,
            "start_hour": hour,
            "hours": 1,
        }
        return cls(initial=initial, court=court, demo_until=demo_until, preset_notes=preset_notes)

    @property
    def is_basketball(self) -> bool:
        return self.court_obj is not None and self.court_obj.kind == CourtKind.BASKETBALL

    def clean(self):
        data = super().clean()
        court = data.get("court")
        day = data.get("date")
        if court is not None:
            self.court_obj = court
            self.fields["sport"].choices = sports_for(court)  # For a re-rendered form.
        if day is not None and self.demo_until is not None and day > self.demo_until:
            self.add_error("date", DEMO_WINDOW)

        if data.get("kind") == Source.BLOCK:
            if not data.get("note", "").strip():
                self.add_error("note", "A block needs a note (for example, Maintenance).")
            data.update(sport=None, coverage=Coverage.FULL, half=None, customer_name="")
            return data

        sport = data.get("sport") or None
        data["sport"] = sport
        if sport is None:
            self.add_error("sport", "Pick a sport for the walk-in.")
            return data
        if court is None:
            return data
        if SPORTS[sport].court_kind != court.kind:
            self.add_error("sport", RULE_ERRORS["wrong_court_for_sport"])
            return data
        coverage = data.get("coverage") or Coverage.FULL
        if court.kind != CourtKind.BASKETBALL or Coverage.HALF not in SPORTS[sport].coverages:
            coverage = Coverage.FULL  # Only basketball splits; volleyball is always full court.
        half = data.get("half") or None
        if coverage == Coverage.FULL:
            half = None
        elif half not in (Half.A, Half.B):
            self.add_error("half", "Pick Half A or Half B.")
        data.update(coverage=coverage, half=half)
        return data
