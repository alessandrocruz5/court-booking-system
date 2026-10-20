import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  getDashboardUrl,
  HOLD_MINUTES,
  HOURS,
  MAX_HOURS,
  PEAK_FROM_HOUR,
  SITE,
  WINDOW_DAYS,
} from "../site";

// The drift guard: the site's copy against the backend's catalog, docs/api/fixtures/catalog.json.
const CATALOG = fileURLToPath(
  new URL("../../../../../docs/api/fixtures/catalog.json", import.meta.url),
);

const catalog = JSON.parse(readFileSync(CATALOG, "utf8")) as {
  venue: { name: string };
  hours: { open: number; close: number };
  window_days: number;
  max_hours: number;
  hold_minutes: number;
  peak: { weekdays_from_hour: number };
};

describe("site copy against the backend catalog fixture", () => {
  it("matches the opening hours", () => {
    expect(HOURS).toEqual(catalog.hours);
  });

  it("matches the booking window and maximum duration", () => {
    expect(WINDOW_DAYS).toBe(catalog.window_days);
    expect(MAX_HOURS).toBe(catalog.max_hours);
  });

  it("matches the hold duration and the weekday peak start", () => {
    expect(HOLD_MINUTES).toBe(catalog.hold_minutes);
    expect(PEAK_FROM_HOUR).toBe(catalog.peak.weekdays_from_hour);
  });

  it("matches the venue name", () => {
    expect(SITE.name).toBe(catalog.venue.name);
  });
});

describe("getDashboardUrl", () => {
  it("reads DASHBOARD_URL from the given source", () => {
    expect(getDashboardUrl({ DASHBOARD_URL: "http://localhost:8000/dashboard/" })).toBe(
      "http://localhost:8000/dashboard/",
    );
  });

  it("throws when DASHBOARD_URL is missing or invalid", () => {
    expect(() => getDashboardUrl({})).toThrow();
    expect(() => getDashboardUrl({ DASHBOARD_URL: "not a url" })).toThrow();
  });
});
