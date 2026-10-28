import Link from "next/link";
import { SPORT_BG } from "@/content/sports";
import type { Catalog, Coverage } from "@/lib/api/schemas";
import { type BookingParams, bookingHref, formatPeso } from "@/lib/booking/params";

const FOCUS = "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court";

type CatalogSport = Catalog["sports"][number];

function fromRate(sport: CatalogSport): number {
  return Math.min(...Object.values(sport.rates).map((r) => r.off_peak));
}

const COVERAGE_LABEL: Record<Coverage, string> = { full: "Full court", half: "Half court" };

/** `₱1,200 – ₱1,600 / hour`, from the catalog's off-peak and peak rates for one coverage. */
function coverageSub(sport: CatalogSport, coverage: Coverage): string {
  const rate = sport.rates[coverage];
  if (!rate) return "";
  const range = `${formatPeso(rate.off_peak)} – ${formatPeso(rate.peak)} / hour`;
  return coverage === "half" ? `Half A or B · ${range}` : range;
}

/** Step 1: one tile per sport, then the court size for a sport that offers more than one. Every choice is a plain link. */
export function SportPicker({ catalog, params }: { catalog: Catalog; params: BookingParams }) {
  const chosen = catalog.sports.find((s) => s.id === params.sport);
  return (
    <>
      <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2.5 p-0">
        {catalog.sports.map((sport) => {
          const selected = params.sport === sport.id;
          const coverage: Coverage = sport.coverages.includes(params.coverage)
            ? params.coverage
            : "full";
          return (
            <li key={sport.id}>
              <Link
                href={bookingHref(params, { sport: sport.id, coverage })}
                aria-current={selected ? "true" : undefined}
                className={`flex h-full min-h-11 flex-col gap-1 rounded-xl border-2 p-3.5 text-ink no-underline ${FOCUS} ${
                  selected
                    ? "border-court bg-court-tint"
                    : "border-line-soft bg-white hover:border-court"
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`mb-2 block h-1 w-[22px] rounded-xs ${SPORT_BG[sport.id]}`}
                />
                <span className="text-[16.5px] font-extrabold">{sport.label}</span>
                <span className="text-[13.5px] text-slate-5">
                  {sport.court_count} courts · from {formatPeso(fromRate(sport))}/h
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      {chosen && chosen.coverages.length > 1 ? (
        <div
          role="group"
          aria-labelledby="coverage-label"
          className="mt-4 border-t border-hair pt-4"
        >
          <p id="coverage-label" className="m-0 mb-2.5 text-sm font-bold text-ink-3">
            {chosen.label} coverage
          </p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-2.5">
            {chosen.coverages.map((c) => {
              const on = params.coverage === c;
              return (
                <Link
                  key={c}
                  href={bookingHref(params, { sport: chosen.id, coverage: c })}
                  aria-current={on ? "true" : undefined}
                  className={`flex min-h-11 items-center gap-3 rounded-xl border-2 px-3.5 py-3 text-ink no-underline ${FOCUS} ${
                    on
                      ? "border-court bg-court-tint"
                      : "border-line-soft bg-white hover:border-court"
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`grid size-[18px] shrink-0 place-items-center rounded-full border-2 ${
                      on ? "border-court" : "border-line"
                    }`}
                  >
                    <span className={`size-2 rounded-full ${on ? "bg-court" : "bg-transparent"}`} />
                  </span>
                  <span className="flex flex-col gap-0.5">
                    <span className="font-bold">{COVERAGE_LABEL[c]}</span>
                    <span className="text-[13px] text-slate-5">{coverageSub(chosen, c)}</span>
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      ) : null}
    </>
  );
}
