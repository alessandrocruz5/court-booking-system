import { baseEnvSchema, createEnv } from "@cb/env";
import { z } from "zod";

/** Server-only settings for the backend's storefront API. Neither is ever `NEXT_PUBLIC_`. */
export const apiEnvSchema = baseEnvSchema.extend({
  /** The backend origin, with no trailing slash, e.g. `http://localhost:8000`. */
  API_URL: z.url(),
  /** The shared bearer token, the same value as the backend's. At least 32 characters. */
  INTERNAL_API_TOKEN: z.string().min(32),
});

export type ApiEnv = z.infer<typeof apiEnvSchema>;

/**
 * Read per call, never at module top level: `next build` runs with no environment variables.
 * Throws `EnvValidationError` (naming the keys, never their values) when either is missing.
 */
export function getApiEnv(source?: Record<string, string | undefined>): ApiEnv {
  return createEnv(apiEnvSchema, source);
}
