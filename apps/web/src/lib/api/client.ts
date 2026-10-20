import "server-only";

import type { z } from "zod";
import { getApiEnv } from "./env";
import {
  apiErrorBodySchema,
  availabilitySchema,
  bookingCreatedSchema,
  bookingLookupSchema,
  catalogSchema,
  checkoutReleaseSchema,
  checkoutStatusSchema,
  type Availability,
  type BookingCreated,
  type BookingLookup,
  type Catalog,
  type CheckoutRelease,
  type CheckoutStatus,
  type Coverage,
  type Sport,
} from "./schemas";

/**
 * The typed client for the backend's storefront API (`docs/api/README.md`). Server only: it sends
 * `INTERNAL_API_TOKEN`, so the `server-only` import makes bundling it into a client component a
 * build error. Env is read per call, never at module top level (`next build` has none).
 */

const TIMEOUT_MS = 10_000;

/**
 * A failed API call. `code` is the body's `error` (`slot_taken`, `rate_limited`, ...),
 * `"unavailable"` when the backend couldn't be reached (`status` 0) or answered without an error
 * body, or `"bad_response"` (`status` 502) when a 2xx body doesn't match its schema. The message
 * never includes the request body.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly fields?: string[],
  ) {
    super(`Storefront API error ${status}: ${code}`);
    this.name = "ApiError";
  }
}

type ApiRequest = { method: "GET" } | { method: "POST"; body: Record<string, unknown> };

async function request<T>(path: string, schema: z.ZodType<T>, init: ApiRequest): Promise<T> {
  // Throws before any fetch when API_URL or INTERNAL_API_TOKEN is missing (fail closed).
  const { API_URL, INTERNAL_API_TOKEN } = getApiEnv();

  const headers: Record<string, string> = {
    authorization: `Bearer ${INTERNAL_API_TOKEN}`,
    accept: "application/json",
  };
  if (init.method === "POST") headers["content-type"] = "application/json";

  let response: Response;
  let text: string;
  try {
    response = await fetch(`${API_URL.replace(/\/+$/, "")}${path}`, {
      method: init.method,
      headers,
      body: init.method === "POST" ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    text = await response.text();
  } catch {
    // Network failure, DNS, or the timeout's abort (which also covers reading the body).
    throw new ApiError(0, "unavailable");
  }

  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch {
    json = undefined; // An empty or non-JSON body, e.g. a 405 or a proxy's error page.
  }

  if (!response.ok) {
    const body = apiErrorBodySchema.safeParse(json);
    if (body.success) throw new ApiError(response.status, body.data.error, body.data.fields);
    throw new ApiError(response.status, "unavailable");
  }

  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    // The path only: never the body, which may describe a booking.
    console.error(`api.bad_response ${path}`);
    throw new ApiError(502, "bad_response");
  }
  return parsed.data;
}

export function getCatalog(): Promise<Catalog> {
  return request("/api/v1/catalog", catalogSchema, { method: "GET" });
}

export function getAvailability({
  date,
  sport,
  coverage,
  hours,
}: {
  date: string;
  sport: Sport;
  coverage: Coverage;
  hours: number;
}): Promise<Availability> {
  const query = new URLSearchParams({ date, sport, coverage, hours: String(hours) });
  return request(`/api/v1/availability?${query}`, availabilitySchema, { method: "GET" });
}

export type CreateBookingInput = {
  court: string;
  sport: Sport;
  coverage: Coverage;
  date: string;
  startHour: number;
  hours: number;
  customer: { name: string; email: string; mobile: string };
  consent: boolean;
  /** The visitor's IP, from `clientIpFrom(headers)`. */
  clientIp: string;
};

/** Hold a slot and open a PayMongo test checkout. The server quotes the price. */
export function createBooking(input: CreateBookingInput): Promise<BookingCreated> {
  return request("/api/v1/bookings", bookingCreatedSchema, {
    method: "POST",
    body: {
      court: input.court,
      sport: input.sport,
      coverage: input.coverage,
      date: input.date,
      start_hour: input.startHour,
      hours: input.hours,
      customer: {
        name: input.customer.name,
        email: input.customer.email,
        mobile: input.customer.mobile,
      },
      consent: input.consent,
      client_ip: input.clientIp,
    },
  });
}

/** The success page's check. Payment status comes only from here, never from the URL. */
export function confirmCheckout(checkoutSessionId: string): Promise<CheckoutStatus> {
  return request("/api/v1/checkout/confirm", checkoutStatusSchema, {
    method: "POST",
    body: { checkout_session_id: checkoutSessionId },
  });
}

/** The cancel page: release a pending hold. */
export function releaseCheckout(checkoutSessionId: string): Promise<CheckoutRelease> {
  return request("/api/v1/checkout/release", checkoutReleaseSchema, {
    method: "POST",
    body: { checkout_session_id: checkoutSessionId },
  });
}

export function lookupBooking({
  reference,
  email,
  clientIp,
}: {
  reference: string;
  email: string;
  clientIp: string;
}): Promise<BookingLookup> {
  return request("/api/v1/bookings/lookup", bookingLookupSchema, {
    method: "POST",
    body: { reference, email, client_ip: clientIp },
  });
}

/**
 * The visitor's IP for the backend's per-IP rate limits: the **rightmost** entry of
 * `x-forwarded-for`, trimmed, or `"0.0.0.0"` when there is none.
 *
 * Assumes exactly one trusted proxy in front of Next: Cloud Run's front end, which appends the
 * address it saw to whatever the client sent. Everything to the left of the last entry is
 * client-supplied and could be forged to dodge the limits. If another proxy (a load balancer,
 * a CDN) is ever put in front, this must skip that many entries from the right.
 */
export function clientIpFrom(headers: Headers): string {
  const entries = (headers.get("x-forwarded-for") ?? "").split(",");
  const last = entries[entries.length - 1]?.trim();
  return last || "0.0.0.0";
}
