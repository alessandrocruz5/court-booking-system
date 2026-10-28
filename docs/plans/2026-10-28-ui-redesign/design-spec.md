# Handoff: Kalaro Courts UI redesign (storefront + staff dashboard)

## Overview
A visual and UX redesign of both apps in `alessandrocruz5/court-booking-system`:
- **Storefront** (`apps/web`, Next.js): landing, `/book`, `/book/success`, `/book/cancelled`, `/booking`.
- **Staff dashboard** (`apps/backend/dashboard`, Django + htmx): a new **Front desk** (lookup + check-in), plus restyled Schedule, Bookings and Overview.

It uses the existing palette (ink `#0f172a`, paper `#f8fafc`, court `#16a34a`, clay `#c2410c`, line `#cbd5e1`) and Archivo. It adds sport colour tags and JetBrains Mono for references.

**The implementation plan is in `docs/plans/2026-10-28-ui-redesign/`**, in this repo's `/plan-feature` format. It holds the plan, this spec (`design-spec.md`), the prototypes and the 12 prompts. Copy that folder into the repo, add the row from `docs/plans/_index.row.md` to `docs/plans/_index.md`, then run `/audit-plan` and `/build-unit` as usual.

## About the design files
The files in `prototypes/` are **design references built in HTML**. They show the intended look and behaviour; they are not production code. Rebuild them in each app's own stack:
- `apps/web`: Tailwind v4 `@theme` tokens in `globals.css`, server components, URL-param state (as `/book` does today).
- Dashboard: Django templates, `dashboard.css` classes, htmx partials.

**Don't copy inline styles.** The dashboard tests run `assert_csp_safe`, so every style goes in a stylesheet class.

The prototypes run on fake data with the clock fixed at **Sun 25 Oct 2026, 7:48 PM**. Open them in a browser, or in Claude Design.

## Fidelity
**High fidelity.** Colours, type, spacing, radii and copy are final. Follow them closely, but repo rules win wherever the two conflict (see the next section).

## Where the prototype differs from the repo, and the repo wins
- **"A copy was sent to {email}"** on the confirmation screen: **drop it.** No email or SMS is ever sent (FAQ, `/privacy`).
- **FAQ copy**: keep `apps/web/src/content/site.ts` `FAQ` word for word. The prototype paraphrased some answers. Only the presentation changes (an accordion).
- **References**: walk-ins and blocks show their real `KC-` reference, not `WI-0412` / `BLK-031`.
- **"Completed"** isn't a `Status`. It's derived: `confirmed` with `ends_at <= now`.
- **"Checked in"** doesn't exist yet. Prompts 05–06 add `Booking.checked_in_at`/`checked_in_by` and `can_check_in`.
- **Viewer role**: the prototype shows the owner's view. The viewer still sees masked name, email and mobile (masked in `queries.py`), and still picks block notes from `BLOCK_REASONS` (a `<select>`, not free text).
- **Demo hint** "Try KC-W3PE7U or KC-G1KQGQ" under the desk lookup: viewer role only, filled with two real demo references from today.
- **Court names** come from `Court.name` in the database. Don't hardcode "Court 7".
- **Payment method** comes from `Booking.payment_method`. Don't hardcode "Card".
- **Spaces**: "Courts in use" is out of 20 spaces (4 basketball halves, 4 tennis, 12 multi). Use the existing space count tested in `test_overview.py::test_space_count_matches_the_venue`.
- The test-mode banner text stays exactly **"Fictional venue · Test mode, no real payments"** on every page of both apps.

## Design tokens

### Colours
| Token | Hex | Use |
|---|---|---|
| ink | `#0f172a` | Text, dark cards, primary dark button, banner |
| ink-2 | `#1e293b` | Dark button hover; input bg on dark |
| ink-3 | `#334155` | Borders on dark; strong secondary text |
| slate-600 | `#475569` | Body-muted text |
| slate-500 | `#64748b` | Captions, labels, table headers |
| slate-400 | `#94a3b8` | Disabled text, chevrons |
| line | `#cbd5e1` | Input borders, outline buttons |
| line-soft | `#e2e8f0` | Card borders |
| hair | `#f1f5f9` | Row dividers, segmented-control track |
| paper | `#f8fafc` | Page bg, table header bg |
| white | `#ffffff` | Cards |
| court | `#16a34a` | Primary CTA, selected states, check-in |
| court-dark | `#15803d` | CTA hover, positive text |
| court-soft | `#dcfce7` | Confirmed pill/block bg |
| court-tint | `#f0fdf4` | Selected tile bg, hover on green outline |
| court-ink | `#14532d` / `#166534` | Text on court-soft (block / pill) |
| clay | `#c2410c` | Eyebrows, peak prices, LATE tag, now line |
| clay-light | `#fb923c` | Eyebrow on dark |
| warn-bg / warn-line / warn-ink | `#fff7ed` / `#fed7aa` / `#9a3412` | Warnings, not-found, form errors |
| pending | `#ea580c` (border) / `#ffedd5` (pill bg) | Payment pending |
| danger-bg / danger-ink | `#fee2e2` / `#991b1b` | Cancelled |
| focus ring | `#16a34a55` | `outline: 3px solid; outline-offset: 1px` |

### Sport tags
Each sport gets a 8–10px rounded square (radius 2–3px) or a 22×4px bar on the sport tile.

| Sport | Hex |
|---|---|
| basketball | `#e0662d` |
| volleyball | `#d4a017` |
| tennis | `#5b9a1e` |
| badminton | `#2b7fc4` |
| pickleball | `#14958a` |
| block | `#94a3b8` |

### Typography
- **Archivo** (variable, `wdth` 62–125, weight 400–900). Already loaded through `next/font` in web. Vendor the woff2 into `core/static/core/fonts/` for Django (OFL).
- **JetBrains Mono** 500/700 for every booking reference and the reference inputs. Uppercase, letter-spacing `.04–.06em`.

| Role | Size / weight / stretch / tracking / line-height |
|---|---|
| Home H1 | `clamp(42px,6vw,68px)` / 900 / 112% / -.035em / .98, `text-wrap: balance` |
| Page H1 (book, find, done) | `clamp(34px,5vw,48px)`; done uses `clamp(36px,6vw,52px)` / 900 / 112% / -.03em |
| Staff H1 | 34px / 900 / 112% / -.03em |
| H2 section | 30px / 800 / 110% / -.025em |
| Card title | 17–19px / 800 |
| Eyebrow | 12.5px / 700 / uppercase / .14em / clay (or clay-light on dark) |
| Body | 15–16px / 400–600; lead 18px, line-height 1.55, slate-600 |
| Field label | 14px / 700 (13.5px in the staff panel) |
| Caption | 13–13.5px slate-500 |
| Table header | 12px / 700 / uppercase / .06–.08em / slate-500 |
| Stat value | 26–30px / 900 / 108%, `tabular-nums` |
| Money | always `font-variant-numeric: tabular-nums` |

### Radii
Pills `999px` · small buttons and nav items `7–8px` · inputs, buttons, time tiles `10px` · sport tiles and coverage cards `12px` · tables and stat cards `14px` · cards `16px` · dark hero cards (desk lookup, reference) `18px`.

### Shadows
- Raised card (Free tonight): `0 1px 2px #0f172a0a, 0 12px 32px -12px #0f172a1f`
- Summary aside: `0 12px 32px -16px #0f172a26`
- Selected segment: `0 1px 3px #0f172a26`
- Bottom bar: `0 -8px 24px -12px #0f172a33`
- Staff side panel: `-20px 0 40px -20px #0f172a40`
- Toast: `0 12px 32px -8px #0f172a66`
- Selected schedule block: `0 0 0 3px #0f172a`

### Spacing and layout
Content max-width `1120px`, side padding `20px`. Cards pad `22px` (staff 16–24px). Grid gaps `8/10/12/14/20/28px`. Hit targets ≥ 44px.

### Shared controls
- **Primary button**: court bg, white, 700, 16–17px, padding `15px 26px` (hero) or `13px 22px`, radius 10. Hover court-dark.
- **Dark button**: ink bg, white. Hover ink-2.
- **Outline button**: `1.5px solid line`, white bg. Hover border ink.
- **Segmented control**: hair track, padding 4, gap 2–4. Selected segment is white with the selected shadow and ink text; the others are transparent with slate-500 text.
- **Status pills** (12.5px/700, padding `4px 10px`, radius 999):

| Status | Background / text |
|---|---|
| Confirmed | `#dcfce7` / `#166534` |
| Checked in | `#16a34a` / `#fff` |
| Payment pending | `#ffedd5` / `#9a3412` |
| Completed | `#f1f5f9` / `#475569` |
| Blocked | `#e2e8f0` / `#334155` |
| Cancelled | `#fee2e2` / `#991b1b` |
| Needs refund | `#fff7ed` / `#9a3412`, with a `1px #fed7aa` border |
| Expired | `#f1f5f9` / `#64748b` |

## Screens: storefront (`apps/web`)

### Shell (`layout.tsx`)
1. Test-mode banner: ink bg, `#e2e8f0` text, 12.5px, tracking .04em, padding `8px 16px`, with a 7px `#4ade80` dot before the text.
2. Sticky header: white, bottom border line-soft, inner 1120px, padding `14px 20px`.
   - Left: logo mark (30×30, radius 8, court bg, white "K" 900/16px/115%) and "Kalaro Courts" (800/19px/-.02em/112%).
   - Right: "Find booking" (ghost, 600/15px, hover hair) and "Book" (dark button, 700/15px, padding `9px 16px`).
3. Footer: top border line-soft, 13.5px slate-500. Left: "Kalaro Courts is a fictional venue. Test mode, no real payments." Right: "Open daily · 7 AM – 11 PM".

### Landing (`app/page.tsx`)
**Hero.** Two columns via `grid-template-columns: repeat(auto-fit, minmax(min(100%,400px),1fr))`, gap 40, padding `56px 20px 40px`.
- Left:
  - Eyebrow: "Open daily · 7 AM – 11 PM"
  - H1: `SITE.tagline`
  - Lead: "Basketball, volleyball, tennis, badminton and pickleball. Pay online, then show your reference at the front desk."
  - Buttons: "Book a court" (primary) and "Find my booking" (outline).
- Right: the **Free tonight** card (white, radius 16, padding 22, raised shadow).
  - Header: "Free tonight" (800/17px), and on the right "{Day d Mon} · peak rates" (13px slate-500). Drop "· peak rates" when the remaining hours aren't peak.
  - One row per sport, as a 4-column grid `10px 1fr auto auto`, padding `13px 10px`, top border hair, hover paper: tag square, label 700/16px, "Next free 8 PM" (court-dark 600/14px) or "Full tonight" (slate-400), and a "›" chevron.
  - A row links to `/book?sport=…&date=today&start=H` (or tomorrow's date when the sport is full tonight).

**Sports & rates.** A table card, not tiles.
- Header row: H2 on the left; on the right, "Per hour" and "**Peak** = weekdays from 5 PM, weekends all day" (Peak in clay).
- Columns `2fr 1fr 1fr 1fr`: Sport (tag + label + a 14px slate-500 sub "Full court"/"Half court" for basketball) · Courts · Off-peak (right, 600) · Peak (right, 700, clay).
- Header row: paper bg, 12px uppercase. Data rows: padding `16px 20px`.
- Under the table, 14px slate-500: "Basketball and volleyball share the same two courts. Badminton and pickleball share 12 multi-courts."

**How it works.** Four cards (`auto-fit minmax(220px,1fr)`). Each has a big number (34px/900/115%, court), a title (800/18px) and copy (15px slate-600). Copy as today.

**Questions.** Two columns.
- Left: H2 "Questions" and the hours sentence.
- Right: an accordion of `FAQ`. Use `<details>`/`<summary>` (no JS) with rows split by line-soft borders, a summary of 700/16px with "+"/"−", and the answer at 15.5px slate-600, max-width 560. The first item is open.

**Owners CTA.** Ink card, radius 18, padding 32, flex with space-between.
- Eyebrow (clay-light): "For venue owners"
- Title (26px/800): "See the owner's side"
- Sub (`#cbd5e1`): "Live schedule, front-desk check-in, walk-ins and revenue."
- Button: primary, "Open the staff dashboard" → `/staff` (`prefetch={false}`).

### Book (`app/book/page.tsx`)
- Eyebrow "Book a court" and H1 "Pick your court".
- Below that, a grid `minmax(0,1fr) 340px`, gap 28. **Under 900px** it becomes one column, the aside is hidden, and a fixed bottom bar appears.
- Left column: four step cards (white, radius 16, padding 22, gap 14). Each card header is a 26px step circle and a title (800/19px).
  - Circle states: done = court bg with "✓"; active = ink with the number; idle = line-soft bg with slate-500 number.

1. **Sport**
   - Tiles in `auto-fill minmax(150px,1fr)`, gap 10, `2px` border, radius 12, padding 14.
   - Each tile: the sport bar (22×4), the label (800/16.5px) and "{n} courts · from ₱350/h" (13.5px slate-500).
   - Selected: court border and court-tint bg. Hover: court border.
   - For basketball, add a **Coverage** sub-row: two radio cards, "Full court" / "₱1,200 – ₱1,600 / hour" and "Half court" / "Half A or B · ₱700 – ₱900 / hour". Use the catalog rates, not literals.
2. **Day & length**
   - Seven day buttons in one row (`repeat(7, minmax(0,1fr))`, gap 6, radius 10, min-height 44). Each has:
     - a top label, "Today" or the weekday (12px)
     - the day number (20px/800/110%)
     - "PEAK" (9.5px/800, clay) on peak-all-day dates
   - Selected day: ink bg, white text, PEAK in `#fed7aa`.
   - Then the Length segmented control: "1 hour · 2 hours · 3 hours".
3. **Start time**
   - Header right side: a clay dot with "Peak rate", and "Prices for {n} hours".
   - Time tiles in `auto-fill minmax(108px,1fr)`, gap 8, radius 10. Each tile has three lines:
     - the time (800/16px)
     - the price (700/13px): clay if peak, `#334155` if off-peak
     - availability (11.5px): "{n} free", or "1 court left" in clay
   - Booked tiles: paper bg, 0.5 opacity, "Booked", not clickable. Selected tile: court bg, white text, sub in `#dcfce7`.
   - On today, add "Earlier times today have passed." (13.5px slate-500) above the tiles.
   - Empty states (dashed `1.5px line` box, radius 12, padding 28, centred slate-500): "Pick a sport to see free times." and "No times left on this day. Try another day or a shorter length."
   - Once a time is chosen, a **Court** row: "Court · {n} free at 8 PM", with pill buttons per free court (ink when selected). The first free court is preselected.
4. **Your details**: the existing `DetailsForm`, restyled.
   - Fields: Full name (full width), then Email and Mobile number side by side (`auto-fit minmax(220px,1fr)`).
   - Inputs: 16px, padding `12px 14px`, `1.5px line` border, radius 10.
   - Consent: a 20px checkbox (accent court) with the existing consent text and the privacy link.
   - The card sits at 0.6 opacity until a court and time are chosen.

**Summary aside** (`position: sticky; top: 84px`; white, radius 16, aside shadow):
- Header: "Your booking", with the sport tag and label on the right.
- Rows: Court, Coverage, Date, Time (15px; key slate-500, value 600; "—" in slate-400 when empty).
- A dashed divider, then the price lines "Off-peak · 1h × ₱1,200 — ₱1,200" and "Peak · 2h × ₱1,600 — ₱3,200".
- Footer: paper bg, "Total" with the amount (900/28px/110%), the full-width **Continue to payment** button, and a hint line (13px, centred). Hint per state:
  - no sport: "Pick a sport to get started."
  - no time: "Pick a start time."
  - details incomplete: "Add your details to continue."
  - ready: "You'll pay on PayMongo's test checkout. Your slot is held for 20 minutes."
- Disabled button: line-soft bg, slate-400 text.
- The price shown comes from fresh availability (`slot.price_centavos`), as today; the server quotes it again. The off-peak/peak split uses the catalog rates and `peak` rules, display only.

**Bottom bar (<900px)**: fixed, white, top border, bar shadow, padding `12px 16px`. Left: "{Sport} · {Sun 25 Oct} · {8 PM–10 PM}" (12.5px, ellipsis) over the total (900/22px). Right: the same Continue button. Add 84px bottom padding to the page when the bar shows.

**Submit → hold overlay**: on submit, show a scrim (`#0f172acc`) with a white card: spinner, "Slot held for 20 minutes", "Taking you to PayMongo's test checkout…". Use `useFormStatus` pending inside `DetailsForm`. Don't touch `actions.ts`.

### Success (`app/book/success/page.tsx`): confirmed state
- Max-width 640.
- Top: a 34px court circle with "✓" and the eyebrow "Payment received" (court-dark). H1 "You're booked."
- **Reference card** (ink, radius 18, padding 26):
  - "Your reference" (13px `#94a3b8`)
  - The reference in mono 700 `clamp(34px,8vw,48px)`, tracking .04em
  - A **Copy** button (`1.5px #334155` border; turns into "Copied")
  - A court strip: "Show this reference at the front desk when you arrive."
- Details card rows: Court, Sport, Date, Time, Amount paid, Payment method. Leave out the email line.
- Buttons: "Look up a booking" (outline ink) → `/booking`; "Book another court" (primary) → `/book`.
- The pending, needs-refund and not-found states keep today's copy and logic, restyled with the same card and warn tokens.

### Cancelled (`app/book/cancelled/page.tsx`)
Same shell as success, with a neutral heading. Copy and logic unchanged.

### Find booking (`app/booking/page.tsx`, `lookup-form.tsx`)
- Max-width 640. Eyebrow "Your booking", H1 "Find your booking", lead "Enter the reference you got after paying and the email you booked with."
- Form card: Booking reference (mono 18px, uppercase, placeholder `KC-XXXXXX`), Email used for the booking, and a "Find booking" primary button.
- Not found: a warn box with "No booking matches that reference and email. Check for typos — references start with KC-."
- Found: a card with a `2px court` border, a court-tint header (mono reference 22px and a status pill), then rows from the lookup payload.

## Screens: staff dashboard (`apps/backend/dashboard`)

### Shell (`dashboard/base.html`)
- The banner, as above.
- Below it, a flex row: a **sidebar** (232px, white, right border line-soft, padding `18px 14px`, sticky, full height) and **main** (padding `28px 32px 48px`).
- Sidebar:
  - Brand: the logo mark, "Kalaro Courts" over "Staff".
  - Nav (buttons 700/15px, padding `10px 12px`, radius 8):
    - **Front desk**, with a court pill badge showing the arriving-next count
    - Schedule
    - Bookings
    - Overview
  - Current nav item: court-tint bg, court-dark text, `aria-current="page"`.
  - Footer: a role caption ("Role: Owner"/"Role: Viewer", using the existing role badge) and **Sign out**, still the POST form.
- Main header: a 13px/700 slate-500 date/time line ("Sunday 25 October · 7:48 PM", Manila), then the H1.
- The viewer's "You're exploring the demo…" note stays at the top of the content.
- Keep the `hx-headers` CSRF wrappers: the sidebar replaces the header block, so the CSRF attribute moves onto the sidebar.

### Front desk (new, `dashboard:desk`)
Two columns, `1.35fr / 1fr`, gap 20.

**Left column, top to bottom:**
1. **Lookup card** (ink, radius 18, padding 24, white text).
   - Title "Check in a customer" (800/18px) and sub "Type their reference, or search by name." (14px `#94a3b8`).
   - A GET form: a mono 24px/700 uppercase input (ink-2 bg, `2px #334155` border, radius 12, padding `14px 18px`, placeholder `KC-XXXXXX`, `autofocus`) and a primary "Look up" button.
   - **Suggestions** (htmx `hx-get` on `input changed delay:250ms`, from 2 characters) list up to 5 matches by reference or name. Each row is `120px 1fr auto`: mono ref · name · "Today, 8 PM – 10 PM". Rows sit on ink-2, with `#334155` dividers and hover.
   - Normalise the query: trim, uppercase, and add `KC-` when there's no hyphen.
2. **Not found**: warn box, "**No booking found for KC-XXXX.** Check the code with the customer, or search their name."
3. **Result card** (white, radius 18; border `2px court` when check-in is possible, otherwise `2px line-soft`):
   - Header: the mono ref and status pill; the name (900/28px/108%); contact (14.5px slate-500, masked for the viewer); on the right, "Paid" and the amount (900/22px).
   - A 3-column facts strip: Court · Sport ("Basketball · full") · Time ("8 PM – 10 PM", prefixed with "Fri 30, " when the booking isn't today).
   - A warning strip (warn tokens). Show the first that applies:
     - confirmed but not today → "This booking is for {Friday 30 Oct} — not today."
     - pending → "Payment not received yet. The slot is on a 20-minute hold."
     - started and not ended → "Running late — started at 7 PM. Ends 9 PM."
     - ended → "This session has already ended."
   - Footer (paper bg): **Check in** (primary, 800/17px, padding `14px 28px`) when `can_check_in`, otherwise "✓ Checked in at 6:55 PM" in court-dark. On the right, "View in schedule" (ghost) → schedule for that day with the panel open.
4. **Stats**, a 4-up grid of white radius-14 cards:
   - Bookings today: "{n} walk-ins"
   - Revenue today: "Online + cash"
   - Courts in use: "{n}/20" and "Right now"
   - Active holds: "Unpaid, 20 min"

**Right column:**
- **Arriving next** card.
  - Header: "Arriving next", with "Next 3 hours" on the right.
  - Includes today's confirmed bookings that aren't checked in, haven't ended, and start within the next 3 hours, earliest first.
  - Rows `62px 1fr auto`: time (800/15px) over a tag ("LATE" in clay if started, "NEXT" in court-dark if it starts next hour) · tag square, name and "{court} · {ref}" · a "Check in" outline-green small button (htmx POST).
  - Empty: "Nobody else is due in the next 3 hours."
- **On court now** card.
  - Header: "On court now", with "{n} checked in" on the right.
  - Rows: tag, name, court, and "until 9 PM". A row opens the booking.

**Check-in action**: a `POST dashboard:check_in` with `reference`.
- Success: re-render the desk partial with an out-of-band toast "{name} checked in · {court}". The toast is court bg, white, 700/15px, radius 12, bottom-centre, toast shadow, prefixed "✓ ".
- Refusal: 403 with "You can't check in this booking.", in the result card.

### Schedule (`schedule.html`)
- Header controls: "‹" · "Today" · "›" outline buttons, then the long date (800/16px).
- Legend row (13px), as swatches 16×12, radius 3:
  - Online
  - Checked in
  - Walk-in
  - Payment pending (dashed)
  - Block (hatched)
  - Done
  - On the right: "Click an empty slot to add a walk-in or block."
- **Grid**: CSS grid, columns `196px repeat(16, minmax(64px,1fr))`, min-width 1220, inside a white radius-14 scroll box (`max-height: calc(100vh - 210px)`). Rows: a 40px header, 30px group rows, 46px court rows. Sticky top header and sticky left court column.
  - Groups: "Basketball · Volleyball" (Court 1 Half A/B, Court 2 Half A/B), "Tennis", "Multi-courts · Badminton & Pickleball". Group rows: paper bg, 11.5px/700 uppercase .08em slate-500.
  - Court label: 700/14px, with the half as 12.5px slate-500 ("Half A").
  - Hour headers: "7 AM"…"10 PM", 12.5px/700. Past hours are slate-400; the current hour has a `#fff7ed` bg.
  - **Bookings are blocks**, not repeated cells. A block spans `column start / span hours` and, for a **full basketball booking, both half rows** (`row / span 2`). Block style: margin `4px 3px`, radius 7, `1.5px` border, padding `4px 9px`, name 700/13px over "Sport · half · KC-XXXX" 11.5px at 0.8 opacity, both with ellipsis. Colours by state:

| State | Background | Border | Text |
|---|---|---|---|
| Online confirmed | `#dcfce7` | `#16a34a` | `#14532d` |
| Checked in | `#16a34a` | `#15803d` | `#fff` |
| Walk-in | `#0f172a` | `#0f172a` | `#fff` |
| Pending | `#fff` | `#ea580c` dashed | `#9a3412` |
| Block | `repeating-linear-gradient(135deg,#f1f5f9 0 6px,#e2e8f0 6px 12px)` | `#cbd5e1` | `#334155` |
| Done | `#f1f5f9` | `#e2e8f0` | `#64748b` |

  - The selected block gets the selected ring.
  - **Empty cells**: a button that shows "+" in slate-400 on hover, with a court-tint hover bg. Past cells are paper and inert.
  - **Now marker**: today only, in the current hour's column at `left: (minutes/60)%`. A 2px clay vertical line, with a clay chip showing "7:48" (10.5px/800, white) at the top.
  - CSP: no inline `style`. Put generated classes in `dashboard.css`: `.r-2…r-26` for grid-row, `.rs-2` for span 2, `.c-2…c-17` for grid-column start, `.cs-1…cs-3` for span, and `.now-m-0…now-m-59` (or 12 five-minute steps) for the marker offset.
- **Side panel** (fixed right, 400px, white, panel shadow, header "Booking"/"Add to schedule" with a × close):
  - **Detail**: mono ref and pill; name (900/24px) and contact; a bordered key/value list (Court, Sport, Date, Time, Source, Amount, Checked in); a full-width **Check in** button when allowed; the existing Cancel action.
  - **Add** (existing `StaffBookingForm`, restyled):
    - "{Court label} · {date}"
    - A segmented control, Walk-in / Block
    - Sport chips limited to the court's sports
    - Coverage chips "Full court" / "Half A" (basketball only)
    - Starts select and Length select (1–3 hours)
    - Customer name or Note. The viewer gets the `BLOCK_REASONS` select.
    - The price line, "Cash · 8 PM – 9 PM" with the amount 900/22px, or "No charge" / "—" for blocks
    - Errors in a warn box
    - An ink submit, "Add walk-in" or "Block court"
    - Block helper text: "A block (maintenance, an event) takes the whole court and needs a note."

### Bookings (`bookings.html`)
- Toolbar: search input ("Search reference, name, email or mobile"; flex 1, min 260) · status segmented (All, Confirmed, Checked in, Pending, Completed) · sport select. These are the existing GET params; keep the htmx partial swap and pagination.
- Table card. Columns `130px minmax(170px,1.2fr) minmax(170px,1.3fr) minmax(180px,1.4fr) 92px 112px 90px`:
  - Reference (mono 700/13.5px)
  - When ("Today, 8 PM – 10 PM" / "Fri 30 Oct, …")
  - Court (tag + name)
  - Customer (name 700, contact 12.5px slate-500 ellipsis, masked for the viewer)
  - Source ("Online"/"Walk-in")
  - Status pill
  - Amount (right, 700, tabular)
- Row hover: paper. The whole row is a link to `booking_detail`.
- Empty: "No bookings match." Footer: "Showing {n} of {total} bookings".

### Overview (`overview.html`)
- A 4-up stat grid:
  - Revenue · 7 days, with a change vs the prior week in court-dark
  - Bookings · 7 days, with "{n} walk-ins"
  - Utilization · 7 days, with "Peak hours {n}%"
  - Avg. booking, with "{h} hours"
- Below, two columns (`1fr / 1.5fr`):
  - **Revenue by sport · last 30 days**: per sport, label and amount, then a 10px bar (hair track, sport colour, width relative to the top sport). Under it, a "Last 7 days / Last 30 days" table with Gross · Fees · Net (Net 800).
  - **Utilization by weekday & hour** ("Last 28 days · darker is busier"): a grid `40px repeat(16, minmax(26px,1fr))`, gap 3, with 26px-high cells and radius 4. Cell colour is `color-mix(in oklch, #16a34a {v}%, #f1f5f9)` with the % printed; text is white above 55%. Use 10 bucket classes (`.heat-0…heat-9`), not inline colours.
- Keep the existing alerts (needs-refund) above the stats.

## Interactions and states (summary)
- Every step on `/book` stays URL-param driven (links, not client state), so back/forward and sharing keep working. Selecting a sport resets the start and court.
- Free tonight: if availability fails, hide the card. No error copy on the landing.
- The reference **Copy** button is a small client component using `navigator.clipboard.writeText`. Its label becomes "Copied" for 2 s.
- Desk lookup works without JS (a GET `?q=`). The suggestions and the check-in partial are htmx enhancements.
- Toasts auto-hide through CSS animation only. No inline JS (CSP).

## Assets
No images. The logo mark is CSS (the "K" square). Fonts: Archivo (OFL) and JetBrains Mono (OFL).

## Files
- `prototypes/Kalaro Booking.dc.html`: storefront prototype (home, book, done, find). The `startScreen` prop picks the screen.
- `prototypes/Kalaro Staff.dc.html`: dashboard prototype. The `startTab` prop is `desk | schedule | bookings | overview`.
- `prototypes/support.js`: the runtime the prototypes need to open in a browser.
- `docs/plans/2026-10-28-ui-redesign/`: the plan, and the prompts in `prompts/`.
- `docs/plans/_index.row.md`: the row to add to `docs/plans/_index.md`.
