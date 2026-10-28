"use client";

import { useEffect, useState } from "react";

/** How long the label reads "Copied" before it goes back to "Copy". */
export const COPIED_MS = 2000;

/**
 * Copies a booking reference to the clipboard. The label becomes "Copied" for 2 s, announced
 * politely to screen readers. If the clipboard is unavailable (an insecure context, or permission
 * denied), nothing changes: the reference is on screen to copy by hand.
 */
export function CopyReference({ reference }: { reference: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(reference);
      setCopied(true);
    } catch {
      // No clipboard: leave the label as it is.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex min-h-11 cursor-pointer items-center focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court rounded-lg border-[1.5px] border-ink-3 bg-transparent px-3.5 text-sm font-bold text-line-soft hover:border-slate-4"
    >
      <span aria-live="polite">{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}
