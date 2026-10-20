import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  clientIpFrom,
  confirmCheckout,
  createBooking,
  getAvailability,
  getAvailabilityOnce,
  getCatalog,
  lookupBooking,
} from "../client";

// Read at run time, not imported: docs/ isn't in the web image's build context, where
// `next build` typechecks this file.
function fixture(name: string): Record<string, unknown> {
  const path = new URL(`../../../../../../docs/api/fixtures/${name}`, import.meta.url);
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

const catalog = fixture("catalog.json");
const availability = fixture("availability.json");
const bookingCreated = fixture("booking-created.json");

// Not a real secret, and nothing gitleaks would mistake for one.
const TOKEN = "t".repeat(40);
const API_URL = "http://backend.test";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubEnv("API_URL", API_URL);
  vi.stubEnv("INTERNAL_API_TOKEN", TOKEN);
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function lastCall(): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.lastCall ?? [];
  return { url: String(url), init: init ?? {} };
}

const bookingInput = {
  court: "tn-2",
  sport: "tennis",
  coverage: "full",
  date: "2026-10-31",
  startHour: 18,
  hours: 2,
  customer: { name: "Ana Reyes", email: "ana@example.com", mobile: "09171234567" },
  consent: true,
  clientIp: "203.0.113.10",
} as const;

describe("request", () => {
  it("sends the bearer token, no-store, redirect: error and a timeout", async () => {
    fetchMock.mockResolvedValue(json(catalog));
    await expect(getCatalog()).resolves.toEqual(catalog);

    const { url, init } = lastCall();
    expect(url).toBe(`${API_URL}/api/v1/catalog`);
    expect(init.method).toBe("GET");
    expect(init.cache).toBe("no-store");
    expect(init.redirect).toBe("error");
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.body).toBeUndefined();
    const headers = new Headers(init.headers);
    expect(headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(headers.has("content-type")).toBe(false);
  });

  it("sends the booking as snake_case JSON", async () => {
    fetchMock.mockResolvedValue(json(bookingCreated, 201));
    await expect(createBooking(bookingInput)).resolves.toEqual(bookingCreated);

    const { url, init } = lastCall();
    expect(url).toBe(`${API_URL}/api/v1/bookings`);
    expect(init.method).toBe("POST");
    expect(init.cache).toBe("no-store");
    expect(init.redirect).toBe("error");
    const headers = new Headers(init.headers);
    expect(headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(headers.get("content-type")).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual({
      court: "tn-2",
      sport: "tennis",
      coverage: "full",
      date: "2026-10-31",
      start_hour: 18,
      hours: 2,
      customer: { name: "Ana Reyes", email: "ana@example.com", mobile: "09171234567" },
      consent: true,
      client_ip: "203.0.113.10",
    });
  });

  it("maps the other calls to snake_case on the wire", async () => {
    fetchMock.mockResolvedValue(json({ status: "not_found", booking: null }));
    await confirmCheckout("cs_abc");
    expect(lastCall().url).toBe(`${API_URL}/api/v1/checkout/confirm`);
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ checkout_session_id: "cs_abc" });

    fetchMock.mockResolvedValue(json({ error: "not_found" }, 404));
    await expect(
      lookupBooking({ reference: "KC-7Q4M2X", email: "ana@example.com", clientIp: "::1" }),
    ).rejects.toMatchObject({ status: 404, code: "not_found" });
    expect(JSON.parse(String(lastCall().init.body))).toEqual({
      reference: "KC-7Q4M2X",
      email: "ana@example.com",
      client_ip: "::1",
    });

    fetchMock.mockResolvedValue(json({ error: "invalid_request", fields: ["date"] }, 400));
    await expect(
      getAvailability({ date: "2026-11-03", sport: "basketball", coverage: "half", hours: 2 }),
    ).rejects.toMatchObject({ status: 400, code: "invalid_request", fields: ["date"] });
    expect(lastCall().url).toBe(
      `${API_URL}/api/v1/availability?date=2026-11-03&sport=basketball&coverage=half&hours=2`,
    );
  });

  it("getAvailabilityOnce delegates to getAvailability", async () => {
    fetchMock.mockResolvedValue(json(availability));
    await expect(getAvailabilityOnce("2026-11-03", "basketball", "half", 2)).resolves.toEqual(
      availability,
    );
    expect(lastCall().url).toBe(
      `${API_URL}/api/v1/availability?date=2026-11-03&sport=basketball&coverage=half&hours=2`,
    );
  });

  it("turns a 409 slot_taken into ApiError(409, slot_taken), without the request body", async () => {
    fetchMock.mockResolvedValue(json({ error: "slot_taken" }, 409));
    const error = await createBooking(bookingInput).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "slot_taken" });
    const message = (error as ApiError).message;
    expect(message).not.toContain("ana@example.com");
    expect(message).not.toContain("Ana Reyes");
  });

  it("turns a non-2xx without an error body into unavailable", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 405 }));
    await expect(getCatalog()).rejects.toMatchObject({ status: 405, code: "unavailable" });
  });

  it("turns a malformed 200 into bad_response, logging the path only", async () => {
    fetchMock.mockResolvedValue(json({ ...catalog, window_days: "seven" }));
    await expect(getCatalog()).rejects.toMatchObject({ status: 502, code: "bad_response" });
    expect(console.error).toHaveBeenCalledWith("api.bad_response /api/v1/catalog");
  });

  it("logs a bad_response path without its query string", async () => {
    fetchMock.mockResolvedValue(json({ ...availability, hours: "two" }));
    await expect(
      getAvailability({ date: "2026-11-03", sport: "basketball", coverage: "half", hours: 2 }),
    ).rejects.toMatchObject({ status: 502, code: "bad_response" });
    expect(console.error).toHaveBeenCalledWith("api.bad_response /api/v1/availability");
    const logged = vi.mocked(console.error).mock.calls.flat().map(String).join("\n");
    expect(logged).not.toContain("?");
    expect(logged).not.toContain("2026-11-03");
  });

  it("turns a rejected fetch into unavailable", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    await expect(getCatalog()).rejects.toMatchObject({ status: 0, code: "unavailable" });
  });

  it("turns a redirect (rejected under redirect: error) into unavailable", async () => {
    fetchMock.mockRejectedValue(new TypeError("unexpected redirect"));
    await expect(confirmCheckout("cs_abc")).rejects.toMatchObject({
      status: 0,
      code: "unavailable",
    });
    expect(lastCall().init.redirect).toBe("error");
  });

  it("throws without calling fetch when INTERNAL_API_TOKEN is unset", async () => {
    vi.stubEnv("INTERNAL_API_TOKEN", undefined);
    await expect(getCatalog()).rejects.toThrow(/INTERNAL_API_TOKEN/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("throws without calling fetch when the token is too short", async () => {
    vi.stubEnv("INTERNAL_API_TOKEN", "t".repeat(31));
    await expect(getCatalog()).rejects.toThrow(/INTERNAL_API_TOKEN/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("clientIpFrom", () => {
  it("takes the rightmost x-forwarded-for entry, the one Cloud Run appended", () => {
    expect(clientIpFrom(new Headers({ "x-forwarded-for": "1.1.1.1, 2.2.2.2" }))).toBe("2.2.2.2");
    expect(clientIpFrom(new Headers({ "x-forwarded-for": " 2001:db8::1 " }))).toBe("2001:db8::1");
  });

  it("falls back to 0.0.0.0", () => {
    expect(clientIpFrom(new Headers())).toBe("0.0.0.0");
    expect(clientIpFrom(new Headers({ "x-forwarded-for": "1.1.1.1, " }))).toBe("0.0.0.0");
  });
});
