import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { z } from "zod";
import {
  apiErrorBodySchema,
  availabilitySchema,
  bookingCreatedSchema,
  bookingLookupSchema,
  bookingSummarySchema,
  catalogSchema,
  checkoutReleaseSchema,
  checkoutStatusSchema,
} from "../schemas";

// The contract: docs/api/fixtures, which the backend's test_contract.py reads too.
const FIXTURES = fileURLToPath(new URL("../../../../../../docs/api/fixtures/", import.meta.url));

/** Every fixture, by file name. A new fixture must be added here, or the test below fails. */
const SCHEMAS: Record<string, z.ZodType> = {
  "availability.json": availabilitySchema,
  "booking-created.json": bookingCreatedSchema,
  "booking-lookup.json": bookingLookupSchema,
  "catalog.json": catalogSchema,
  "checkout-release.json": checkoutReleaseSchema,
  "checkout-status.json": checkoutStatusSchema,
  "error.json": apiErrorBodySchema,
};

function fixture(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as Record<string, unknown>;
}

const files = readdirSync(FIXTURES)
  .filter((name) => name.endsWith(".json"))
  .sort();

describe("API schemas against docs/api/fixtures", () => {
  it("finds the fixtures", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("maps every fixture to a schema, and every schema to a fixture", () => {
    expect(files).toEqual(Object.keys(SCHEMAS).sort());
  });

  it.each(files)("%s parses with its schema", (name) => {
    const schema = SCHEMAS[name];
    expect(schema, `no schema mapped for ${name}`).toBeDefined();
    const result = schema!.safeParse(fixture(name));
    expect(result.error?.issues ?? []).toEqual([]);
  });

  // The drift guard: the runtime schemas strip unknown keys, so a fixture field a schema lacks
  // would be dropped here and the round trip would fail.
  it.each(files)("%s parses back to itself, with no field stripped", (name) => {
    expect(SCHEMAS[name]!.parse(fixture(name))).toEqual(fixture(name));
  });
});

describe("API schemas", () => {
  const summary = fixture("booking-lookup.json").booking as Record<string, unknown>;

  it("strips a field the contract doesn't have", () => {
    const catalog = catalogSchema.parse({ ...fixture("catalog.json"), extra: 1 });
    expect(catalog).not.toHaveProperty("extra");
    const booking = bookingSummarySchema.parse({ ...summary, email: "ana@example.com" });
    expect(booking).not.toHaveProperty("email");
    expect(booking).toEqual(summary);
  });

  it("takes nullability from the README, not the fixtures", () => {
    for (const key of ["hold_expires_at", "paid_at", "payment_method", "sport", "half"]) {
      expect(bookingSummarySchema.safeParse({ ...summary, [key]: null }).success, key).toBe(true);
    }
    expect(
      bookingSummarySchema.safeParse({
        ...summary,
        hold_expires_at: "2026-10-30T14:20:00+08:00",
        paid_at: "2026-10-30T14:07:12+08:00",
        payment_method: "card",
        coverage: "half",
        half: "B",
      }).success,
    ).toBe(true);
    expect(bookingSummarySchema.safeParse({ ...summary, reference: null }).success).toBe(false);
  });

  it("accepts every checkout status, with a null booking when there is none", () => {
    for (const status of ["not_found", "unavailable"]) {
      expect(checkoutStatusSchema.safeParse({ status, booking: null }).success, status).toBe(true);
    }
    const booking = fixture("checkout-status.json").booking;
    for (const status of ["confirmed", "pending", "expired", "cancelled", "needs_refund"]) {
      expect(checkoutStatusSchema.safeParse({ status, booking }).success, status).toBe(true);
    }
    expect(checkoutStatusSchema.safeParse({ status: "paid", booking }).success).toBe(false);
    for (const status of ["released", "already_paid", "not_found"]) {
      expect(checkoutReleaseSchema.safeParse({ status }).success, status).toBe(true);
    }
  });

  it("requires integer centavos", () => {
    const created = fixture("booking-created.json");
    expect(bookingCreatedSchema.safeParse({ ...created, price_centavos: 1400.5 }).success).toBe(
      false,
    );
    expect(bookingCreatedSchema.safeParse({ ...created, price_centavos: "140000" }).success).toBe(
      false,
    );
  });

  it("parses nested customer field names in errors", () => {
    expect(
      apiErrorBodySchema.safeParse({
        error: "invalid_request",
        fields: ["customer.name", "customer.email", "customer.mobile"],
      }).success,
    ).toBe(true);
    expect(apiErrorBodySchema.safeParse({ error: "slot_taken" }).success).toBe(true);
  });
});
