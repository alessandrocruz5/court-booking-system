import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createBooking } from "@/lib/api/client";
import type * as Client from "@/lib/api/client";
import type { BookingCreated } from "@/lib/api/schemas";
import { type CheckoutState, startCheckout } from "../actions";

vi.mock("@/lib/api/client", async (importActual) => {
  // The real ApiError and clientIpFrom; only the network call is faked.
  const actual = await importActual<typeof Client>();
  return { ...actual, createBooking: vi.fn() };
});

const cookieSet = vi.fn();
let requestHeaders = new Headers();

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ set: cookieSet })),
  headers: vi.fn(async () => requestHeaders),
}));

// Like the real one, redirect() throws to end the action.
vi.mock("next/navigation", () => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT ${url}`);
  }),
}));

const { redirect } = await import("next/navigation");
const createBookingMock = vi.mocked(createBooking);
const redirectMock = vi.mocked(redirect);

const NAME = "Ana Reyes";
const EMAIL = "ana@example.com";
const MOBILE = "0917 123-4567";

const INITIAL: CheckoutState = { values: { name: "", email: "", mobile: "" } };

const CREATED: BookingCreated = {
  reference: "KC-7Q4M2X",
  checkout_url: "https://checkout.paymongo.com/cs_test_abc#xyz",
  checkout_session_id: "cs_test_abc",
  hold_expires_at: "2026-10-30T14:20:00+08:00",
  price_centavos: 140000,
};

function form(overrides: Record<string, string | undefined> = {}): FormData {
  const fields: Record<string, string | undefined> = {
    name: NAME,
    email: EMAIL,
    mobile: MOBILE,
    consent: "on",
    court: "tn-2",
    sport: "tennis",
    coverage: "full",
    date: "2026-10-31",
    start: "18",
    hours: "2",
    ...overrides,
  };
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined) data.set(key, value);
  }
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
  createBookingMock.mockReset();
  cookieSet.mockReset();
  redirectMock.mockClear();
  consoleSpies.length = 0;
  vi.restoreAllMocks();
});

describe("startCheckout validation", () => {
  it("returns fieldErrors and the values, and never calls createBooking", async () => {
    const state = await startCheckout(
      INITIAL,
      form({ name: " A ", email: "not-an-email", mobile: "12345" }),
    );
    expect(state.fieldErrors).toEqual({
      name: expect.any(String),
      email: expect.any(String),
      mobile: expect.any(String),
    });
    expect(state.values).toEqual({ name: " A ", email: "not-an-email", mobile: "12345" });
    expect(createBookingMock).not.toHaveBeenCalled();
    expect(cookieSet).not.toHaveBeenCalled();
  });

  it("requires consent", async () => {
    const state = await startCheckout(INITIAL, form({ consent: undefined }));
    expect(state.fieldErrors).toEqual({ consent: expect.any(String) });
    expect(createBookingMock).not.toHaveBeenCalled();
  });

  it("rejects a tampered selection with a form-level message", async () => {
    const state = await startCheckout(INITIAL, form({ sport: "chess", start: "abc" }));
    expect(state.fieldErrors).toEqual({});
    expect(state.message).toBeTruthy();
    expect(createBookingMock).not.toHaveBeenCalled();
  });
});

describe("startCheckout success", () => {
  it("sends the cleaned input, sets the httpOnly cookie, then redirects to PayMongo", async () => {
    createBookingMock.mockResolvedValue(CREATED);

    await expect(startCheckout(INITIAL, form({ name: `  ${NAME} ` }))).rejects.toThrow(
      "NEXT_REDIRECT",
    );

    expect(createBookingMock).toHaveBeenCalledWith({
      court: "tn-2",
      sport: "tennis",
      coverage: "full",
      date: "2026-10-31",
      startHour: 18,
      hours: 2,
      customer: { name: NAME, email: EMAIL, mobile: "09171234567" },
      consent: true,
      clientIp: "203.0.113.10",
    });
    expect(cookieSet).toHaveBeenCalledTimes(1);
    expect(cookieSet).toHaveBeenCalledWith(
      "cb_checkout",
      "cs_test_abc",
      expect.objectContaining({ httpOnly: true, path: "/book", sameSite: "lax", maxAge: 86400 }),
    );
    expect(redirectMock).toHaveBeenCalledWith(CREATED.checkout_url);
    expect(cookieSet.mock.invocationCallOrder[0]).toBeLessThan(
      redirectMock.mock.invocationCallOrder[0] ?? 0,
    );
  });

  it("passes the rightmost x-forwarded-for entry as the client IP", async () => {
    requestHeaders = new Headers({ "x-forwarded-for": "10.0.0.1, 192.0.2.1 ,  203.0.113.99 " });
    createBookingMock.mockResolvedValue(CREATED);

    await expect(startCheckout(INITIAL, form())).rejects.toThrow("NEXT_REDIRECT");
    expect(createBookingMock.mock.lastCall?.[0].clientIp).toBe("203.0.113.99");
  });

  it.each([
    "http://checkout.paymongo.com/cs_test_abc",
    "https://checkout.paymongo.com.evil.test/cs_test_abc",
    "https://evil.test/cs_test_abc",
    "https://checkout.paymongo.com:8443/cs_test_abc",
    "https://user@checkout.paymongo.com/cs_test_abc",
  ])("doesn't redirect to %s", async (checkoutUrl) => {
    createBookingMock.mockResolvedValue({ ...CREATED, checkout_url: checkoutUrl });

    const state = await startCheckout(INITIAL, form());
    expect(state.message).toBe("Payments are unavailable right now. Please try again shortly.");
    expect(state.values).toEqual({ name: NAME, email: EMAIL, mobile: MOBILE });
    expect(redirectMock).not.toHaveBeenCalled();
    expect(cookieSet).not.toHaveBeenCalled();
  });
});

describe("startCheckout API errors", () => {
  it("gives slot_taken its fixed message and keeps the values", async () => {
    createBookingMock.mockRejectedValue(new ApiError(409, "slot_taken"));

    const state = await startCheckout(INITIAL, form());
    expect(state).toEqual({
      message: "Someone just booked that time. Pick another slot.",
      values: { name: NAME, email: EMAIL, mobile: MOBILE },
    });
    expect(cookieSet).not.toHaveBeenCalled();
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it.each([
    ["rate_limited", "Too many bookings in progress. Finish or cancel one, then try again."],
    ["too_many_holds", "Too many bookings in progress. Finish or cancel one, then try again."],
    ["payments_unavailable", "Payments are unavailable right now. Please try again shortly."],
    ["unavailable", "Payments are unavailable right now. Please try again shortly."],
    ["outside_window", "Something went wrong. Please try again."],
    ["invalid_request", "Something went wrong. Please try again."],
  ])("maps %s to its fixed message", async (code, message) => {
    createBookingMock.mockRejectedValue(new ApiError(400, code));
    const state = await startCheckout(INITIAL, form());
    expect(state.message).toBe(message);
  });

  it("rethrows anything that isn't an ApiError", async () => {
    createBookingMock.mockRejectedValue(new TypeError("boom"));
    await expect(startCheckout(INITIAL, form())).rejects.toThrow("boom");
  });
});

describe("personal data", () => {
  it("never logs the name, email or mobile", async () => {
    await startCheckout(INITIAL, form({ consent: undefined }));
    createBookingMock.mockRejectedValueOnce(new ApiError(409, "slot_taken"));
    await startCheckout(INITIAL, form());
    createBookingMock.mockResolvedValueOnce({ ...CREATED, checkout_url: "https://evil.test/x" });
    await startCheckout(INITIAL, form());
    createBookingMock.mockResolvedValueOnce(CREATED);
    await expect(startCheckout(INITIAL, form())).rejects.toThrow("NEXT_REDIRECT");

    const logged = consoleSpies.flatMap((spy) => spy.mock.calls.flat().map(String)).join("\n");
    expect(logged).toContain("slot_taken");
    expect(logged).not.toContain(EMAIL);
    expect(logged).not.toContain(NAME);
    expect(logged).not.toContain("0917");
  });
});
