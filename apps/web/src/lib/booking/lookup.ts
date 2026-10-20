"use server";

import { headers } from "next/headers";
import { z } from "zod";
import { ApiError, clientIpFrom, lookupBooking } from "@/lib/api/client";
import type { BookingSummary } from "@/lib/api/schemas";

export type LookupState = {
  /** The booking that matched. Never holds a name, email or mobile. */
  booking?: BookingSummary;
  /** A fixed message. */
  message?: string;
  /** What the visitor typed, re-shown in the form. Never logged. */
  values: { reference: string; email: string };
};

const REFERENCE_RE = /^KC-[0-9A-HJKMNP-TV-Z]{6}$/;

const formSchema = z.object({
  reference: z.string().trim().toUpperCase().pipe(z.string().regex(REFERENCE_RE)),
  email: z.string().trim().pipe(z.email().max(254)),
});

const INVALID = "Enter your reference (like KC-7Q4M2X) and the email you booked with.";
const NOT_FOUND = "No booking matches that reference and email.";
const RATE_LIMITED = "Too many lookups. Try again in a few minutes.";
const UNAVAILABLE = "Lookup is unavailable right now.";

function text(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value : "";
}

/**
 * The lookup form's action: a reference plus the booking's email, sent to the backend as a POST,
 * so neither ever appears in a URL. Inputs are never logged (RA 10173): failures log only the code.
 */
export async function lookup(_prev: LookupState, formData: FormData): Promise<LookupState> {
  const values = { reference: text(formData, "reference"), email: text(formData, "email") };

  const parsed = formSchema.safeParse(values);
  if (!parsed.success) return { message: INVALID, values };

  try {
    const result = await lookupBooking({
      reference: parsed.data.reference,
      email: parsed.data.email,
      clientIp: clientIpFrom(await headers()),
    });
    return { booking: result.booking, values };
  } catch (error) {
    if (!(error instanceof ApiError)) {
      // Not an API failure (e.g. the env is unset): fixed message, no detail.
      console.error("lookup.failed");
      return { message: UNAVAILABLE, values };
    }
    console.error(`lookup.failed ${error.code}`);
    if (error.code === "not_found") return { message: NOT_FOUND, values };
    if (error.code === "rate_limited") return { message: RATE_LIMITED, values };
    return { message: UNAVAILABLE, values };
  }
}
