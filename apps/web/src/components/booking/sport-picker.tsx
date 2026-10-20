import Link from "next/link";
import type { Catalog, Coverage } from "@/lib/api/schemas";
import { type BookingParams, bookingHref, formatPeso } from "@/lib/booking/params";

const FOCUS = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court";

function fromRate(sport: Catalog["sports"][number]): number {
  return Math.min(...Object.values(sport.rates).map((r) => r.off_peak));
}

const COVERAGE_LABEL: Record<Coverage, string> = { full: "Full court", half: "Half court" };

/** Step 1: one card per sport. Every choice is a plain link. */
export function SportPicker({ catalog, params }: { catalog: Catalog; params: BookingParams }) {
  return (
    <section aria-labelledby="sport-heading">
      <h2 id="sport-heading" className="disp text-xl">
        Sport
      </h2>
      <ul className="m-0 mt-3 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {catalog.sports.map((sport) => {
          const selected = params.sport === sport.id;
          const coverage: Coverage = sport.coverages.includes(params.coverage)
            ? params.coverage
            : "full";
          const toggle = sport.coverages.length > 1;
          return (
            <li
              key={sport.id}
              className={`rounded-xl border-2 bg-white p-4 ${selected ? "border-court" : "border-line"}`}
            >
              <Link
                href={bookingHref(params, { sport: sport.id, coverage })}
                aria-current={selected ? "true" : undefined}
                className={`block min-h-11 rounded-md text-ink no-underline ${FOCUS}`}
              >
                <span className="disp block text-lg">{sport.label}</span>
                <span className="mt-1 block text-sm text-ink/70">
                  {sport.court_count} courts · from {formatPeso(fromRate(sport))}/h
                </span>
              </Link>
              {toggle ? (
                <div
                  role="group"
                  aria-label={`${sport.label} court size`}
                  className="mt-3 flex gap-2"
                >
                  {sport.coverages.map((c) => {
                    const on = selected && coverage === c;
                    return (
                      <Link
                        key={c}
                        href={bookingHref(params, { sport: sport.id, coverage: c })}
                        aria-current={on ? "true" : undefined}
                        className={`inline-flex min-h-11 flex-1 items-center justify-center rounded-lg border-2 px-3 text-sm font-bold no-underline ${FOCUS} ${
                          on
                            ? "border-court bg-court text-white"
                            : "border-line text-ink hover:bg-line"
                        }`}
                      >
                        {c === "full" ? "Full" : "Half"}
                      </Link>
                    );
                  })}
                </div>
              ) : sport.id === "volleyball" ? (
                <p className="mt-3 text-sm font-bold text-ink/70">{COVERAGE_LABEL.full}</p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
