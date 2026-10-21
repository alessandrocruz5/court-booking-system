---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 07
unit: CBS-14
status: done
model: sonnet
effort: medium
depends_on: [06]
parallel_group: C
files:
  create: []
  modify:
    - apps/backend/dashboard/forms.py
    - apps/backend/dashboard/views.py
    - apps/backend/dashboard/templates/dashboard/overview.html
    - apps/backend/dashboard/tests/test_schedule.py
    - apps/backend/dashboard/tests/test_overview.py
  delete: []
---
# 07 · Viewer block reasons; neutral refund alert

## Task
1. The public demo viewer picks a block's note from a fixed list of reasons; it can't type free text that every other
   visitor would then see. The owner's form is unchanged.
2. The overview's refund alert stops claiming a cause: `needs_refund` now also comes from a staff cancel of a paid
   booking.

## Context
- Repo root: `/home/apa/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1.2, Python 3.14, uv). Tests run
  on Postgres at `localhost:54329`.
- Why: a block's note is shown to everyone (`dashboard/queries.py:620-622`, and the schedule panel), and the viewer is
  one shared public account. So free text is a defacement risk on a public portfolio demo (code-guardian N8; the user
  chose preset reasons on 2026-10-21).
- `dashboard/forms.py` `StaffBookingForm`: `note = forms.CharField(max_length=120, required=False)`;
  `__init__(self, *args, court=None, demo_until=None, **kw)`; `for_cell(cls, *, court_code, space, hour, day,
  demo_until=None)`; `clean()` requires a non-blank note for a block ("A block needs a note (for example,
  Maintenance).").
  - Add `BLOCK_REASONS = ("Maintenance", "Resurfacing", "Coaching clinic", "League night", "Private event")`. It must
    include every note in `bookings/demo.py` `BLOCKS` (:72-78).
  - Add a keyword `preset_notes: bool = False` to `__init__` and `for_cell` (passed through). When it's true, replace
    `self.fields["note"]` with `forms.ChoiceField(choices=[("", "—"), *((r, r) for r in BLOCK_REASONS)],
    required=False, label="Reason")`. The server then rejects anything else, and the block-needs-a-note check in
    `clean()` still applies. The template renders fields generically (`schedule.html` form partial), so it needs no
    change.
- `dashboard/views.py`: pass `preset_notes=role == Role.VIEWER` (or `request.staff_role == Role.VIEWER`) where
  `StaffBookingForm.for_cell(...)` is called (`_new_panel`) and where `StaffBookingForm(request.POST, ...)` is built
  (`_create`).
- `dashboard/templates/dashboard/overview.html:15`: "… need a refund (payment arrived after the hold expired)." Make it
  cause-neutral, for example `1 paid booking needs a refund in the PayMongo dashboard (test mode).` with the plural
  form kept. Update `dashboard/tests/test_overview.py:450` to match.
- Tests in `test_schedule.py` (fixtures `viewer`, `owner`, `HX`, `NEW`, `form_data`):
  - The viewer's block with `note="Spray paint"` → form error and no booking. With `note="Maintenance"` → "Booking
    added.", note stored.
  - The viewer's GET of the add form renders a `<select` for the note with the five reasons; the owner's renders a text
    input.
  - The owner's block with free text still works.
  - `set(n for n, *_ in demo.BLOCKS) <= set(forms.BLOCK_REASONS)`.
  - Update any existing viewer test that posts a free-text block note so it uses a listed reason.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Change the model, the migrations or `bookings.holds`.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
! grep -n 'payment arrived after the hold expired' apps/backend/dashboard/templates/dashboard/overview.html
```
- `uv run pytest dashboard -q` passes, including the viewer free-text-rejected case.
