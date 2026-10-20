"use client";

import Link from "next/link";
import { type ReactNode, useActionState } from "react";
import type { Coverage, Sport } from "@/lib/api/schemas";
import { type CheckoutState, startCheckout } from "@/lib/booking/actions";

const FOCUS = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court";
const INPUT = `block min-h-11 w-full rounded-lg border-2 bg-white px-3 text-base text-ink ${FOCUS}`;

const INITIAL: CheckoutState = { values: { name: "", email: "", mobile: "" } };

export type DetailsSelection = {
  court: string;
  sport: Sport;
  coverage: Coverage;
  date: string;
  start: number;
  hours: number;
};

/** Display strings, computed on the server. The backend re-quotes the price on submit. */
export type DetailsSummary = {
  courtName: string;
  sportLabel: string;
  /** `Half court`, or undefined when the sport has only one coverage. */
  coverageLabel?: string;
  dateLabel: string;
  timeRange: string;
  price: string;
};

/** Step 3: the guest's details and consent, then a redirect to PayMongo's test checkout. */
export function DetailsForm({
  selection,
  summary,
}: {
  selection: DetailsSelection;
  summary: DetailsSummary;
}) {
  const [state, formAction, pending] = useActionState(startCheckout, INITIAL);
  const errors = state.fieldErrors ?? {};

  return (
    <form action={formAction} className="mt-2 grid gap-5">
      <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="font-bold">Court</dt>
        <dd className="m-0">{summary.courtName}</dd>
        <dt className="font-bold">Sport</dt>
        <dd className="m-0">
          {summary.sportLabel}
          {summary.coverageLabel ? `, ${summary.coverageLabel.toLowerCase()}` : ""}
        </dd>
        <dt className="font-bold">Date</dt>
        <dd className="m-0">{summary.dateLabel}</dd>
        <dt className="font-bold">Time</dt>
        <dd className="m-0">{summary.timeRange}</dd>
        <dt className="font-bold">Price</dt>
        <dd className="m-0 font-bold">{summary.price}</dd>
      </dl>

      <input type="hidden" name="court" value={selection.court} />
      <input type="hidden" name="sport" value={selection.sport} />
      <input type="hidden" name="coverage" value={selection.coverage} />
      <input type="hidden" name="date" value={selection.date} />
      <input type="hidden" name="start" value={String(selection.start)} />
      <input type="hidden" name="hours" value={String(selection.hours)} />

      {state.message ? (
        <p role="alert" className="m-0 rounded-lg border-2 border-clay p-3 font-bold">
          {state.message}
        </p>
      ) : null}

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

      <div>
        <div className="flex items-start gap-3">
          <input
            id="consent"
            name="consent"
            type="checkbox"
            required
            aria-invalid={errors.consent ? true : undefined}
            aria-describedby={errors.consent ? "consent-error" : undefined}
            className={`mt-1 size-5 shrink-0 accent-court ${FOCUS}`}
          />
          <label htmlFor="consent" className="text-sm">
            I agree to the{" "}
            <Link href="/privacy" className={`font-bold text-court ${FOCUS}`}>
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

      <div>
        <button
          type="submit"
          disabled={pending}
          aria-disabled={pending}
          className="btn btn-accent w-full disabled:cursor-wait disabled:opacity-70 sm:w-auto"
        >
          {pending ? "Holding your slot…" : "Continue to payment"}
        </button>
        <p className="mt-2 mb-0 text-sm text-ink/70">
          You&apos;ll pay on PayMongo&apos;s test checkout. Your slot is held for 20 minutes.
        </p>
      </div>
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
