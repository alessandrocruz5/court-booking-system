import { baseEnvSchema, createEnv } from "@cb/env";
import { z } from "zod";

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
