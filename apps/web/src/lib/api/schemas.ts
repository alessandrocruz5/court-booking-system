import { z } from "zod";

/**
 * The storefront API's response bodies, mirroring `docs/api/fixtures/*.json` and the tables in
 * `docs/api/README.md` (nullability comes from the README). A contract change updates the
 * fixtures, both test suites, this file and the README together.
 *
 * Objects strip unknown keys rather than reject them: the backend deploys first, so an additive
 * field must not turn every call into `bad_response`. Drift is caught in `schemas.test.ts` instead,
 * where every fixture must parse back to itself (a field this file lacks would be stripped).
 */

export const sportSchema = z.enum([
  "basketball",
  "volleyball",
  "tennis",
  "badminton",
  "pickleball",
]);
export type Sport = z.infer<typeof sportSchema>;

export const coverageSchema = z.enum(["full", "half"]);
export type Coverage = z.infer<typeof coverageSchema>;

export const courtKindSchema = z.enum(["basketball", "tennis", "multi"]);
export type CourtKind = z.infer<typeof courtKindSchema>;

export const bookingStatusSchema = z.enum([
  "pending",
  "confirmed",
  "expired",
  "cancelled",
  "needs_refund",
]);
export type BookingStatus = z.infer<typeof bookingStatusSchema>;

/** Integer centavos (PHP). */
const centavos = z.int().nonnegative();
/** A local hour, 7 to 23. */
const hour = z.int().min(0).max(23);
/** `YYYY-MM-DD`, a local date. */
const localDate = z.iso.date();
/** ISO-8601 with the venue offset, e.g. `2026-10-30T14:20:00+08:00`. */
const timestamp = z.iso.datetime({ offset: true });

const rateSchema = z.object({ off_peak: centavos, peak: centavos });

export const catalogSchema = z.object({
  venue: z.object({ name: z.string(), time_zone: z.string() }),
  hours: z.object({ open: hour, close: hour }),
  window_days: z.int().positive(),
  max_hours: z.int().positive(),
  hold_minutes: z.int().positive(),
  peak: z.object({ weekdays_from_hour: hour, weekends_all_day: z.boolean() }),
  sports: z.array(
    z.object({
      id: sportSchema,
      label: z.string(),
      court_kind: courtKindSchema,
      court_count: z.int().positive(),
      coverages: z.array(coverageSchema).min(1),
      rates: z.partialRecord(coverageSchema, rateSchema),
    }),
  ),
});
export type Catalog = z.infer<typeof catalogSchema>;

export const availabilitySchema = z.object({
  date: localDate,
  sport: sportSchema,
  coverage: coverageSchema,
  hours: z.int().positive(),
  courts: z.array(
    z.object({
      code: z.string(),
      name: z.string(),
      starts: z.array(z.object({ hour, price_centavos: centavos, peak: z.boolean() })),
    }),
  ),
});
export type Availability = z.infer<typeof availabilitySchema>;

export const bookingCreatedSchema = z.object({
  reference: z.string(),
  checkout_url: z.url(),
  checkout_session_id: z.string(),
  hold_expires_at: timestamp,
  price_centavos: centavos,
});
export type BookingCreated = z.infer<typeof bookingCreatedSchema>;

/** `booking_summary`: no name, email or mobile. */
export const bookingSummarySchema = z.object({
  reference: z.string(),
  status: bookingStatusSchema,
  court: z.object({ code: z.string(), name: z.string() }),
  sport: sportSchema.nullable(),
  coverage: coverageSchema,
  half: z.enum(["A", "B"]).nullable(),
  date: localDate,
  start_hour: hour,
  hours: z.int().positive(),
  price_centavos: centavos,
  hold_expires_at: timestamp.nullable(),
  paid_at: timestamp.nullable(),
  payment_method: z.string().nullable(),
});
export type BookingSummary = z.infer<typeof bookingSummarySchema>;

export const checkoutStatusValueSchema = z.enum([
  "confirmed",
  "pending",
  "needs_refund",
  "not_found",
  "unavailable",
  "expired",
  "cancelled",
]);
export type CheckoutStatusValue = z.infer<typeof checkoutStatusValueSchema>;

export const checkoutStatusSchema = z.object({
  status: checkoutStatusValueSchema,
  booking: bookingSummarySchema.nullable(),
});
export type CheckoutStatus = z.infer<typeof checkoutStatusSchema>;

export const checkoutReleaseSchema = z.object({
  status: z.enum(["released", "already_paid", "not_found"]),
});
export type CheckoutRelease = z.infer<typeof checkoutReleaseSchema>;

export const bookingLookupSchema = z.object({ booking: bookingSummarySchema });
export type BookingLookup = z.infer<typeof bookingLookupSchema>;

/**
 * `{"error": code, "fields"?: [...]}`. `fields` names nested customer fields as `customer.name`,
 * `customer.email` and `customer.mobile`, and a non-object body as `body`.
 */
export const apiErrorBodySchema = z.object({
  error: z.string().min(1),
  fields: z.array(z.string()).optional(),
});
export type ApiErrorBody = z.infer<typeof apiErrorBodySchema>;
