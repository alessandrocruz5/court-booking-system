import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import {
  AvailabilityGrid,
  AvailabilitySkeleton,
  LoadError,
} from "@/components/booking/availability-grid";
import { DateStrip } from "@/components/booking/date-strip";
import { DurationPicker } from "@/components/booking/duration-picker";
import { DetailsForm } from "@/components/booking/details-form";
import { SportPicker } from "@/components/booking/sport-picker";
import { ApiError, getAvailability, getCatalog } from "@/lib/api/client";
import type { Catalog } from "@/lib/api/schemas";
import {
  type BookingParams,
  type RawSearchParams,
  bookingHref,
  formatHour,
  formatPeso,
  manilaToday,
  parseBookingParams,
  windowDates,
} from "@/lib/booking/params";

export const metadata: Metadata = { title: "Book a court" };

// Dynamic: searchParams is a request-time API, and the client reads env per call, never at build.
export default async function BookPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const raw = await searchParams;

  let catalog;
  try {
    catalog = await getCatalog();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    // Keep the visitor's choices in the retry link. Never show the error's detail.
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(raw)) {
      const v = Array.isArray(value) ? value[0] : value;
      if (v !== undefined) query.set(key, v);
    }
    const qs = query.toString();
    return (
      <main className="wrap">
        <StepHeader step="sport" />
        <LoadError href={qs ? `/book?${qs}` : "/book"} />
      </main>
    );
  }

  const today = manilaToday();
  const params = parseBookingParams(raw, catalog, today);
  const date = params.date ?? today;
  const sport = catalog.sports.find((s) => s.id === params.sport);
  const selected =
    sport && params.court !== undefined && params.start !== undefined
      ? { court: params.court, start: params.start }
      : undefined;
  const step = selected ? "details" : sport ? "time" : "sport";

  return (
    <main className="wrap">
      <StepHeader step={step} />
      <div className="mt-6 grid gap-8">
        <SportPicker catalog={catalog} params={params} />
        <DurationPicker params={params} maxHours={catalog.max_hours} />
        <DateStrip
          params={params}
          dates={windowDates(today, catalog.window_days)}
          today={today}
          selected={date}
          weekendsPeak={catalog.peak.weekends_all_day}
        />
        <section aria-labelledby="times-heading">
          <h2 id="times-heading" className="disp text-xl">
            Times
          </h2>
          <div className="mt-3">
            {/* Keyed so the skeleton shows again when a choice changes. */}
            <Suspense
              key={`${params.sport}|${params.coverage}|${params.hours}|${date}`}
              fallback={<AvailabilitySkeleton />}
            >
              <AvailabilityGrid params={params} date={date} />
            </Suspense>
          </div>
        </section>
        {selected && sport ? (
          <section
            aria-labelledby="selected-heading"
            className="rounded-xl border-2 border-court bg-white p-4"
          >
            <h2 id="selected-heading" className="disp text-xl">
              Selected
            </h2>
            {/* Its own boundary: the slot is re-checked against fresh availability. */}
            <Suspense
              key={`${params.sport}|${params.coverage}|${params.hours}|${date}|${selected.court}|${selected.start}`}
              fallback={
                <>
                  <p className="mt-2 mb-0">
                    {sport.label}
                    {sport.coverages.length > 1 ? `, ${params.coverage} court` : ""} · Court{" "}
                    <span className="uppercase">{selected.court}</span>
                  </p>
                  <p className="mt-1 mb-0">
                    {date} · {formatHour(selected.start)}–
                    {formatHour(selected.start + params.hours)} ({params.hours}{" "}
                    {params.hours === 1 ? "hour" : "hours"})
                  </p>
                  <p aria-busy="true" className="mt-3 mb-0 text-sm text-ink/70">
                    Checking that time is still free…
                  </p>
                </>
              }
            >
              <DetailsStep params={params} date={date} sport={sport} />
            </Suspense>
          </section>
        ) : null}
      </div>
    </main>
  );
}

/**
 * The details form, shown only when the selected start is in fresh availability for that court.
 * The price shown comes from that availability; the backend quotes it again on submit.
 */
async function DetailsStep({
  params,
  date,
  sport,
}: {
  params: BookingParams;
  date: string;
  sport: Catalog["sports"][number];
}) {
  const { court, start } = params;
  if (court === undefined || start === undefined) return null;

  let availability;
  try {
    availability = await getAvailability({
      date,
      sport: sport.id,
      coverage: params.coverage,
      hours: params.hours,
    });
  } catch (error) {
    if (error instanceof ApiError) return <LoadError href={bookingHref(params, { date })} />;
    throw error;
  }

  const courtEntry = availability.courts.find((c) => c.code === court);
  const slot = courtEntry?.starts.find((s) => s.hour === start);
  if (!courtEntry || !slot) {
    return (
      <div role="alert" className="mt-2">
        <p className="m-0 font-bold">That time is no longer available.</p>
        <Link
          href={bookingHref(params, { date, court: undefined, start: undefined })}
          className="btn mt-3"
        >
          Pick another time
        </Link>
      </div>
    );
  }

  return (
    <DetailsForm
      selection={{
        court,
        sport: sport.id,
        coverage: params.coverage,
        date,
        start,
        hours: params.hours,
      }}
      summary={{
        courtName: courtEntry.name,
        sportLabel: sport.label,
        coverageLabel:
          sport.coverages.length > 1
            ? params.coverage === "half"
              ? "Half court"
              : "Full court"
            : undefined,
        dateLabel: formatDate(date),
        timeRange: `${formatHour(start)}–${formatHour(start + params.hours)} (${params.hours} ${
          params.hours === 1 ? "hour" : "hours"
        })`,
        price: formatPeso(slot.price_centavos),
      }}
    />
  );
}

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

const STEPS = [
  { id: "sport", label: "Sport" },
  { id: "time", label: "Time" },
  { id: "details", label: "Details" },
] as const;

function StepHeader({ step }: { step: (typeof STEPS)[number]["id"] }) {
  const current = STEPS.findIndex((s) => s.id === step);
  return (
    <header>
      <p className="eyebrow">Book a court</p>
      <h1 className="disp text-4xl sm:text-5xl">Pick your court</h1>
      <nav aria-label="Booking steps" className="mt-4">
        <ol className="m-0 flex list-none flex-wrap items-center gap-2 p-0 text-sm font-bold">
          {STEPS.map((s, i) => (
            <li
              key={s.id}
              aria-current={i === current ? "step" : undefined}
              className={i === current ? "text-court" : "text-ink/60"}
            >
              {i > 0 ? <span aria-hidden="true">→ </span> : null}
              {s.label}
            </li>
          ))}
        </ol>
      </nav>
    </header>
  );
}
