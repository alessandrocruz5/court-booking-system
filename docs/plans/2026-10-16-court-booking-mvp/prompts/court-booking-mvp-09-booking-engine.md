---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 09
unit: CBS-4
status: done
model: opus
effort: xhigh
depends_on: [08]
parallel_group: I
files:
  create:
    - apps/backend/bookings/pricing.py
    - apps/backend/bookings/availability.py
    - apps/backend/bookings/holds.py
    - apps/backend/bookings/references.py
    - apps/backend/bookings/tests/test_rules.py
    - apps/backend/bookings/tests/test_pricing.py
    - apps/backend/bookings/tests/test_availability.py
    - apps/backend/bookings/tests/test_holds.py
  modify:
    - apps/backend/bookings/rules.py
  delete: []
---
# 09 · Rules, pricing, availability and holds

## Task
Implement the booking engine as plain Python services in `apps/backend/bookings`: validation rules, price quotes,
availability, payment holds with lazy expiry, staff bookings, release, and late-payment re-acquisition. The
`SlotLock` unique constraint must be the only thing that decides who gets a slot.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1, Python 3.14, uv;
  tests via `config.settings_test` on Postgres 17 at `localhost:54329`). `docker compose up -d --wait db` first.
- Already there (prompt 07). Read `bookings/models.py` and `bookings/rules.py` first.
  - Models `Court(code, name, kind, sort_order, is_active)` and `Booking`: id, reference, court, sport, coverage, half,
    starts_at, ends_at, hours, source, status, price_centavos, customer_name, customer_email, customer_mobile,
    consent_at, note, hold_expires_at, checkout_session_id, payment fields, is_demo, created_by, timestamps.
  - `SlotLock(booking, court, space, starts_at)` with `UNIQUE(court, space, starts_at)`.
  - Constants: `TIME_ZONE` (Asia/Manila), `OPEN_HOUR=7`, `CLOSE_HOUR=23`, `WINDOW_DAYS=7`, `MAX_HOURS=3`, `HOLD_MINUTES=20`,
    the TextChoices `CourtKind`, `Sport`, `Coverage`, `Half`, `Source` and `Status`, and the maps `SPORTS` and `SPACES`.
- **Add to `rules.py`**. These exact names are imported by later prompts:
  - `class BookingRuleError(Exception)` with a `.code` attribute. Codes: `unknown_sport`, `court_inactive`,
    `wrong_court_for_sport`, `coverage_not_allowed`, `invalid_hours`, `outside_hours`, `outside_window`, `in_the_past`.
  - `def local_today(now: datetime) -> date` (in Asia/Manila).
  - `def bookable_dates(now: datetime) -> list[date]`: today through today + 6, so `WINDOW_DAYS` dates.
  - `def slot_starts(day: date, start_hour: int, hours: int) -> list[datetime]`: aware datetimes in Asia/Manila, one per hour.
  - `def spaces_for(court: Court, coverage: str, half: str | None) -> list[str]`. Basketball full → `["A", "B"]`,
    basketball half → `[half]`, everything else → `["F"]`.
  - `def validate_customer_request(*, court, sport, coverage, day, start_hour, hours, now) -> None`. It raises
    `BookingRuleError` when: the sport isn't in `SPORTS`; the court is inactive; `court.kind` doesn't match the
    sport's `court_kind`; the coverage isn't allowed for the sport (volleyball half is refused); `hours` isn't
    1..`MAX_HOURS`; `start_hour < OPEN_HOUR` or `start_hour + hours > CLOSE_HOUR` (22:00 is the last start); the day
    isn't in `bookable_dates(now)`; or the first slot starts at or before `now`.
  - `def validate_staff_request(*, court, sport, coverage, day, start_hour, hours, now) -> None`. The same sport,
    court and hours rules (sport may be `None` for a block), but the window runs from today to today + 30, and the
    booking only has to **end** after `now` (staff can log a walk-in for the hour in progress).
- **`pricing.py`**: prices are integer centavos per hour as `(off_peak, peak)`, keyed by `(sport, coverage)`:
  - `("basketball","full"): (120_000, 160_000)` and `("basketball","half"): (70_000, 90_000)`
  - `("volleyball","full"): (120_000, 160_000)`
  - `("tennis","full"): (50_000, 70_000)`
  - `("badminton","full"): (35_000, 45_000)` and `("pickleball","full"): (40_000, 50_000)`

  Functions:
  - `PEAK_FROM_HOUR = 17`. `def is_peak(day, hour) -> bool` is true on Saturday or Sunday, or when `hour >= 17`.
  - `def quote(sport, coverage, day, start_hour, hours) -> int` sums the rate for each hour.
  - `def rate_table() -> dict` gives the catalog's rates. The API in a later prompt serializes it.
- **`references.py`**: `def new_reference() -> str` returns `"KC-"` plus 6 characters drawn with `secrets.choice` from the
  Crockford alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ`. Callers retry on a unique clash, up to 5 times.
- **`availability.py`**:
  - `def active_locks_q(now) -> Q`: a booking's locks are active when `status == confirmed`, or when
    `status == pending and hold_expires_at > now`. `needs_refund`, `expired` and `cancelled` bookings have no locks.
  - `@dataclass(frozen=True) StartOption(hour: int, price_centavos: int, peak: bool)` and
    `CourtAvailability(code: str, name: str, starts: list[StartOption])`.
  - `def availability(*, day, sport, coverage, hours, now=None) -> list[CourtAvailability]`. It covers every active court
    of the sport's kind, in `sort_order`. Include a start hour only when all `hours` hours are free for the needed
    spaces (for half coverage, **one** half must be free for the whole span), the span ends by `CLOSE_HOUR`, and the
    start is after `now`. Use one query for the day's active locks, then compute in Python. Validate the inputs with
    the rules above, ignoring the court (raise `BookingRuleError` for a bad sport, coverage, hours or day).
  - `def occupancy(day, *, now=None) -> dict[tuple[int, str, int], Booking]`: (court_id, space, hour) → booking, for the
    staff grid, using active locks only and `select_related("booking", "court")`.
- **`holds.py`**. Exact signatures, which later prompts import:
  ```python
  @dataclass(frozen=True)
  class Customer: name: str; email: str; mobile: str
  class SlotTaken(Exception): ...
  def claim_slots(booking: Booking, spaces: list[str], starts: list[datetime], *, now: datetime) -> None
  def create_hold(*, court, sport, coverage, day, start_hour, hours, customer: Customer, now=None) -> Booking
  def create_staff_booking(*, source: str, court, sport: str | None, coverage: str, half: str | None, day, start_hour,
                           hours, created_by, customer_name: str = "", note: str = "", is_demo: bool = False,
                           now=None) -> Booking
  def release(booking: Booking, *, status: str, now=None) -> bool
  def expire_stale_holds(*, now=None) -> int
  def reacquire(booking: Booking, *, now=None) -> bool
  ```
  - `claim_slots`: it must be called inside `transaction.atomic()`. First, **lazily expire** stale holds on exactly
    those (court, space, starts_at) keys: find the locks whose booking is `pending` with `hold_expires_at <= now`, set
    those bookings to `expired`, and delete **all** their locks. Lock those bookings with `select_for_update().order_by("pk")` first, so two
    claims can't deadlock by locking them in opposite orders. Then `bulk_create` the new locks inside a nested
    `atomic()` (a savepoint). On `IntegrityError`, raise `SlotTaken`. Never check-then-insert without the constraint.
  - `create_hold`: `validate_customer_request`, then quote. Half coverage tries half `A`, then `B`, each in its own
    savepoint. The booking is `source=online`, `status=pending`, `hold_expires_at = now + HOLD_MINUTES`,
    `consent_at = now`, with a fresh reference (retry on a unique clash), the customer fields, `ends_at` and the
    price snapshot. Everything runs in one `transaction.atomic()`. **No external calls in here**: the API calls PayMongo
    after this commits.
  - `create_staff_booking`: `validate_staff_request`, then `status=confirmed`. A walk-in gets
    `price_centavos=quote(...)` and `payment_method="cash"`. A block gets `sport=None`, `price_centavos=0`, a required
    `note`, and coverage full (a block on a basketball court takes both halves).
  - `release`: inside `atomic()`, `select_for_update` the booking. Only `pending` or `confirmed` bookings can be
    released. Delete its locks and set `status` (`cancelled` also sets `cancelled_at`). Return False if the booking was
    already final, which makes the call idempotent.
  - `expire_stale_holds`: bulk-expire every pending booking with `hold_expires_at <= now` and delete their locks.
    Lock them with `select_for_update().order_by("pk")` first, for the same reason.
    Return the count.
  - `reacquire`: for an `expired` online booking, re-claim the **same** court, spaces and starts. Return True on
    success and False on `SlotTaken`. Don't change the status here; the caller (payment confirmation) does.
  - Log `cb.bookings` events with the reference only (e.g. `hold.created`, `hold.expired count=3`), never customer data.
- **Tests** (pytest-django, `django_db`; use a fixed `now`, e.g. a Monday at 10:00 Manila time):
  - `test_rules.py`: every `BookingRuleError` code; the 22:00 start is OK for 1 h and refused for 2 h; day 7 is refused
    and day 6 is OK; a start already passed today is refused; volleyball half and a badminton booking on a tennis
    court are refused; the staff window allows +30 and the hour in progress.
  - `test_pricing.py`: weekday 16:00 is off-peak and 17:00 peak; Saturday 08:00 is peak; a 2 h span across 16–18
    sums one off-peak and one peak hour; every `(sport, coverage)` pair has a rate.
  - `test_availability.py`:
    - Only the sport's courts are listed.
    - A confirmed full basketball booking removes both half and full availability for that hour.
    - Booking half A still leaves half available (B) but not full.
    - An expired pending hold counts as free.
    - Hours that run past 23:00 are omitted.
  - `test_holds.py`:
    - Half bookings go A then B, and a third half is `SlotTaken`.
    - Full after half is `SlotTaken`, and half after full is `SlotTaken`.
    - A stale hold is lazily expired, and its slots go to the new claimer.
    - `release` is idempotent.
    - `reacquire` succeeds when free and returns False when taken.
    - A block on a basketball court locks A and B.
    - **Concurrency**: 8 threads call `create_hold` for the same tennis court and hour, and exactly 1 succeeds while 7
      raise `SlotTaken`. Run it with `django_db(transaction=True, serialized_rollback=True)` (the seeded courts must survive earlier
      transactional tests' flushes) and close each thread's connection in a `finally`.
- Review constraints: **slot integrity**, **no external HTTP inside a DB transaction**, and **personal data stays out of logs**.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Change `models.py` or add migrations. If a constraint seems wrong, stop and report.
- Add views, API or PayMongo code.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run pytest bookings -q -p no:randomly
```
