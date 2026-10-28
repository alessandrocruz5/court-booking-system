"use client";

import { useFormStatus } from "react-dom";

/**
 * A scrim over the page while the checkout form is submitting (the slot is being held and the
 * visitor is sent to PayMongo's test checkout). Render it inside the `<form>`: `useFormStatus`
 * reports that form's pending state.
 */
export function SubmitOverlay({ holdMinutes }: { holdMinutes: number }) {
  const { pending } = useFormStatus();
  return (
    <div role="status" aria-live="polite">
      {pending ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[#0f172acc] p-5">
          <div className="w-full max-w-[360px] rounded-2xl bg-white p-7 text-center shadow-[0_12px_32px_-8px_#0f172a66]">
            <span
              aria-hidden="true"
              className="mx-auto mb-4 block size-9 animate-spin rounded-full border-4 border-line-soft border-t-court motion-reduce:animate-none"
            />
            <p className="m-0 text-lg font-extrabold">Slot held for {holdMinutes} minutes</p>
            <p className="m-0 mt-1.5 text-[15px] text-slate-6">
              Taking you to PayMongo&apos;s test checkout…
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
