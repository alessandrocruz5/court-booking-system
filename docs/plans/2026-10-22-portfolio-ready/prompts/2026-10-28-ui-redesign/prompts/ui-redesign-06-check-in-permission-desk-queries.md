---
type: prompt
plan: "[[2026-10-28-ui-redesign]]"
id: 06
unit: CBS-18
status: todo
model: opus
effort: high
depends_on: [05]
parallel_group: B
files:
  create:
    - apps/backend/dashboard/desk.py
    - apps/backend/dashboard/tests/test_desk_queries.py
  modify:
    - apps/backend/accounts/roles.py
    - apps/backend/accounts/tests/test_access.py
    - apps/backend/dashboard/queries.py
  delete: []
---
# 06 · can_check_in, desk queries, derived statuses

## Task
1. Add `roles.can_check_in(role, booking, *, now)`.
2. Add `dashboard/desk.py` with the Front desk's read models.
3. Make `queries.py` aware of "Checked in" and "Completed".

## Context
- `accounts/**` is **high-stakes**. Permissions are checked on the server; templates only reflect them.
- `can_check_in` mirrors `can_cancel`:
  - The owner: whenever `checkin.check_in` would succeed.
  - The viewer: only when `booking.is_demo or booking.source != Source.ONLINE`, and never a real visitor's online booking.
  - `now` is required.
- `desk.py` (all masking goes through the existing `queries.name_for`, `mask_email` and `mask_mobile`):
  - `normalise_query(text) -> str`: trim and uppercase. Add `KC-` when there's no `-` and the text looks like 6 Crockford characters. Reject `\x00` (return "").
  - `lookup(role, text, now) -> DeskResult | None`: an exact reference match.
    - `DeskResult` carries: reference, status_label, pill class, masked name and contact, amount, court label, sport label, time label, `warning: str | None`, `can_check_in`, `checked_in_clock`, schedule day.
    - The warning copy and precedence follow the spec's Front desk section.
  - `suggest(role, text, now, limit=5)`: reference `icontains` or a name `icontains`. Name search is **owner only**: the viewer sees masked names, so a name search would leak them. Blocks are excluded.
  - `arriving(role, now, within_hours=3)`, `on_court(role, now)`, `stats(now)`.
    - Stats: bookings today, walk-ins today, revenue today (confirmed and paid plus walk-ins), spaces in use now out of the venue's space count (reuse the overview's count), and active holds.
- `queries.py`:
  - Add `checked_in` and `completed` to `STATUS_CHOICES` as **derived filters**:
    - `checked_in` = confirmed with `checked_in_at` set
    - `completed` = confirmed with `ends_at <= now`
    - plain `confirmed` excludes both
  - `_row` and `get_booking` expose `status_key` (`confirmed | checked_in | completed | pending | cancelled | needs_refund | expired | block`) and `checked_in_clock`.
  - Keep the masking where it is. Thread `now` the way 2026-10-21 prompt 04 did.
- Tests:
  - `test_access.py`: the `can_check_in` matrix.
  - `test_desk_queries.py`: normalising, viewer masking, viewer name search returning nothing, each warning, the arriving window and its LATE/NEXT tags, the derived status filters.
  - Pin `now` like the existing `pinned_clock`.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/portfolio/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
cd apps/backend && uv run pytest accounts dashboard -q
```
