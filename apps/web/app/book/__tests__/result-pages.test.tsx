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

/** Calls a page the way Next would, optionally with props it must ignore, and renders it. */
async function render(page: unknown, props?: Record<string, unknown>): Promise<string> {
  const element = await (page as (props: unknown) => Promise<ReactElement>)(props ?? {});
  return renderToStaticMarkup(element);
}

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

  it("confirms the session in the cb_checkout cookie and shows the reference", async () => {
    cookieValue = "cs_x";
    confirmMock.mockResolvedValue(confirmed);

    const html = await render(SuccessPage);
    expect(confirmMock).toHaveBeenCalledWith("cs_x");
    expect(html).toContain("Booking confirmed");
    expect(html).toContain(confirmed.booking!.reference);
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
    ["next-router-prefetch", "1"],
  ])("on a speculative load (%s: %s), renders the release button instead", async (name, value) => {
    cookieValue = "cs_x";
    requestHeaders = new Headers({ [name]: value });

    const html = await render(CancelledPage);
    expect(releaseMock).not.toHaveBeenCalled();
    expect(html).toContain("<form");
    expect(html).toContain("Release my hold");
    expect(html).not.toContain("Your hold was released.");
  });
});
