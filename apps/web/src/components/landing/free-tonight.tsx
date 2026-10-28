import Link from "next/link";
import { connection } from "next/server";
import { SPORT_BG } from "@/content/sports";
import { getAvailabilityOnce } from "@/lib/api/client";
import type { Catalog } from "@/lib/api/schemas";
import { bookingHref, formatHour, manilaToday, windowDates } from "@/lib/booking/params";

/** `Sun 25 Oct`, from a `YYYY-MM-DD` date. */
function formatTonight(date: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).formatToParts(new Date(`${date}T00:00:00Z`));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("weekday")} ${get("day")} ${get("month")}`;
}

/**
 * The hero's "Free tonight" card: per sport, the earliest free one-hour start today, linking
 * straight into /book. A sport whose availability call fails is left out; if nothing loads, the
 * card is not rendered at all (no error copy on the landing). `loadCatalog` is the page's
 * request-scoped catalog call, shared with the rates table.
 */
export async function FreeTonight({ loadCatalog }: { loadCatalog: () => Promise<Catalog> }) {
  // Opt out of prerendering, so the build never calls the API.
  await connection();
  let catalog;
  try {
    catalog = await loadCatalog();
  } catch {
    // An ApiError, or the env error when API_URL / INTERNAL_API_TOKEN are unset. Code only.
    console.error("landing.free_tonight_unavailable");
    return null;
  }

  const today = manilaToday();
  const [, tomorrow = today] = windowDates(today, 2);

  const results = await Promise.allSettled(
    catalog.sports.map((sport) => getAvailabilityOnce(today, sport.id, "full", 1)),
  );
  const rows = catalog.sports.flatMap((sport, i) => {
    const result = results[i];
    if (!result || result.status === "rejected") return [];
    const starts = result.value.courts.flatMap((court) => court.starts);
    const first = starts.reduce<(typeof starts)[number] | undefined>(
      (best, start) => (best === undefined || start.hour < best.hour ? start : best),
      undefined,
    );
    return [{ sport, next: first?.hour, nextPeak: first?.peak ?? false }];
  });
  if (rows.length === 0) {
    console.error("landing.free_tonight_unavailable");
    return null;
  }

  // "Peak rates" follows the earliest free start across sports, by the server's own peak flag.
  const earliest = rows.reduce<(typeof rows)[number] | undefined>(
    (best, row) =>
      row.next !== undefined && (best?.next === undefined || row.next < best.next) ? row : best,
    undefined,
  );
  const peak = earliest?.nextPeak ?? false;

  return (
    <div className="rounded-2xl border border-line-soft bg-white p-[22px] shadow-[0_1px_2px_#0f172a0a,0_12px_32px_-12px_#0f172a1f]">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="m-0 text-[17px] font-extrabold">Free tonight</h2>
        <p className="m-0 text-[13px] text-slate-5">
          {formatTonight(today)}
          {peak ? " · peak rates" : ""}
        </p>
      </div>
      <ul className="m-0 flex list-none flex-col p-0">
        {rows.map(({ sport, next }) => (
          <li key={sport.id}>
            <Link
              href={
                next === undefined
                  ? bookingHref({ coverage: "full", hours: 1 }, { sport: sport.id, date: tomorrow })
                  : bookingHref(
                      { coverage: "full", hours: 1 },
                      { sport: sport.id, date: today, start: next },
                    )
              }
              className="grid grid-cols-[10px_1fr_auto_auto] items-center gap-3 rounded-lg border-t border-hair px-2.5 py-[13px] text-ink no-underline hover:bg-paper"
            >
              <span aria-hidden="true" className={`size-2.5 rounded-[3px] ${SPORT_BG[sport.id]}`} />
              <span className="text-base font-bold">{sport.label}</span>
              {next === undefined ? (
                <span className="text-sm text-slate-4">Full tonight</span>
              ) : (
                <span className="text-sm font-semibold text-court-dark">
                  Next free {formatHour(next)}
                </span>
              )}
              <span aria-hidden="true" className="text-lg text-slate-4">
                ›
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
