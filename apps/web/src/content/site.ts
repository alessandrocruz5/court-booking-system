import { baseEnvSchema, createEnv } from "@cb/env";
import { z } from "zod";
import { formatHour } from "@/lib/booking/params";

/** Kalaro Courts is fictional. */
export const SITE = {
  name: "Kalaro Courts",
  tagline: "Book a court in under a minute.",
  description:
    "Basketball, volleyball, tennis, badminton and pickleball courts in one fictional Metro Manila complex, open daily 7 AM–11 PM.",
  testModeNotice: "Fictional venue · Test mode, no real payments",
} as const;

const siteEnvSchema = baseEnvSchema.extend({
  /** Public origin, e.g. `https://kalaro-courts.example`. Used for absolute SEO URLs. */
  SITE_URL: z.url(),
});

/**
 * The site's origin without a trailing slash. Read per call, never at module top level:
 * `next build` runs with no environment variables.
 */
export function getSiteUrl(source?: Record<string, string | undefined>): string {
  return createEnv(siteEnvSchema, source).SITE_URL.replace(/\/+$/, "");
}

/** The venue's opening hours, as local hours. Tested against `docs/api/fixtures/catalog.json`. */
export const HOURS = { open: 7, close: 23 } as const;
/** How many days ahead a booking can be made, today included. Tested against the fixture. */
export const WINDOW_DAYS = 7;
/** The longest booking, in hours. Tested against the fixture. */
export const MAX_HOURS = 3;
/** Visitor bookings are anonymized this many days after they end (see `/privacy`). */
export const RETENTION_DAYS = 7;
/** How long a slot is held while the visitor pays, in minutes. Tested against the fixture. */
export const HOLD_MINUTES = 20;
/** Weekday peak pricing starts at this local hour. Tested against the fixture. */
export const PEAK_FROM_HOUR = 17;

const dashboardEnvSchema = baseEnvSchema.extend({
  /** The Django staff dashboard's URL. Only `/staff` reads it. */
  DASHBOARD_URL: z.url(),
});

/**
 * Where `/staff` sends the visitor: the backend's staff dashboard. Read per call, never at module
 * top level: `next build` runs with no environment variables. Throws when `DASHBOARD_URL` is
 * missing or invalid.
 */
export function getDashboardUrl(source?: Record<string, string | undefined>): string {
  return createEnv(dashboardEnvSchema, source).DASHBOARD_URL;
}

/** Landing-page FAQ. Answers must stay true to the backend's rules and to `/privacy`. */
export const FAQ: readonly { question: string; answer: string }[] = [
  {
    question: "How long is my slot held?",
    answer: `Your slot is held for ${HOLD_MINUTES} minutes while you pay. If the hold runs out, the slot is released.`,
  },
  {
    question: "How do I pay?",
    answer:
      "Payment runs through PayMongo in test mode: card, GCash, Maya or GrabPay. No real money moves.",
  },
  {
    question: "How far ahead can I book?",
    answer: `Up to ${WINDOW_DAYS} days ahead, for 1 to ${MAX_HOURS} hours, starting on the hour.`,
  },
  {
    question: "What counts as peak time?",
    answer: `Weekdays from ${formatHour(PEAK_FROM_HOUR)}, and all day on weekends. Everything else is off-peak.`,
  },
  {
    question: "Can I book half a basketball court?",
    answer:
      "Yes, for basketball. Volleyball uses the full court only. Tennis, badminton and pickleball courts are booked whole.",
  },
  {
    question: "How do I find my booking again?",
    answer:
      "Use Find a booking with your reference (it starts with KC-) and the email you booked with. No email or SMS is sent, so keep your reference.",
  },
  {
    question: "Is this a real venue?",
    answer:
      "No. Kalaro Courts is a fictional portfolio demo. It uses dummy data and PayMongo test mode, never real payments.",
  },
];
