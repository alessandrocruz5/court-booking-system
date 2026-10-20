import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { catalogSchema } from "@/lib/api/schemas";
import {
  bookingHref,
  formatHour,
  formatPeso,
  manilaToday,
  parseBookingParams,
  windowDates,
} from "../params";

const FIXTURE = fileURLToPath(
  new URL("../../../../../../docs/api/fixtures/catalog.json", import.meta.url),
);
const catalog = catalogSchema.parse(JSON.parse(readFileSync(FIXTURE, "utf8")));
const TODAY = "2026-10-17";

describe("parseBookingParams", () => {
  it("applies the defaults", () => {
    expect(parseBookingParams({}, catalog, TODAY)).toEqual({
      sport: undefined,
      coverage: "full",
      hours: 1,
      date: undefined,
      court: undefined,
      start: undefined,
    });
  });

  it("falls back on unknown values", () => {
    const p = parseBookingParams(
      { sport: "golf", coverage: "third", hours: "abc", date: "nope", start: "x" },
      catalog,
      TODAY,
    );
    expect(p).toMatchObject({ sport: undefined, coverage: "full", hours: 1, date: undefined });
    expect(p.start).toBeUndefined();
  });

  it("turns half into full for volleyball", () => {
    expect(
      parseBookingParams({ sport: "volleyball", coverage: "half" }, catalog, TODAY).coverage,
    ).toBe("full");
    expect(
      parseBookingParams({ sport: "basketball", coverage: "half" }, catalog, TODAY).coverage,
    ).toBe("half");
  });

  it("clamps hours to 1..max_hours", () => {
    expect(parseBookingParams({ hours: "9" }, catalog, TODAY).hours).toBe(3);
    expect(parseBookingParams({ hours: "0" }, catalog, TODAY).hours).toBe(1);
    expect(parseBookingParams({ hours: "2" }, catalog, TODAY).hours).toBe(2);
  });

  it("drops a date outside the window", () => {
    expect(parseBookingParams({ date: "2026-10-23" }, catalog, TODAY).date).toBe("2026-10-23");
    expect(parseBookingParams({ date: "2026-10-24" }, catalog, TODAY).date).toBeUndefined();
    expect(parseBookingParams({ date: "2026-10-16" }, catalog, TODAY).date).toBeUndefined();
  });

  it("keeps a valid court and start, and drops an out-of-hours start", () => {
    const p = parseBookingParams({ court: "bb-1", start: "18" }, catalog, TODAY);
    expect(p).toMatchObject({ court: "bb-1", start: 18 });
    expect(parseBookingParams({ start: "23" }, catalog, TODAY).start).toBeUndefined();
    expect(parseBookingParams({ start: "6" }, catalog, TODAY).start).toBeUndefined();
  });

  it("takes the first of a repeated parameter", () => {
    expect(parseBookingParams({ sport: ["tennis", "badminton"] }, catalog, TODAY).sport).toBe(
      "tennis",
    );
  });
});

describe("bookingHref", () => {
  const params = parseBookingParams(
    {
      sport: "basketball",
      coverage: "half",
      hours: "2",
      date: "2026-10-18",
      court: "bb-1",
      start: "18",
    },
    catalog,
    TODAY,
  );

  it("round-trips the params", () => {
    expect(bookingHref(params)).toBe(
      "/book?sport=basketball&coverage=half&hours=2&date=2026-10-18&court=bb-1&start=18",
    );
  });

  it("clears the court and start when the sport changes", () => {
    const href = bookingHref(params, { sport: "tennis", coverage: "full" });
    expect(href).toBe("/book?sport=tennis&hours=2&date=2026-10-18");
  });

  it("clears the start when the date or duration changes", () => {
    expect(bookingHref(params, { date: "2026-10-19" })).not.toContain("start=");
    expect(bookingHref(params, { hours: 3 })).not.toContain("start=");
    expect(bookingHref(params, { hours: 3 })).toContain("court=bb-1");
  });

  it("sets the court and start together", () => {
    expect(bookingHref(params, { court: "bb-2", start: 20 })).toContain("court=bb-2&start=20");
  });

  it("is /book with nothing set", () => {
    expect(bookingHref(parseBookingParams({}, catalog, TODAY))).toBe("/book");
  });
});

describe("dates and formatting", () => {
  it("gives the Manila date, which can be ahead of UTC", () => {
    expect(manilaToday(new Date("2026-10-16T17:30:00Z"))).toBe("2026-10-17");
    expect(manilaToday(new Date("2026-10-16T15:59:00Z"))).toBe("2026-10-16");
  });

  it("lists the window", () => {
    const dates = windowDates("2026-10-29", 7);
    expect(dates).toHaveLength(7);
    expect(dates[0]).toBe("2026-10-29");
    expect(dates[6]).toBe("2026-11-04");
  });

  it("formats pesos and hours", () => {
    expect(formatPeso(160000)).toBe("₱1,600");
    expect(formatPeso(120000)).toBe("₱1,200");
    expect(formatHour(7)).toBe("7 AM");
    expect(formatHour(12)).toBe("12 PM");
    expect(formatHour(22)).toBe("10 PM");
    expect(formatHour(24)).toBe("12 AM");
  });
});
