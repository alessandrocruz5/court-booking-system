---
type: prompt
plan: "[[2026-10-16-court-booking-mvp]]"
id: 07
unit: CBS-4
status: todo
model: opus
effort: xhigh
depends_on: [06]
parallel_group: G
files:
  create:
    - apps/backend/bookings/__init__.py
    - apps/backend/bookings/apps.py
    - apps/backend/bookings/models.py
    - apps/backend/bookings/rules.py
    - apps/backend/bookings/migrations/__init__.py
    - apps/backend/bookings/migrations/0001_initial.py
    - apps/backend/bookings/migrations/0002_courts.py
    - apps/backend/bookings/tests/__init__.py
    - apps/backend/bookings/tests/test_models.py
  modify:
    - apps/backend/config/settings.py
  delete: []
---
# 07 · Booking schema and courts

## Task
Create the `bookings` Django app with the `Court`, `Booking` and `SlotLock` models. The database constraints must make
double-booking impossible. Seed the complex's 18 courts in a data migration. Put the rule **constants** in `rules.py`;
prompt 09 adds the functions.

## Context
- Repo root: `/Users/alessandrocruz/Code/court-booking-system`. The backend is `apps/backend`: Django 6.1, Python 3.14,
  uv, settings `config.settings`, tests `config.settings_test` against Postgres 17 (`docker compose up -d --wait db`,
  port 54329). `pnpm --filter @cb/backend test` runs `makemigrations --check` and pytest. `DEFAULT_AUTO_FIELD` is
  `BigAutoField`, `TIME_ZONE` is `Asia/Manila` and `USE_TZ` is on.
- The business: the fictional Kalaro Courts is open daily 07:00–23:00 and takes bookings up to 7 days ahead.
  - 2 basketball courts, bookable **full or half** (halves `A` and `B`). They can also be booked for **volleyball, full
    court only**, and the sport must always be specified.
  - 4 tennis courts.
  - 12 multi-purpose courts, booked for **badminton or pickleball**, with the sport specified.
- **`rules.py`** (constants only in this prompt):
  - `TIME_ZONE = ZoneInfo("Asia/Manila")`, `OPEN_HOUR = 7`, `CLOSE_HOUR = 23`, `WINDOW_DAYS = 7`, `MAX_HOURS = 3`, `HOLD_MINUTES = 20`.
  - `class CourtKind(TextChoices)`: `BASKETBALL = "basketball"`, `TENNIS = "tennis"`, `MULTI = "multi"`.
  - `class Sport(TextChoices)`: `basketball`, `volleyball`, `tennis`, `badminton`, `pickleball`.
  - `class Coverage(TextChoices)`: `full`, `half`. `class Half(TextChoices)`: `A`, `B`.
  - `class Source(TextChoices)`: `online`, `walk_in`, `block`.
  - `class Status(TextChoices)`: `pending`, `confirmed`, `expired`, `cancelled`, `needs_refund`.
  - `SPORTS: dict[str, SportRule]`, where `SportRule` is a frozen dataclass with `court_kind` and `coverages`:
    basketball → (basketball, (full, half)); volleyball → (basketball, (full,)); tennis → (tennis, (full,));
    badminton and pickleball → (multi, (full,)).
  - `SPACES = {"basketball": ("A", "B"), "tennis": ("F",), "multi": ("F",)}`. A full basketball booking takes both A and B.
  - `COURT_COUNTS = {"basketball": 2, "tennis": 4, "multi": 12}`: the seeded courts per kind. The catalog API
    (prompt 12) reads it, so the catalog never queries the DB. A test asserts the migration matches it.
- **`models.py`**:
  - `Court`: `code` (SlugField, max 8, unique), `name` (CharField 40), `kind` (CourtKind), `sort_order`
    (PositiveSmallIntegerField), `is_active` (default True). Ordered by `["sort_order"]`. `__str__` returns the name.
  - `Booking`:
    - `id` (UUIDField pk, default uuid4) and `reference` (CharField 9, unique, e.g. `KC-7KQ2M9`; prompt 09 generates it).
    - `court` (FK Court, PROTECT, related_name `bookings`), `sport` (Sport, **null** only for blocks), `coverage`
      (default full) and `half` (Half, null).
    - `starts_at` and `ends_at` (DateTimeField), `hours` (PositiveSmallIntegerField), `source` (Source) and `status` (Status).
    - `price_centavos` (PositiveIntegerField).
    - `customer_name` (CharField 80, blank, default ""), `customer_email` (EmailField 254, null, blank) and
      `customer_mobile` (CharField 13, null, blank).
    - `consent_at` (null), `note` (CharField 120, blank, default "") and `hold_expires_at` (null).
    - `checkout_session_id` (CharField 64, **unique**, null, blank), `payment_id` (CharField 64, blank, default ""),
      `payment_method` (CharField 20, blank, default ""), `fee_centavos` (PositiveIntegerField, null),
      `net_centavos` (IntegerField, null) and `paid_at` (null).
    - `is_demo` (default False) and `created_by` (FK `settings.AUTH_USER_MODEL`, null, SET_NULL, related_name `+`).
    - `created_at` (auto_now_add), `updated_at` (auto_now), `cancelled_at` (null) and `anonymized_at` (null).
  - `Booking.Meta.constraints`. Django 6 uses `CheckConstraint(condition=…)`, **not** `check=`, so verify against the
    installed Django.
    - `booking_hours_1_to_3`: hours between 1 and 3.
    - `booking_ends_after_starts`: `ends_at > starts_at`.
    - `booking_half_matches_coverage`: `(coverage='full' AND half IS NULL) OR (coverage='half' AND half IN ('A','B'))`.
    - `booking_block_has_no_sport_or_price`: `source <> 'block' OR (sport IS NULL AND price_centavos = 0)`.
    - `booking_non_block_has_sport`: `source = 'block' OR sport IS NOT NULL`.
    - `booking_pending_has_hold`: `status <> 'pending' OR hold_expires_at IS NOT NULL`.
  - `Booking.Meta.indexes`: `(status, hold_expires_at)`, `(starts_at)` and `(court, starts_at)`.
  - `SlotLock`: `booking` (FK Booking, CASCADE, related_name `locks`), `court` (FK Court, PROTECT), `space` (CharField 1,
    choices F/A/B) and `starts_at` (DateTimeField, an hour start). Constraints:
    `UniqueConstraint(fields=["court", "space", "starts_at"], name="slotlock_one_booking_per_space_hour")` and
    `CheckConstraint(condition=Q(space__in=["F", "A", "B"]), name="slotlock_space_valid")`.
    **This unique constraint is the double-booking guarantee.** Every claim inserts one row per space per hour, so a
    full-court booking (A+B) conflicts with either half, and the two halves don't conflict with each other.
- Ruff's `DJ001` flags `null=True` on string fields. Here it's deliberate: keep `null=True` on `sport` and `half`
  (blocks and full courts) and on `customer_email` and `customer_mobile` (anonymization), and mark each one
  `# noqa: DJ001` with that reason. **Never drop `null=True` to satisfy lint.** DJ001 skips `checkout_session_id`,
  because it's unique.
- **Migrations**: `0001_initial` comes from `makemigrations`. `0002_courts` is a `RunPython` data migration, reversible
  (the reverse deletes by code), that creates:
  - `bb-1` and `bb-2` ("Basketball Court 1/2", basketball, sort 10/11)
  - `tn-1`…`tn-4` ("Tennis Court 1…4", tennis, sort 20…23)
  - `mp-01`…`mp-12` ("Court 1…12", multi, sort 30…41)
  Use `apps.get_model`, never a direct import.
- `apps.py`: `BookingsConfig`, `name = "bookings"`, `default_auto_field` inherited. Add `"bookings"` to `INSTALLED_APPS` after `core`.
- `tests/test_models.py`, with `@pytest.mark.django_db`:
  - The courts migration yields 18 courts: 2 basketball, 4 tennis, 12 multi, matching `rules.COURT_COUNTS`.
  - Each CheckConstraint rejects a violating row: wrap the save in `transaction.atomic()` and expect `IntegrityError`.
  - Two `SlotLock`s on the same (court, space, starts_at) raise `IntegrityError`. Same court and hour with spaces A and B
    succeeds. Two `checkout_session_id=None` rows coexist, and two equal non-null IDs fail.
- Review constraints: **slot integrity** (the DB constraint is the guarantee), **migrations are expand/contract and
  never edited once applied**, and **personal data**: the customer fields are nullable so the nightly job can
  anonymize them.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Add services, views or admin registrations. Prompt 09 adds the services; there's no `django.contrib.admin`.
- Add Postgres extensions (no btree_gist) or raw SQL in the schema migration.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /Users/alessandrocruz/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test          # includes makemigrations --check
cd apps/backend && uv run python manage.py sqlmigrate bookings 0001 --settings=config.settings_test | grep -E 'slotlock_one_booking_per_space_hour|booking_half_matches_coverage'
```
