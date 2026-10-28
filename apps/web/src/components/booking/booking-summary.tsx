import { HOLD_MINUTES } from "@/content/site";
import { SPORT_BG } from "@/content/sports";
import { ApiError, getAvailabilityOnce } from "@/lib/api/client";
import type { Catalog } from "@/lib/api/schemas";
import { type BookingParams, formatHour, formatPeso, isWeekend } from "@/lib/booking/params";

type Props = { catalog: Catalog; params: BookingParams; date: string };

/** What fresh availability says about the selected slot. */
type Found = { courtName: string; priceCentavos: number };

const BUTTON =
  "inline-flex items-center justify-center rounded-[10px] font-extrabold disabled:cursor-not-allowed";

/** `Sat 31 Oct`, from a local `YYYY-MM-DD`. */
function formatDate(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)));
}

/**
 * The off-peak and peak lines under the rows, from the catalog's rates and peak rules. Display
 * only: the total shown, and the price charged, are the server's quote.
 */
function priceLines(
  catalog: Catalog,
  sport: Catalog["sports"][number],
  params: BookingParams,
  date: string,
  start: number,
): { label: string; amount: string }[] {
  const rate = sport.rates[params.coverage];
  if (!rate) return [];
  let peakHours = 0;
  for (let hour = start; hour < start + params.hours; hour++) {
    const peak =
      (catalog.peak.weekends_all_day && isWeekend(date)) || hour >= catalog.peak.weekdays_from_hour;
    if (peak) peakHours++;
  }
  const offPeakHours = params.hours - peakHours;
  const lines = [];
  if (offPeakHours > 0) {
    lines.push({
      label: `Off-peak · ${offPeakHours}h × ${formatPeso(rate.off_peak)}`,
      amount: formatPeso(offPeakHours * rate.off_peak),
    });
  }
  if (peakHours > 0) {
    lines.push({
      label: `Peak · ${peakHours}h × ${formatPeso(rate.peak)}`,
      amount: formatPeso(peakHours * rate.peak),
    });
  }
  return lines;
}

/**
 * The "Your booking" aside (wide screens) and bottom bar (under 900px). When a court and start are
 * chosen, the total is the price of that slot in fresh availability, the same call the grid and the
 * details step share. "Continue to payment" submits the details form.
 */
export async function BookingSummary({ catalog, params, date }: Props) {
  const { court, start } = params;
  let found: Found | undefined;
  if (params.sport && court !== undefined && start !== undefined) {
    try {
      const availability = await getAvailabilityOnce(
        date,
        params.sport,
        params.coverage,
        params.hours,
      );
      const entry = availability.courts.find((c) => c.code === court);
      const slot = entry?.starts.find((s) => s.hour === start);
      if (entry && slot) found = { courtName: entry.name, priceCentavos: slot.price_centavos };
    } catch (error) {
      // Without a slot the total stays empty and Continue stays disabled; the details step says why.
      if (!(error instanceof ApiError)) throw error;
    }
  }
  return <SummaryView catalog={catalog} params={params} date={date} found={found} />;
}

/** The same aside and bar while the slot is being checked: no total, Continue disabled. */
export function BookingSummaryPending(props: Props) {
  return <SummaryView {...props} checking />;
}

function SummaryView({
  catalog,
  params,
  date,
  found,
  checking = false,
}: Props & { found?: Found; checking?: boolean }) {
  const sport = catalog.sports.find((s) => s.id === params.sport);
  const { start } = params;
  const hasTime = start !== undefined && params.court !== undefined;
  const timeRange =
    start === undefined ? undefined : `${formatHour(start)} – ${formatHour(start + params.hours)}`;
  const lines =
    sport && found && start !== undefined ? priceLines(catalog, sport, params, date, start) : [];
  const total = found ? formatPeso(found.priceCentavos) : undefined;
  const ready = found !== undefined;

  const rows: [string, string | undefined][] = [
    ["Court", found?.courtName],
    ["Coverage", sport ? (params.coverage === "half" ? "Half court" : "Full court") : undefined],
    ["Date", formatDate(date)],
    ["Time", timeRange],
  ];

  const barSub =
    sport && hasTime && start !== undefined
      ? `${sport.label} · ${formatDate(date)} · ${formatHour(start)}–${formatHour(start + params.hours)}`
      : "Pick a start time";

  return (
    <>
      <aside
        aria-label="Your booking"
        className="sticky top-[84px] hidden overflow-hidden rounded-2xl border border-line-soft bg-white shadow-[0_12px_32px_-16px_#0f172a26] min-[900px]:block"
      >
        <div className="flex items-center justify-between gap-3 border-b border-hair px-[22px] py-5">
          <h2 className="m-0 text-lg font-extrabold">Your booking</h2>
          {sport ? (
            <span className="flex items-center gap-1.5 text-[13px] font-bold text-ink-3">
              <span
                aria-hidden="true"
                className={`size-[9px] rounded-[3px] ${SPORT_BG[sport.id]}`}
              />
              {sport.label}
            </span>
          ) : null}
        </div>
        <dl className="m-0 flex flex-col gap-3 px-[22px] py-[18px]">
          {rows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3 text-[15px]">
              <dt className="text-slate-5">{label}</dt>
              <dd className={`m-0 text-right font-semibold ${value ? "text-ink" : "text-slate-4"}`}>
                {value ?? "—"}
              </dd>
            </div>
          ))}
        </dl>
        {lines.length > 0 ? (
          <div className="flex flex-col gap-1.5 border-t border-dashed border-line-soft px-[22px] py-3.5">
            {lines.map((line) => (
              <p
                key={line.label}
                className="m-0 flex justify-between gap-3 text-sm text-slate-6 tabular-nums"
              >
                <span>{line.label}</span>
                <span>{line.amount}</span>
              </p>
            ))}
          </div>
        ) : null}
        <div className="border-t border-hair bg-paper px-[22px] pt-4 pb-[22px]">
          <p className="m-0 mb-3.5 flex items-baseline justify-between">
            <span className="font-bold">Total</span>
            <span
              className={`text-[28px] leading-[1.1] font-black tabular-nums font-stretch-[110%] ${
                total ? "text-ink" : "text-slate-4"
              }`}
            >
              {total ?? "—"}
            </span>
          </p>
          <ContinueButton enabled={ready} className="w-full px-[22px] py-[15px] text-[16.5px]" />
          <p className="m-0 mt-2.5 text-center text-[13px] leading-normal text-slate-5">
            <Hint sport={sport !== undefined} hasTime={hasTime} ready={ready} checking={checking} />
          </p>
        </div>
      </aside>

      {sport ? (
        <div className="book-bar fixed inset-x-0 bottom-0 z-30 flex items-center gap-3.5 border-t border-line-soft bg-white px-4 py-3 shadow-[0_-8px_24px_-12px_#0f172a33] min-[900px]:hidden">
          <div className="min-w-0 flex-1">
            <p className="m-0 truncate text-[12.5px] text-slate-5">{barSub}</p>
            <p className="m-0 text-[22px] leading-tight font-black tabular-nums">{total ?? "—"}</p>
          </div>
          <ContinueButton enabled={ready} className="shrink-0 px-5 py-3.5 text-base" />
        </div>
      ) : null}
    </>
  );
}

/** Submits the details form from outside it, through `form="details-form"`. */
function ContinueButton({ enabled, className }: { enabled: boolean; className: string }) {
  return (
    <button
      type="submit"
      form="details-form"
      disabled={!enabled}
      className={`${BUTTON} ${className} ${
        enabled ? "bg-court text-white hover:bg-court-dark" : "bg-line-soft text-slate-4"
      }`}
    >
      Continue to payment
    </button>
  );
}

/**
 * The line under the button. Once the slot is confirmed free, the form's own validity picks between
 * "Add your details" and the payment note, in CSS, since the form lives in a client component.
 */
function Hint({
  sport,
  hasTime,
  ready,
  checking,
}: {
  sport: boolean;
  hasTime: boolean;
  ready: boolean;
  checking: boolean;
}) {
  if (!sport) return "Pick a sport to get started.";
  if (checking) return "Checking that time is still free…";
  if (!hasTime || !ready) return "Pick a start time.";
  return (
    <>
      <span className="group-has-[#details-form:invalid]/book:hidden">
        You&apos;ll pay on PayMongo&apos;s test checkout. Your slot is held for {HOLD_MINUTES}{" "}
        minutes.
      </span>
      <span className="hidden group-has-[#details-form:invalid]/book:inline">
        Add your details to continue.
      </span>
    </>
  );
}
