"use client";

import Link from "next/link";
import { type ReactNode, useActionState } from "react";
import type { Coverage, Sport } from "@/lib/api/schemas";
import { type CheckoutState, startCheckout } from "@/lib/booking/actions";
import { SubmitOverlay } from "./submit-overlay";

const FOCUS = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court";
const INPUT = `block min-h-11 w-full rounded-[10px] border-[1.5px] bg-white px-3.5 py-3 text-base text-ink ${FOCUS}`;

const INITIAL: CheckoutState = { values: { name: "", email: "", mobile: "" } };

export type DetailsSelection = {
  court: string;
  sport: Sport;
  coverage: Coverage;
  date: string;
  start: number;
  hours: number;
};

/**
 * Step 4: the guest's details and consent. The submit button is the summary's "Continue to payment"
 * (it points here through `form="details-form"`), and the action then redirects to PayMongo's test
 * checkout. The server re-quotes the price on submit.
 */
export function DetailsForm({
  selection,
  holdMinutes,
}: {
  selection: DetailsSelection;
  /** `HOLD_MINUTES`, passed from the server page so `site.ts` stays out of the client bundle. */
  holdMinutes: number;
}) {
  const [state, formAction, pending] = useActionState(startCheckout, INITIAL);
  const errors = state.fieldErrors ?? {};

  return (
    <form
      id="details-form"
      action={formAction}
      // Continue lives outside the form, so it can't be disabled while pending: drop a second submit.
      onSubmit={(event) => {
        if (pending) event.preventDefault();
      }}
      className="grid gap-4"
    >
      <input type="hidden" name="court" value={selection.court} />
      <input type="hidden" name="sport" value={selection.sport} />
      <input type="hidden" name="coverage" value={selection.coverage} />
      <input type="hidden" name="date" value={selection.date} />
      <input type="hidden" name="start" value={String(selection.start)} />
      <input type="hidden" name="hours" value={String(selection.hours)} />

      {state.message ? (
        <p
          role="alert"
          className="m-0 rounded-[10px] border border-warn-line bg-warn-bg p-3 font-bold text-warn-ink"
        >
          {state.message}
        </p>
      ) : null}

      {/* Disabled while the action runs, so a second Enter can't submit twice. */}
      <fieldset disabled={pending} className="m-0 grid min-w-0 gap-4 border-0 p-0">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3.5">
          <div className="col-span-full">
            <Field id="name" label="Full name" error={errors.name}>
              <input
                id="name"
                name="name"
                type="text"
                autoComplete="name"
                required
                maxLength={80}
                defaultValue={state.values.name}
                aria-invalid={errors.name ? true : undefined}
                aria-describedby={errors.name ? "name-error" : undefined}
                className={`${INPUT} ${errors.name ? "border-clay" : "border-line"}`}
              />
            </Field>
          </div>

          <Field id="email" label="Email" error={errors.email}>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              defaultValue={state.values.email}
              aria-invalid={errors.email ? true : undefined}
              aria-describedby={errors.email ? "email-error" : undefined}
              className={`${INPUT} ${errors.email ? "border-clay" : "border-line"}`}
            />
          </Field>

          <Field id="mobile" label="Mobile number" error={errors.mobile}>
            <input
              id="mobile"
              name="mobile"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="0917 123 4567"
              required
              maxLength={20}
              defaultValue={state.values.mobile}
              aria-invalid={errors.mobile ? true : undefined}
              aria-describedby={errors.mobile ? "mobile-error" : undefined}
              className={`${INPUT} ${errors.mobile ? "border-clay" : "border-line"}`}
            />
          </Field>
        </div>

        <div>
          <div className="flex items-start gap-3">
            <input
              id="consent"
              name="consent"
              type="checkbox"
              required
              aria-invalid={errors.consent ? true : undefined}
              aria-describedby={errors.consent ? "consent-error" : undefined}
              className={`mt-0.5 size-5 shrink-0 accent-court ${FOCUS}`}
            />
            <label htmlFor="consent" className="text-[14.5px] leading-normal text-ink-3">
              I agree to the{" "}
              <Link href="/privacy" className={`font-bold text-court-dark ${FOCUS}`}>
                privacy notice
              </Link>{" "}
              and to Kalaro Courts storing my name, email and mobile for this booking.
            </label>
          </div>
          {errors.consent ? (
            <p id="consent-error" className="mt-1 mb-0 text-sm font-bold text-clay">
              {errors.consent}
            </p>
          ) : null}
        </div>
      </fieldset>

      {/* Beside the form on wide screens, the summary's hint says this; below 900px there is no summary. */}
      <p className="m-0 text-[13px] text-slate-5 min-[900px]:hidden">
        You&apos;ll pay on PayMongo&apos;s test checkout. Your slot is held for {holdMinutes}{" "}
        minutes.
      </p>

      <SubmitOverlay holdMinutes={holdMinutes} />
    </form>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-bold">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="mt-1 mb-0 text-sm font-bold text-clay">
          {error}
        </p>
      ) : null}
    </div>
  );
}
