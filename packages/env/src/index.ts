import { z } from "zod";

/** Variables every runtime needs. Packages extend this with their own keys. */
export const baseEnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
});

export class EnvValidationError extends Error {
  constructor(public readonly issues: string[]) {
    super(`Invalid environment variables:\n${issues.map((i) => `  - ${i}`).join("\n")}`);
    this.name = "EnvValidationError";
  }
}

/**
 * Parse `source` against `schema` and fail fast: throws once with every
 * invalid/missing key listed, so a misconfigured deploy never boots.
 *
 * Call it per request (or lazily on first use), never at module top level in code `next build`
 * evaluates: the build runs with no environment variables.
 */
export function createEnv<T extends z.ZodType>(
  schema: T,
  source: Record<string, string | undefined> = process.env,
): z.infer<T> {
  const result = schema.safeParse(source);
  if (!result.success) {
    throw new EnvValidationError(
      result.error.issues.map((issue) => `${issue.path.join(".") || "(root)"}: ${issue.message}`),
    );
  }
  return result.data;
}
