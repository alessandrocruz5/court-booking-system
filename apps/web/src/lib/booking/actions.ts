"use server";

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";
import { ApiError, clientIpFrom, createBooking, releaseCheckout } from "@/lib/api/client";
import { coverageSchema, sportSchema } from "@/lib/api/schemas";
import { addCheckout, CHECKOUT_COOKIE, isReference, pickCheckout } from "./checkout-cookie";

export type CheckoutField = "name" | "email" | "mobile" | "consent";

export type CheckoutState = {
  /** One fixed message per invalid visible field. */
  fieldErrors?: Partial<Record<CheckoutField, string>>;
  /** A form-level message: an API error, or a selection that no longer validates. */
  message?: string;
  /** What the visitor typed, re-shown in the form. Never logged. */
  values: { name: string; email: string; mobile: string };
};

const MOBILE_RE = /^(\+63|0)9\d{9}$/;
const COURT_RE = /^[a-z0-9][a-z0-9-]{0,31}$/i;
const SMALL_INT_RE = /^\d{1,2}$/;

const smallInt = z.string().regex(SMALL_INT_RE).transform(Number);

const formSchema = z.object({
  name: z.string().trim().min(2).max(80),
  email: z.string().trim().pipe(z.email().max(254)),
  mobile: z
    .string()
    .transform((value) => value.replace(/[\s-]/g, ""))
    .pipe(z.string().regex(MOBILE_RE)),
  consent: z.literal("on"),
  court: z.string().regex(COURT_RE),
  sport: sportSchema,
  coverage: coverageSchema,
  date: z.iso.date(),
  start: smallInt.pipe(z.int().min(0).max(23)),
  hours: smallInt.pipe(z.int().min(1)),
});

const FIELD_MESSAGES: Record<CheckoutField, string> = {
  name: "Enter your name (2 to 80 characters).",
  email: "Enter a valid email address.",
  mobile: "Enter a Philippine mobile number, like 0917 123 4567.",
  consent: "Please agree to the privacy notice to continue.",
};

/** The backend's `invalid_request` names for the visible customer fields. */
const API_FIELDS = new Map<string, CheckoutField>([
  ["customer.name", "name"],
  ["customer.email", "email"],
  ["customer.mobile", "mobile"],
]);

const SELECTION_MESSAGE = "That time is no longer available. Pick another slot.";
const SLOT_TAKEN = "Someone just booked that time. Pick another slot.";
const TOO_MANY = "Too many bookings in progress. Finish or cancel one, then try again.";
const UNAVAILABLE = "Payments are unavailable right now. Please try again shortly.";
const GENERIC = "Something went wrong. Please try again.";

function messageFor(code: string): string {
  switch (code) {
    case "slot_taken":
      return SLOT_TAKEN;
    case "rate_limited":
    case "too_many_holds":
      return TOO_MANY;
    case "payments_unavailable":
    case "unavailable":
      return UNAVAILABLE;
    default:
      return GENERIC;
  }
}

/**
 * The backend's `invalid_request` field names as the form's errors: a customer field gets its own
 * fixed message; anything else (`court`, `start_hour`, `body`, ...) is the selection's.
 */
function apiFieldErrors(fields: string[]): Pick<CheckoutState, "fieldErrors" | "message"> {
  const fieldErrors: Partial<Record<CheckoutField, string>> = {};
  let selectionFailed = false;
  for (const name of fields) {
    const field = API_FIELDS.get(name);
    if (field) fieldErrors[field] = FIELD_MESSAGES[field];
    else selectionFailed = true;
  }
  return { fieldErrors, message: selectionFailed ? SELECTION_MESSAGE : undefined };
}

/** Only a top-level redirect to PayMongo's hosted checkout, over https, on its exact host. */
function isPayMongoCheckout(value: string): boolean {
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      url.host === "checkout.paymongo.com" &&
      url.username === "" &&
      url.password === ""
    );
  } catch {
    return false;
  }
}

function text(formData: FormData, key: string): string | undefined {
  const value = formData.get(key);
  return typeof value === "string" ? value : undefined;
}

/**
 * The details form's action: hold the slot and open a PayMongo test checkout, then redirect there.
 * The backend re-validates everything and quotes the price; nothing here sets one. Form values are
 * never logged (RA 10173): failures log only the error code.
 */
export async function startCheckout(
  _prev: CheckoutState,
  formData: FormData,
): Promise<CheckoutState> {
  const values = {
    name: text(formData, "name") ?? "",
    email: text(formData, "email") ?? "",
    mobile: text(formData, "mobile") ?? "",
  };

  const parsed = formSchema.safeParse({
    name: values.name,
    email: values.email,
    mobile: values.mobile,
    consent: text(formData, "consent"),
    court: text(formData, "court"),
    sport: text(formData, "sport"),
    coverage: text(formData, "coverage"),
    date: text(formData, "date"),
    start: text(formData, "start"),
    hours: text(formData, "hours"),
  });

  if (!parsed.success) {
    const failed = new Set(parsed.error.issues.map((issue) => String(issue.path[0])));
    const fieldErrors: Partial<Record<CheckoutField, string>> = {};
    for (const field of Object.keys(FIELD_MESSAGES) as CheckoutField[]) {
      if (failed.has(field)) fieldErrors[field] = FIELD_MESSAGES[field];
    }
    const selectionFailed = [...failed].some((key) => !(key in FIELD_MESSAGES));
    return { fieldErrors, message: selectionFailed ? SELECTION_MESSAGE : undefined, values };
  }

  const input = parsed.data;
  const clientIp = clientIpFrom(await headers());

  let created;
  try {
    created = await createBooking({
      court: input.court,
      sport: input.sport,
      coverage: input.coverage,
      date: input.date,
      startHour: input.start,
      hours: input.hours,
      customer: { name: input.name, email: input.email, mobile: input.mobile },
      consent: true,
      clientIp,
    });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.code === "invalid_request" && error.fields?.includes("client_ip")) {
      // Our forwarded IP, not the visitor's input: the field name only, never its value.
      console.error("checkout.create_failed invalid_request client_ip");
      return { message: UNAVAILABLE, values };
    }
    console.error(`checkout.create_failed ${error.code}`);
    if (error.code === "invalid_request" && error.fields?.length) {
      return { ...apiFieldErrors(error.fields), values };
    }
    return { message: messageFor(error.code), values };
  }

  // Checked before the cookie is set, so a session the visitor can't reach is never stored.
  if (!isPayMongoCheckout(created.checkout_url)) {
    console.error("checkout.bad_checkout_url");
    // Best effort: free the slot this visitor can't pay for, rather than leave it held.
    try {
      await releaseCheckout(created.checkout_session_id);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      console.error(`checkout.release_failed ${error.code}`);
    }
    return { message: UNAVAILABLE, values };
  }

  const store = await cookies();
  store.set(
    CHECKOUT_COOKIE,
    addCheckout(store.get(CHECKOUT_COOKIE)?.value, {
      reference: created.reference,
      sessionId: created.checkout_session_id,
    }),
    {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/book",
      maxAge: 86_400,
    },
  );

  // Outside any try/catch: redirect() throws to end the action.
  redirect(created.checkout_url);
}

/**
 * The cancel page's "Release my hold" button, shown instead of releasing when that page was loaded
 * by a prefetch or prerender. The form's `ref` only picks one of this browser's own cookie entries
 * (no or a malformed `ref`: the newest); the session ID always comes from the cookie. It releases
 * that hold, then reloads the cancel page for the same `ref`, whose own release is idempotent
 * (`released` again, or `already_paid`) and shows the result; a failure there shows its fixed copy.
 * Logs only the error code.
 */
export async function releaseHold(formData: FormData): Promise<void> {
  const ref = formData.get("ref");
  const checkoutSessionId = pickCheckout((await cookies()).get(CHECKOUT_COOKIE)?.value, ref);
  if (checkoutSessionId) {
    try {
      await releaseCheckout(checkoutSessionId);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      console.error(`checkout.release_failed ${error.code}`);
    }
  }

  // Outside any try/catch: redirect() throws to end the action.
  redirect(isReference(ref) ? `/book/cancelled?ref=${ref}` : "/book/cancelled");
}
