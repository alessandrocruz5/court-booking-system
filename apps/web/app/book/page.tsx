import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import {
  AvailabilityGrid,
  AvailabilitySkeleton,
  LoadError,
} from "@/components/booking/availability-grid";
import { BookingSummary, BookingSummaryPending } from "@/components/booking/booking-summary";
import { DateStrip } from "@/components/booking/date-strip";
import { DurationPicker } from "@/components/booking/duration-picker";
import { DetailsForm } from "@/components/booking/details-form";
import { StepCard } from "@/components/booking/step-card";
import { HOLD_MINUTES } from "@/content/site";
import { SportPicker } from "@/components/booking/sport-picker";
import { ApiError, getAvailabilityOnce, getCatalog } from "@/lib/api/client";
import type { Catalog, Sport } from "@/lib/api/schemas";
import {
  type BookingParams,
  type RawSearchParams,
  bookingHref,
  manilaToday,
  parseBookingParams,
  windowDates,
} from "@/lib/booking/params";

export const metadata: Metadata = { title: "Book a court" };

const HEADING = (
  <>
    <p className="eyebrow">Book a court</p>
    <h1 className="m-0 mb-7 text-[clamp(34px,5vw,48px)] leading-[1.1] font-black tracking-[-0.03em] font-stretch-[112%]">
      Pick your court
    </h1>
  </>
);

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
        {HEADING}
        <LoadError href={qs ? `/book?${qs}` : "/book"} />
      </main>
    );
  }

  const today = manilaToday();
  let params = parseBookingParams(raw, catalog, today);
  const date = params.date ?? today;
  const sport = catalog.sports.find((s) => s.id === params.sport);
  if (sport && params.start !== undefined && params.court === undefined) {
    params = await withFirstFreeCourt(params, date, sport.id);
  }
  const selected =
    sport && params.court !== undefined && params.start !== undefined
      ? { court: params.court, start: params.start }
      : undefined;
  const hoursLabel = `${params.hours} ${params.hours === 1 ? "hour" : "hours"}`;

  return (
    <main className="wrap">
      {HEADING}
      <div className="group/book grid grid-cols-1 items-start gap-7 min-[900px]:grid-cols-[minmax(0,1fr)_340px]">
        <div className="grid min-w-0 gap-3.5">
          <StepCard number={1} title="Sport" state={sport ? "done" : "active"}>
            <SportPicker catalog={catalog} params={params} />
          </StepCard>
          <StepCard number={2} title="Day & length" state={sport ? "done" : "idle"}>
            <DateStrip
              params={params}
              dates={windowDates(today, catalog.window_days)}
              today={today}
              selected={date}
              weekendsPeak={catalog.peak.weekends_all_day}
            />
            <DurationPicker params={params} maxHours={catalog.max_hours} />
          </StepCard>
          <StepCard
            number={3}
            title="Start time"
            state={selected ? "done" : sport ? "active" : "idle"}
            right={
              <div className="flex items-center gap-3.5 text-[13px] text-slate-5">
                <span className="flex items-center gap-1.5">
                  <span aria-hidden="true" className="size-2 rounded-full bg-clay" />
                  Peak rate
                </span>
                <span>Prices for {hoursLabel}</span>
              </div>
            }
          >
            {/* Keyed so the skeleton shows again when a choice changes. */}
            <Suspense
              key={`${params.sport}|${params.coverage}|${params.hours}|${date}`}
              fallback={<AvailabilitySkeleton />}
            >
              <AvailabilityGrid params={params} date={date} today={today} hours={catalog.hours} />
            </Suspense>
          </StepCard>
          <StepCard
            number={4}
            title="Your details"
            state={selected ? "active" : "idle"}
            dimmed={!selected}
          >
            {selected && sport ? (
              /* Its own boundary: the slot is re-checked against fresh availability. */
              <Suspense
                key={`${params.sport}|${params.coverage}|${params.hours}|${date}|${selected.court}|${selected.start}`}
                fallback={
                  <p aria-busy="true" className="m-0 text-[15px] text-slate-5">
                    Checking that time is still free…
                  </p>
                }
              >
                <DetailsStep params={params} date={date} sport={sport} />
              </Suspense>
            ) : (
              <p className="m-0 text-[15px] text-slate-5">
                {sport && params.start !== undefined
                  ? "That start time is no longer free. Pick another one."
                  : "Pick a sport, a day and a start time first."}
              </p>
            )}
          </StepCard>
        </div>
        <Suspense
          key={`${params.sport}|${params.coverage}|${params.hours}|${date}|${params.court}|${params.start}`}
          fallback={<BookingSummaryPending catalog={catalog} params={params} date={date} />}
        >
          <BookingSummary catalog={catalog} params={params} date={date} />
        </Suspense>
      </div>
    </main>
  );
}

/**
 * A start with no court (the landing's "Free tonight" links) selects the first court that is free
 * at that hour. If availability can't be loaded, the params are left alone and the grid shows the
 * error.
 */
async function withFirstFreeCourt(
  params: BookingParams,
  date: string,
  sport: Sport,
): Promise<BookingParams> {
  try {
    // Shares the grid's call within this request (same arguments).
    const availability = await getAvailabilityOnce(date, sport, params.coverage, params.hours);
    const first = availability.courts.find((c) => c.starts.some((s) => s.hour === params.start));
    return first ? { ...params, court: first.code } : params;
  } catch (error) {
    if (error instanceof ApiError) return params;
    throw error;
  }
}

/**
 * The details form, shown only when the selected start is in fresh availability for that court.
 * The price shown in the summary comes from that availability; the backend quotes it again on submit.
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
    // Shares the grid's call within this request (same arguments).
    availability = await getAvailabilityOnce(date, sport.id, params.coverage, params.hours);
  } catch (error) {
    if (error instanceof ApiError) return <LoadError href={bookingHref(params, { date })} />;
    throw error;
  }

  const courtEntry = availability.courts.find((c) => c.code === court);
  const slot = courtEntry?.starts.find((s) => s.hour === start);
  if (!courtEntry || !slot) {
    return (
      <div role="alert">
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
      holdMinutes={HOLD_MINUTES}
      selection={{
        court,
        sport: sport.id,
        coverage: params.coverage,
        date,
        start,
        hours: params.hours,
      }}
    />
  );
}
