import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, lookupBooking } from "@/lib/api/client";
import type * as Client from "@/lib/api/client";
import type { BookingSummary } from "@/lib/api/schemas";
import { type LookupState, lookup } from "../lookup";

vi.mock("@/lib/api/client", async (importActual) => {
  // The real ApiError and clientIpFrom; only the network call is faked.
  const actual = await importActual<typeof Client>();
  return { ...actual, lookupBooking: vi.fn() };
});

let requestHeaders = new Headers();

vi.mock("next/headers", () => ({
  headers: vi.fn(async () => requestHeaders),
}));

const lookupBookingMock = vi.mocked(lookupBooking);

const REFERENCE = "KC-7Q4M2X";
const EMAIL = "ana@example.com";

const INITIAL: LookupState = { values: { reference: "", email: "" } };

const BOOKING = {
  reference: REFERENCE,
  status: "confirmed",
} as BookingSummary;

function form(reference: string, email: string): FormData {
  const data = new FormData();
  data.set("reference", reference);
  data.set("email", email);
  return data;
}

const consoleSpies: ReturnType<typeof vi.spyOn>[] = [];

beforeEach(() => {
  requestHeaders = new Headers({ "x-forwarded-for": "198.51.100.7, 203.0.113.10" });
  for (const method of ["log", "info", "warn", "error", "debug"] as const) {
    consoleSpies.push(vi.spyOn(console, method).mockImplementation(() => {}));
  }
});

afterEach(() => {
  lookupBookingMock.mockReset();
  consoleSpies.length = 0;
  vi.restoreAllMocks();
});

describe("lookup validation", () => {
  it("trims and uppercases the reference", async () => {
    lookupBookingMock.mockResolvedValue({ booking: BOOKING });

    const state = await lookup(INITIAL, form(" kc-7q4m2x ", ` ${EMAIL} `));
    expect(lookupBookingMock).toHaveBeenCalledWith({
      reference: REFERENCE,
      email: EMAIL,
      clientIp: "203.0.113.10",
    });
    expect(state.booking).toEqual(BOOKING);
  });

  it("rejects a reference with excluded Crockford letters", async () => {
    const state = await lookup(INITIAL, form("KC-ILOU12", EMAIL));
    expect(state.message).toBeTruthy();
    expect(state.booking).toBeUndefined();
    expect(state.values).toEqual({ reference: "KC-ILOU12", email: EMAIL });
    expect(lookupBookingMock).not.toHaveBeenCalled();
  });

  it("rejects an invalid email", async () => {
    const state = await lookup(INITIAL, form(REFERENCE, "not-an-email"));
    expect(state.message).toBeTruthy();
    expect(lookupBookingMock).not.toHaveBeenCalled();
  });
});

describe("lookup client IP", () => {
  it("passes the rightmost x-forwarded-for entry", async () => {
    requestHeaders = new Headers({ "x-forwarded-for": "10.0.0.1, 192.0.2.1 ,  203.0.113.99 " });
    lookupBookingMock.mockResolvedValue({ booking: BOOKING });

    await lookup(INITIAL, form(REFERENCE, EMAIL));
    expect(lookupBookingMock.mock.lastCall?.[0].clientIp).toBe("203.0.113.99");
  });
});

describe("lookup API errors", () => {
  it.each([
    [new ApiError(404, "not_found"), "No booking matches that reference and email."],
    [new ApiError(429, "rate_limited"), "Too many lookups. Try again in a few minutes."],
    [new ApiError(500, "server_error"), "Lookup is unavailable right now."],
    [new ApiError(0, "unavailable"), "Lookup is unavailable right now."],
    [new TypeError("boom"), "Lookup is unavailable right now."],
  ])("maps %s to its fixed message", async (error, message) => {
    lookupBookingMock.mockRejectedValue(error);

    const state = await lookup(INITIAL, form(REFERENCE, EMAIL));
    expect(state.message).toBe(message);
    expect(state.booking).toBeUndefined();
    expect(state.values).toEqual({ reference: REFERENCE, email: EMAIL });
  });
});

describe("personal data", () => {
  it("never logs the email or the reference", async () => {
    lookupBookingMock.mockRejectedValueOnce(new ApiError(404, "not_found"));
    await lookup(INITIAL, form(REFERENCE, EMAIL));
    lookupBookingMock.mockRejectedValueOnce(new ApiError(429, "rate_limited"));
    await lookup(INITIAL, form(REFERENCE, EMAIL));
    lookupBookingMock.mockRejectedValueOnce(new TypeError(`boom ${EMAIL} ${REFERENCE}`));
    await lookup(INITIAL, form(REFERENCE, EMAIL));
    lookupBookingMock.mockResolvedValueOnce({ booking: BOOKING });
    await lookup(INITIAL, form(REFERENCE, EMAIL));
    await lookup(INITIAL, form(REFERENCE, "not-an-email"));

    const logged = consoleSpies.flatMap((spy) => spy.mock.calls.flat().map(String)).join("\n");
    expect(logged).toContain("not_found");
    expect(logged).not.toContain(EMAIL);
    expect(logged).not.toContain("example.com");
    expect(logged).not.toContain(REFERENCE);
  });
});
