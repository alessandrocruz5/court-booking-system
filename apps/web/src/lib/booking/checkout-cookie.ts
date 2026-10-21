/**
 * The `cb_checkout` cookie (httpOnly, path `/book`): the visitor's recent checkout sessions, set by
 * `startCheckout` in `./actions.ts` and read by `app/book/{success,cancelled}`. It lives here, not in
 * `actions.ts`, because a `"use server"` file may export only async functions. Pure: no React, no
 * `next/headers`.
 *
 * Format: up to `MAX_CHECKOUTS` entries, newest first, joined by `|`; each is `<reference>.<session>`,
 * e.g. `KC-7Q4M2X.cs_abc|KC-2B9D4F.cs_def`. A bare session ID (`cs_abc`) is the legacy format, read as
 * an entry with no reference. `.` and `|` can't appear in a reference or a session ID, so they are
 * safe separators; a malformed part is dropped. The bound keeps the cookie small and lets a visitor
 * with a few tabs open come back to each one's result.
 *
 * The result pages' `?ref=` only selects among the sessions already in this browser's own cookie,
 * and a `ref` that isn't there selects none of the referenced entries. What a page shows still
 * comes only from the backend's check of that session, so the URL can't change a result.
 */

export const CHECKOUT_COOKIE = "cb_checkout";
export const MAX_CHECKOUTS = 3;

export type CheckoutEntry = { reference: string | null; sessionId: string };

/** `apps/backend/bookings/references.py`: Crockford base32, no I, L, O or U. */
const REFERENCE_RE = /^KC-[0-9A-HJKMNP-TV-Z]{6}$/;
/** Looser than the backend's `^cs_[A-Za-z0-9]+$`, so test IDs such as `cs_test_abc` pass. */
const SESSION_RE = /^cs_\w{1,128}$/;

export function isReference(value: unknown): value is string {
  return typeof value === "string" && REFERENCE_RE.test(value);
}

function isSessionId(value: string): boolean {
  return SESSION_RE.test(value);
}

/**
 * `"KC-AAAAAA.cs_x|KC-BBBBBB.cs_y"` (newest first) → entries; a legacy bare `"cs_x"` → one entry
 * with reference null; malformed parts are dropped.
 */
export function parseCheckouts(value: string | undefined): CheckoutEntry[] {
  if (!value) return [];
  const entries: CheckoutEntry[] = [];
  for (const part of value.split("|")) {
    const dot = part.indexOf(".");
    if (dot === -1) {
      if (isSessionId(part)) entries.push({ reference: null, sessionId: part });
      continue;
    }
    const reference = part.slice(0, dot);
    const sessionId = part.slice(dot + 1);
    if (isReference(reference) && isSessionId(sessionId)) entries.push({ reference, sessionId });
  }
  return entries.slice(0, MAX_CHECKOUTS);
}

function serialize(entries: CheckoutEntry[]): string {
  return entries
    .map(({ reference, sessionId }) => (reference ? `${reference}.${sessionId}` : sessionId))
    .join("|");
}

/** Prepend `entry`, drop any older entry with the same reference or session, keep MAX_CHECKOUTS. */
export function addCheckout(
  value: string | undefined,
  entry: { reference: string; sessionId: string },
): string {
  const older = parseCheckouts(value).filter(
    (e) => e.reference !== entry.reference && e.sessionId !== entry.sessionId,
  );
  return serialize([entry, ...older].slice(0, MAX_CHECKOUTS));
}

/**
 * A well-formed `ref`: that entry's session; if no entry has it, a legacy (reference-null) entry's
 * session if there is one (the rollout window: new backend URL, old web cookie), else undefined.
 * Never another referenced entry. No or malformed `ref`: the newest entry's session (also the
 * legacy value).
 */
export function pickCheckout(value: string | undefined, ref: unknown): string | undefined {
  const entries = parseCheckouts(value);
  if (!isReference(ref)) return entries[0]?.sessionId;
  return (
    entries.find((e) => e.reference === ref)?.sessionId ??
    entries.find((e) => e.reference === null)?.sessionId
  );
}
