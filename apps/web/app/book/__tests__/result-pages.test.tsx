import { readFileSync } from "node:fs";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, confirmCheckout, releaseCheckout } from "@/lib/api/client";
import type * as Client from "@/lib/api/client";
import type { CheckoutStatus } from "@/lib/api/schemas";
import CancelledPage from "../cancelled/page";
import SuccessPage from "../success/page";

vi.mock("@/lib/api/client", async (importActual) => {
  // The real ApiError; only the network calls are faked.
  const actual = await importActual<typeof Client>();
  return { ...actual, confirmCheckout: vi.fn(), releaseCheckout: vi.fn() };
});

let cookieValue: string | undefined;
let requestHeaders = new Headers();

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) =>
      name === "cb_checkout" && cookieValue !== undefined ? { value: cookieValue } : undefined,
  })),
  headers: vi.fn(async () => requestHeaders),
}));

// Read at run time, not imported: docs/ isn't in the web image's build context.
const confirmed = JSON.parse(
  readFileSync(
    new URL("../../../../../docs/api/fixtures/checkout-status.json", import.meta.url),
    "utf8",
  ),
) as CheckoutStatus;

const confirmMock = vi.mocked(confirmCheckout);
const releaseMock = vi.mocked(releaseCheckout);

/** Calls a page the way Next would (no search params unless given), and renders it. */
async function render(page: unknown, props?: Record<string, unknown>): Promise<string> {
  const element = await (page as (props: unknown) => Promise<ReactElement>)(
    props ?? withSearchParams({}),
  );
  return renderToStaticMarkup(element);
}

function withSearchParams(params: Record<string, string | string[]>) {
  return { searchParams: Promise.resolve(params) };
}

const REF_A = "KC-AAAAAA";
const REF_B = "KC-BBBBBB";
/** Two checkouts in one browser: B (newest) then A. */
const TWO_CHECKOUTS = `${REF_B}.cs_b|${REF_A}.cs_a`;

const forgedSearchParams = {
  searchParams: Promise.resolve({ status: "confirmed", reference: "KC-FORGED" }),
};

const consoleSpies: ReturnType<typeof vi.spyOn>[] = [];

beforeEach(() => {
  cookieValue = undefined;
  requestHeaders = new Headers();
  for (const method of ["log", "info", "warn", "error", "debug"] as const) {
    consoleSpies.push(vi.spyOn(console, method).mockImplementation(() => {}));
  }
});

afterEach(() => {
  confirmMock.mockReset();
  releaseMock.mockReset();
  consoleSpies.length = 0;
  vi.restoreAllMocks();
});

function logged(): string {
  return consoleSpies.flatMap((spy) => spy.mock.calls.flat().map(String)).join("\n");
}

describe("/book/success", () => {
  it("without a cookie, renders not_found and never calls confirmCheckout", async () => {
    const html = await render(SuccessPage);
    expect(html).toContain("Nothing to show yet.");
    expect(html).toContain("Paid in another app or browser?");
    expect(html).toContain('href="/booking"');
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it("ignores searchParams: a forged status=confirmed changes nothing without a cookie", async () => {
    const html = await render(SuccessPage, forgedSearchParams);
    expect(html).toContain("Nothing to show yet.");
    expect(html).not.toContain("KC-FORGED");
    expect(html).not.toContain("You&#x27;re booked.");
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it("ignores a forged status/reference with a cookie: only the backend's answer counts", async () => {
    cookieValue = "cs_x";
    confirmMock.mockResolvedValue({ ...confirmed, status: "expired" });

    const html = await render(SuccessPage, forgedSearchParams);
    expect(confirmMock).toHaveBeenCalledWith("cs_x");
    expect(html).toContain("Your hold has ended.");
    expect(html).not.toContain("KC-FORGED");
    expect(html).not.toContain("You&#x27;re booked.");
  });

  it("confirms the session in the cb_checkout cookie and shows the reference", async () => {
    cookieValue = "cs_x";
    confirmMock.mockResolvedValue(confirmed);

    const html = await render(SuccessPage);
    expect(confirmMock).toHaveBeenCalledWith("cs_x");
    expect(html).toContain("Payment received");
    expect(html).toContain(confirmed.booking!.reference);
  });

  it("never says a copy was sent: no email is sent", async () => {
    cookieValue = "cs_x";
    confirmMock.mockResolvedValue(confirmed);

    const html = await render(SuccessPage);
    expect(html).toContain("You&#x27;re booked.");
    expect(html).not.toContain("sent to");
  });

  it("renders expired as a hold that may still go through", async () => {
    cookieValue = "cs_x";
    confirmMock.mockResolvedValue({ ...confirmed, status: "expired" });

    const html = await render(SuccessPage);
    expect(html).toContain("Your hold has ended.");
    expect(html).toContain("may still go through");
  });

  it("maps an ApiError to the unavailable copy, logging only the code", async () => {
    cookieValue = "cs_x";
    confirmMock.mockRejectedValue(new ApiError(0, "unavailable"));

    const html = await render(SuccessPage);
    expect(html).toContain("We couldn&#x27;t check right now.");
    expect(logged()).toBe("checkout.confirm_failed unavailable");
    expect(logged()).not.toContain("cs_x");
  });

  it("with ?ref= of the older entry, confirms that entry's session", async () => {
    cookieValue = TWO_CHECKOUTS;
    confirmMock.mockResolvedValue({ ...confirmed, status: "pending" });

    const html = await render(SuccessPage, withSearchParams({ ref: REF_A }));
    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(confirmMock).toHaveBeenCalledWith("cs_a");
    expect(html).toContain(`href="/book/success?ref=${REF_A}"`);
  });

  it("with a valid ref that isn't in the cookie, renders not_found and never calls confirmCheckout", async () => {
    cookieValue = TWO_CHECKOUTS;

    const html = await render(SuccessPage, withSearchParams({ ref: "KC-CCCCCC" }));
    expect(html).toContain("Nothing to show yet.");
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it("without a ref, confirms the newest entry", async () => {
    cookieValue = TWO_CHECKOUTS;
    confirmMock.mockResolvedValue({ ...confirmed, status: "pending" });

    const html = await render(SuccessPage);
    expect(confirmMock).toHaveBeenCalledWith("cs_b");
    expect(html).toContain('href="/book/success"');
  });

  it("still confirms a legacy bare cookie, with or without a ref", async () => {
    cookieValue = "cs_legacy";
    confirmMock.mockResolvedValue(confirmed);

    expect(await render(SuccessPage, withSearchParams({ ref: REF_A }))).toContain(
      "Payment received",
    );
    expect(await render(SuccessPage)).toContain("Payment received");
    expect(confirmMock.mock.calls).toEqual([["cs_legacy"], ["cs_legacy"]]);
  });

  it("renders needs_refund without naming a cause", async () => {
    cookieValue = "cs_x";
    confirmMock.mockResolvedValue({ status: "needs_refund", booking: null });

    const html = await render(SuccessPage);
    expect(html).toContain("Refund due");
    expect(html).toContain("Your booking didn&#x27;t go through.");
    expect(html).toContain("cancelled or its slot was taken");
    expect(html).toContain("refund you (test mode)");
    expect(html).not.toContain("hold expired");
  });
});

describe("/book/cancelled", () => {
  it("without a cookie, never calls releaseCheckout", async () => {
    const html = await render(CancelledPage, forgedSearchParams);
    expect(releaseMock).not.toHaveBeenCalled();
    expect(html).toContain("Your hold was released.");
  });

  it("releases the hold in the cookie on a normal GET", async () => {
    cookieValue = "cs_x";
    releaseMock.mockResolvedValue({ status: "released" });

    const html = await render(CancelledPage);
    expect(releaseMock).toHaveBeenCalledWith("cs_x");
    expect(html).toContain("Your hold was released.");
  });

  it("maps already_paid to its copy", async () => {
    cookieValue = "cs_x";
    releaseMock.mockResolvedValue({ status: "already_paid" });

    const html = await render(CancelledPage);
    expect(html).toContain("This booking is already paid.");
  });

  it("maps an ApiError to the unavailable copy, logging only the code", async () => {
    cookieValue = "cs_x";
    releaseMock.mockRejectedValue(new ApiError(503, "unavailable"));

    const html = await render(CancelledPage);
    expect(html).toContain("We couldn&#x27;t check right now.");
    expect(logged()).toBe("checkout.release_failed unavailable");
  });

  it.each([
    ["sec-purpose", "prefetch;prerender"],
    ["sec-purpose", "prefetch"],
    ["purpose", "prefetch"],
  ])("on a speculative load (%s: %s), renders the release button instead", async (name, value) => {
    cookieValue = "cs_x";
    requestHeaders = new Headers({ [name]: value });

    const html = await render(CancelledPage);
    expect(releaseMock).not.toHaveBeenCalled();
    expect(html).toContain("<form");
    expect(html).toContain("Release my hold");
    expect(html).not.toContain("Your hold was released.");
    expect(html).not.toContain('name="ref"');
  });

  it("with ?ref= of A, releases A's session only", async () => {
    cookieValue = TWO_CHECKOUTS;
    releaseMock.mockResolvedValue({ status: "released" });

    const html = await render(CancelledPage, withSearchParams({ ref: REF_A }));
    expect(releaseMock).toHaveBeenCalledTimes(1);
    expect(releaseMock).toHaveBeenCalledWith("cs_a");
    expect(html).toContain("Your hold was released.");
  });

  it("with a valid ref that isn't in the cookie, never calls releaseCheckout", async () => {
    cookieValue = TWO_CHECKOUTS;

    const html = await render(CancelledPage, withSearchParams({ ref: "KC-CCCCCC" }));
    expect(releaseMock).not.toHaveBeenCalled();
    expect(html).toContain("Your hold was released.");
  });

  it("keeps the ref on See your booking and Check again", async () => {
    cookieValue = TWO_CHECKOUTS;
    releaseMock.mockResolvedValueOnce({ status: "already_paid" });
    const paid = await render(CancelledPage, withSearchParams({ ref: REF_A }));
    expect(paid).toContain(`href="/book/success?ref=${REF_A}"`);

    releaseMock.mockRejectedValueOnce(new ApiError(503, "unavailable"));
    const unavailable = await render(CancelledPage, withSearchParams({ ref: REF_A }));
    expect(unavailable).toContain(`href="/book/cancelled?ref=${REF_A}"`);
  });

  it("on a speculative load with ?ref=, the release form carries the ref", async () => {
    cookieValue = TWO_CHECKOUTS;
    requestHeaders = new Headers({ "sec-purpose": "prefetch" });

    const html = await render(CancelledPage, withSearchParams({ ref: REF_A }));
    expect(releaseMock).not.toHaveBeenCalled();
    expect(html).toContain(`<input type="hidden" name="ref" value="${REF_A}"/>`);
  });
});
