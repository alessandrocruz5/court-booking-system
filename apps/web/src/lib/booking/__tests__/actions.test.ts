import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createBooking, releaseCheckout } from "@/lib/api/client";
import type * as Client from "@/lib/api/client";
import type { BookingCreated } from "@/lib/api/schemas";
import { type CheckoutState, releaseHold, startCheckout } from "../actions";

vi.mock("@/lib/api/client", async (importActual) => {
  // The real ApiError and clientIpFrom; only the network call is faked.
  const actual = await importActual<typeof Client>();
  return { ...actual, createBooking: vi.fn(), releaseCheckout: vi.fn() };
});

const cookieSet = vi.fn();
let cookieValue: string | undefined;
let requestHeaders = new Headers();

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    set: cookieSet,
    get: (name: string) =>
      name === "cb_checkout" && cookieValue !== undefined ? { value: cookieValue } : undefined,
  })),
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
const releaseCheckoutMock = vi.mocked(releaseCheckout);
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
  releaseCheckoutMock.mockReset();
  cookieSet.mockReset();
  cookieValue = undefined;
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
      "KC-7Q4M2X.cs_test_abc",
      expect.objectContaining({ httpOnly: true, path: "/book", sameSite: "lax", maxAge: 86400 }),
    );
    expect(redirectMock).toHaveBeenCalledWith(CREATED.checkout_url);
    expect(cookieSet.mock.invocationCallOrder[0]).toBeLessThan(
      redirectMock.mock.invocationCallOrder[0] ?? 0,
    );
  });

  it("adds the new entry first and drops the oldest when the cookie already holds 3", async () => {
    cookieValue = "KC-AAAAAA.cs_test_a|KC-BBBBBB.cs_test_b|KC-CCCCCC.cs_test_c";
    createBookingMock.mockResolvedValue(CREATED);

    await expect(startCheckout(INITIAL, form())).rejects.toThrow("NEXT_REDIRECT");
    expect(cookieSet).toHaveBeenCalledWith(
      "cb_checkout",
      "KC-7Q4M2X.cs_test_abc|KC-AAAAAA.cs_test_a|KC-BBBBBB.cs_test_b",
      expect.objectContaining({ httpOnly: true, path: "/book", sameSite: "lax", maxAge: 86400 }),
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
  ])("doesn't redirect to %s, and releases the hold it just made", async (checkoutUrl) => {
    createBookingMock.mockResolvedValue({ ...CREATED, checkout_url: checkoutUrl });
    releaseCheckoutMock.mockResolvedValue({ status: "released" });

    const state = await startCheckout(INITIAL, form());
    expect(state.message).toBe("Payments are unavailable right now. Please try again shortly.");
    expect(state.values).toEqual({ name: NAME, email: EMAIL, mobile: MOBILE });
    expect(releaseCheckoutMock).toHaveBeenCalledTimes(1);
    expect(releaseCheckoutMock).toHaveBeenCalledWith("cs_test_abc");
    expect(redirectMock).not.toHaveBeenCalled();
    expect(cookieSet).not.toHaveBeenCalled();
  });

  it("still returns the unavailable message when releasing a bad-URL hold fails", async () => {
    createBookingMock.mockResolvedValue({ ...CREATED, checkout_url: "https://evil.test/x" });
    releaseCheckoutMock.mockRejectedValue(new ApiError(0, "unavailable"));

    const state = await startCheckout(INITIAL, form());
    expect(state.message).toBe("Payments are unavailable right now. Please try again shortly.");
    expect(releaseCheckoutMock).toHaveBeenCalledWith("cs_test_abc");
    expect(console.error).toHaveBeenCalledWith("checkout.bad_checkout_url");
    expect(console.error).toHaveBeenCalledWith("checkout.release_failed unavailable");
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

  it("maps invalid_request customer fields to their field errors and keeps the values", async () => {
    createBookingMock.mockRejectedValue(
      new ApiError(400, "invalid_request", ["customer.name", "customer.email", "customer.mobile"]),
    );
    const state = await startCheckout(INITIAL, form());
    expect(state).toEqual({
      fieldErrors: {
        name: "Enter your name (2 to 80 characters).",
        email: "Enter a valid email address.",
        mobile: "Enter a Philippine mobile number, like 0917 123 4567.",
      },
      message: undefined,
      values: { name: NAME, email: EMAIL, mobile: MOBILE },
    });
  });

  it.each([["court"], ["start_hour"], ["body"]])(
    "maps an invalid_request %s to the selection message",
    async (field) => {
      createBookingMock.mockRejectedValue(new ApiError(400, "invalid_request", [field]));
      const state = await startCheckout(INITIAL, form());
      expect(state.fieldErrors).toEqual({});
      expect(state.message).toBe("That time is no longer available. Pick another slot.");
    },
  );

  it("maps an invalid_request client_ip to the unavailable message and logs the field name only", async () => {
    createBookingMock.mockRejectedValue(new ApiError(400, "invalid_request", ["client_ip"]));
    const state = await startCheckout(INITIAL, form());
    expect(state.fieldErrors).toBeUndefined();
    expect(state.message).toBe("Payments are unavailable right now. Please try again shortly.");
    expect(console.error).toHaveBeenCalledWith("checkout.create_failed invalid_request client_ip");
  });

  it("maps mixed invalid_request fields to both", async () => {
    createBookingMock.mockRejectedValue(
      new ApiError(400, "invalid_request", ["date", "customer.email", "constructor"]),
    );
    const state = await startCheckout(INITIAL, form());
    expect(state.fieldErrors).toEqual({ email: "Enter a valid email address." });
    expect(state.message).toBe("That time is no longer available. Pick another slot.");
  });
});

function releaseForm(ref?: string): FormData {
  const data = new FormData();
  if (ref !== undefined) data.set("ref", ref);
  return data;
}

describe("releaseHold", () => {
  const COOKIE = "KC-7Q4M2X.cs_test_abc|KC-AAAAAA.cs_test_a|KC-BBBBBB.cs_test_b";

  it("releases the entry named by ref, then reloads the cancel page for that ref", async () => {
    cookieValue = COOKIE;
    releaseCheckoutMock.mockResolvedValue({ status: "released" });

    await expect(releaseHold(releaseForm("KC-AAAAAA"))).rejects.toThrow(
      "NEXT_REDIRECT /book/cancelled?ref=KC-AAAAAA",
    );
    expect(releaseCheckoutMock).toHaveBeenCalledTimes(1);
    expect(releaseCheckoutMock).toHaveBeenCalledWith("cs_test_a");
    expect(redirectMock).toHaveBeenCalledWith("/book/cancelled?ref=KC-AAAAAA");
  });

  it("without a ref, releases the newest entry and reloads the plain cancel page", async () => {
    cookieValue = COOKIE;
    releaseCheckoutMock.mockResolvedValue({ status: "released" });

    await expect(releaseHold(releaseForm())).rejects.toThrow("NEXT_REDIRECT /book/cancelled");
    expect(releaseCheckoutMock).toHaveBeenCalledWith("cs_test_abc");
    expect(redirectMock).toHaveBeenCalledWith("/book/cancelled");
  });

  it("with a malformed ref, releases the newest entry and drops the ref from the redirect", async () => {
    cookieValue = COOKIE;
    releaseCheckoutMock.mockResolvedValue({ status: "released" });

    await expect(releaseHold(releaseForm("../evil"))).rejects.toThrow(
      "NEXT_REDIRECT /book/cancelled",
    );
    expect(releaseCheckoutMock).toHaveBeenCalledWith("cs_test_abc");
    expect(redirectMock).toHaveBeenCalledWith("/book/cancelled");
  });

  it("with a ref not in the cookie, releases nothing", async () => {
    cookieValue = COOKIE;

    await expect(releaseHold(releaseForm("KC-ZZZZZZ"))).rejects.toThrow(
      "NEXT_REDIRECT /book/cancelled?ref=KC-ZZZZZZ",
    );
    expect(releaseCheckoutMock).not.toHaveBeenCalled();
  });

  it("still releases a legacy bare cookie", async () => {
    cookieValue = "cs_test_abc";
    releaseCheckoutMock.mockResolvedValue({ status: "released" });

    await expect(releaseHold(releaseForm())).rejects.toThrow("NEXT_REDIRECT /book/cancelled");
    expect(releaseCheckoutMock).toHaveBeenCalledWith("cs_test_abc");
    expect(redirectMock).toHaveBeenCalledWith("/book/cancelled");
  });

  it("without a cookie, never calls the backend", async () => {
    await expect(releaseHold(releaseForm())).rejects.toThrow("NEXT_REDIRECT /book/cancelled");
    expect(releaseCheckoutMock).not.toHaveBeenCalled();
  });

  it("logs only the code of an ApiError, then still reloads the cancel page", async () => {
    cookieValue = "cs_test_abc";
    releaseCheckoutMock.mockRejectedValue(new ApiError(0, "unavailable"));

    await expect(releaseHold(releaseForm())).rejects.toThrow("NEXT_REDIRECT /book/cancelled");
    const logged = consoleSpies.flatMap((spy) => spy.mock.calls.flat().map(String)).join("\n");
    expect(logged).toBe("checkout.release_failed unavailable");
  });

  it("rethrows anything that isn't an ApiError", async () => {
    cookieValue = "cs_test_abc";
    releaseCheckoutMock.mockRejectedValue(new TypeError("boom"));
    await expect(releaseHold(releaseForm())).rejects.toThrow("boom");
    expect(redirectMock).not.toHaveBeenCalled();
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
