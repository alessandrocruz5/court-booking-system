import type { ReactNode } from "react";

export type StepState = "done" | "active" | "idle";

const CIRCLE: Record<StepState, string> = {
  done: "bg-court text-white",
  active: "bg-ink text-white",
  idle: "bg-line-soft text-slate-5",
};

/**
 * One numbered card of the /book flow. Presentational: the page decides each card's state from the
 * URL params, and passes the card's content as children.
 */
export function StepCard({
  number,
  title,
  state,
  right,
  dimmed = false,
  children,
}: {
  number: number;
  title: string;
  state: StepState;
  /** Shown at the right of the header (wraps under the title on narrow screens). */
  right?: ReactNode;
  /** Fades the card, for a step that can't be used yet. */
  dimmed?: boolean;
  children: ReactNode;
}) {
  const headingId = `step-${number}-heading`;
  return (
    <section
      aria-labelledby={headingId}
      aria-current={state === "active" ? "step" : undefined}
      className={`rounded-2xl border border-line-soft bg-white p-[22px] ${dimmed ? "opacity-60" : ""}`}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2.5">
        <h2
          id={headingId}
          className="m-0 flex items-center gap-2.5 text-[19px] leading-tight font-extrabold"
        >
          <span
            aria-hidden="true"
            className={`grid size-[26px] shrink-0 place-items-center rounded-full text-[13px] font-extrabold ${CIRCLE[state]}`}
          >
            {state === "done" ? "✓" : number}
          </span>
          <span className="sr-only">
            Step {number}
            {state === "done" ? ", done" : ""}:{" "}
          </span>
          {title}
        </h2>
        {right}
      </div>
      {children}
    </section>
  );
}
