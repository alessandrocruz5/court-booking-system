import type { Catalog, Coverage, Sport } from "@/lib/api/schemas";

/**
 * The /book flow's state, kept in the URL. Pure and tested: it imports only types, never the
 * server-only API client.
 */
export type BookingParams = {
  sport?: Sport;
  coverage: Coverage;
  hours: number;
  /** `YYYY-MM-DD`, inside the booking window. */
  date?: string;
  /** A court code such as `bb-1`. */
  court?: string;
  /** The start hour, 0 to 23. */
  start?: number;
};

export type RawSearchParams = Record<string, string | string[] | undefined>;

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const COURT_RE = /^[a-z0-9][a-z0-9-]{0,31}$/i;
const DIGITS_RE = /^\d{1,2}$/;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * Reads the query string into valid params. Unknown or invalid values fall back to `undefined` or
 * the defaults (coverage `full`, 1 hour). `today` is the Manila date, `YYYY-MM-DD`.
 */
export function parseBookingParams(
  searchParams: RawSearchParams,
  catalog: Catalog,
  today: string,
): BookingParams {
  const rawSport = first(searchParams.sport);
  const sportEntry = catalog.sports.find((s) => s.id === rawSport);

  const rawCoverage = first(searchParams.coverage);
  let coverage: Coverage = rawCoverage === "half" ? "half" : "full";
  // A coverage the sport doesn't offer (volleyball with half) becomes full.
  if (sportEntry && !sportEntry.coverages.includes(coverage)) coverage = "full";

  const rawHours = first(searchParams.hours);
  const hours =
    rawHours !== undefined && DIGITS_RE.test(rawHours)
      ? Math.min(Math.max(Number(rawHours), 1), catalog.max_hours)
      : 1;

  const rawDate = first(searchParams.date);
  const date =
    rawDate !== undefined &&
    DATE_RE.test(rawDate) &&
    windowDates(today, catalog.window_days).includes(rawDate)
      ? rawDate
      : undefined;

  const rawCourt = first(searchParams.court);
  const court = rawCourt !== undefined && COURT_RE.test(rawCourt) ? rawCourt : undefined;

  const rawStart = first(searchParams.start);
  const startNumber = rawStart !== undefined && DIGITS_RE.test(rawStart) ? Number(rawStart) : NaN;
  const start =
    Number.isInteger(startNumber) &&
    startNumber >= catalog.hours.open &&
    startNumber < catalog.hours.close
      ? startNumber
      : undefined;

  return { sport: sportEntry?.id, coverage, hours, date, court, start };
}

/**
 * `/book?...` for the current params with `patch` applied. Changing the sport clears the court and
 * start; changing the date, duration or coverage clears the start. Defaults (full, 1 hour) are
 * left out of the URL.
 */
export function bookingHref(params: BookingParams, patch: Partial<BookingParams> = {}): string {
  const base: BookingParams = { ...params };
  if ("sport" in patch) {
    base.court = undefined;
    base.start = undefined;
  }
  if ("date" in patch || "hours" in patch || "coverage" in patch) base.start = undefined;
  const next = { ...base, ...patch };

  const query = new URLSearchParams();
  if (next.sport) query.set("sport", next.sport);
  if (next.coverage !== "full") query.set("coverage", next.coverage);
  if (next.hours !== 1) query.set("hours", String(next.hours));
  if (next.date) query.set("date", next.date);
  if (next.court) query.set("court", next.court);
  if (next.start !== undefined) query.set("start", String(next.start));
  const qs = query.toString();
  return qs ? `/book?${qs}` : "/book";
}

/** Today's date in Asia/Manila as `YYYY-MM-DD`. */
export function manilaToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function toUtc(date: string): Date {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1));
}

/** `days` consecutive dates starting at `today`. */
export function windowDates(today: string, days: number): string[] {
  const start = toUtc(today);
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + i);
    return d.toISOString().slice(0, 10);
  });
}

export function isWeekend(date: string): boolean {
  const day = toUtc(date).getUTCDay();
  return day === 0 || day === 6;
}

/** `Today`, or `Sat 18`. */
export function formatDayChip(date: string, today: string): string {
  if (date === today) return "Today";
  const weekday = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "UTC" }).format(
    toUtc(date),
  );
  return `${weekday} ${toUtc(date).getUTCDate()}`;
}

/** `₱1,200`, from integer centavos. Whole pesos only; the rate card has no centavos. */
export function formatPeso(centavos: number): string {
  return `₱${Math.round(centavos / 100).toLocaleString("en-US")}`;
}

/** `7 AM`, `12 PM`, `10 PM`. */
export function formatHour(hour: number): string {
  const h = hour % 24;
  return `${h % 12 === 0 ? 12 : h % 12} ${h < 12 ? "AM" : "PM"}`;
}
