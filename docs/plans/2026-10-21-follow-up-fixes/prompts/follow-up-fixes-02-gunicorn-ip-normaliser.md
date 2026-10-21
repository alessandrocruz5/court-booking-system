---
type: prompt
plan: "[[2026-10-21-follow-up-fixes]]"
id: 02
unit: U1
status: todo
model: opus
effort: medium
depends_on: [01]
parallel_group: A
files:
  create: []
  modify:
    - apps/backend/config/gunicorn.conf.py
    - apps/backend/core/http.py
    - apps/backend/storefront/views.py
  delete: []
---
# 02 · gunicorn control socket off; one IP normaliser

## Task
1. Turn off gunicorn's control socket.
2. Remove the duplicate IP normaliser: make `core.http._normalise` public as `normalise_ip`, and have
   `storefront.views` use it in place of its own `_client_ip`.

## Context
- Repo root: `/home/apa/Code/court-booking-system`. Backend: `apps/backend` (Django 6.1.2, Python 3.14, uv). Tests run
  on Postgres at `localhost:54329`.
- **gunicorn** 26.2.0 (`uv.lock`) creates a control socket in `~/.gunicorn` by default. The setting
  `control_socket_disable` (since 25.1.0) turns it off. In `config/gunicorn.conf.py`, add
  `control_socket_disable = True` near the other server settings, with a one-line comment (nothing uses `gunicornc`;
  Cloud Run's container doesn't need the socket). Leave the Dockerfile alone: its home directory is harmless.
- **IP normaliser.** `core/http.py:19-30` `_normalise(value) -> str | None` and `storefront/views.py:131-145`
  `_client_ip(value) -> str | None` have identical bodies: a zone ID is invalid, IPv4-mapped IPv6 counts as IPv4, plain
  IPv6 becomes its /64.
  - In `core/http.py`, rename `_normalise` to `normalise_ip`, give it a one-line docstring, update its two uses in
    `client_ip`, and rewrite the module docstring's sentence "The key is normalised like
    `storefront.views._client_ip` …" so it says `storefront.views` uses `normalise_ip` for the IP the web server
    forwards. Keep the RA 10173 line ("never log the result").
  - In `storefront/views.py`, delete `_client_ip`, import `normalise_ip` from `core.http`, and use it at the two call
    sites (`create_booking` ~:236 and `booking_lookup` ~:377). Remove `import ipaddress` if nothing else uses it.
- No test refers to `_client_ip` or `_normalise` by name. These already cover the behaviour and must still pass:
  `accounts/tests/test_access.py` (`test_client_ip`), `storefront/tests/test_bookings_api.py` (zone ID, IPv6 /64,
  invalid IP), and `storefront/tests/test_checkout_api.py:317-344`.
- Review constraint: no personal data in logs. Don't add logging of IPs.

## Do not
- Touch files outside the `files` list. If you must, stop and report why.
- Change the normalisation's behaviour.
- Add dependencies, abstractions or config that aren't listed here.
- Create or switch branches, commit, or push.

## Done when
```bash
cd /home/apa/Code/court-booking-system
docker compose up -d --wait db
pnpm --filter @cb/backend lint
pnpm --filter @cb/backend test
cd apps/backend && uv run python -c "import runpy; assert runpy.run_path('config/gunicorn.conf.py')['control_socket_disable'] is True"
cd /home/apa/Code/court-booking-system && ! grep -rn --include='*.py' -e '_client_ip\b' -e '_normalise\b' apps/backend
docker build -t cb-backend:local apps/backend
```
- The image still starts and fails fast without env, as the CI `images` job checks.
