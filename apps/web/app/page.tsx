import Link from "next/link";
import { cache, Suspense } from "react";
import { connection } from "next/server";
import { FreeTonight } from "@/components/landing/free-tonight";
import { FAQ, HOLD_MINUTES, HOURS, MAX_HOURS, SITE, WINDOW_DAYS } from "@/content/site";
import { SPORT_BG } from "@/content/sports";
import { getCatalog } from "@/lib/api/client";
import { formatHour, formatPeso } from "@/lib/booking/params";

// One catalog request per render, shared by Free tonight and the rates table.
const getLandingCatalog = cache(() => getCatalog());

// Dynamic: the rates and Free tonight are fetched per request, and the client reads env per call,
// never at build.
export default function HomePage() {
  return (
    <main>
      <section
        aria-labelledby="hero-heading"
        className="mx-auto grid max-w-[1120px] grid-cols-[repeat(auto-fit,minmax(min(100%,400px),1fr))] items-center gap-10 px-5 pt-14 pb-10"
      >
        <div>
          <p className="eyebrow">
            Open daily · {formatHour(HOURS.open)} – {formatHour(HOURS.close)}
          </p>
          <h1
            id="hero-heading"
            className="m-0 mt-3.5 mb-[18px] text-[clamp(42px,6vw,68px)] leading-[0.98] font-black tracking-[-0.035em] text-balance font-stretch-[112%]"
          >
            {SITE.tagline}
          </h1>
          <p className="m-0 mb-7 max-w-[480px] text-lg leading-[1.55] text-pretty text-slate-6">
            Basketball, volleyball, tennis, badminton and pickleball. Pay online, then show your
            reference at the front desk.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/book" className="btn btn-accent">
              Book a court
            </Link>
            <Link href="/booking" className="btn">
              Find my booking
            </Link>
          </div>
        </div>
        <Suspense fallback={null}>
          <FreeTonight loadCatalog={getLandingCatalog} />
        </Suspense>
      </section>

      <section
        aria-labelledby="rates-heading"
        className="mx-auto flex max-w-[1120px] flex-wrap items-end justify-between gap-x-4 gap-y-[18px] px-5 py-8"
      >
        <h2 id="rates-heading" className="disp m-0 text-3xl font-stretch-[110%]">
          Sports &amp; rates
        </h2>
        <Suspense fallback={<RatesSkeleton />}>
          <Rates />
        </Suspense>
      </section>

      <section aria-labelledby="how-heading" className="mx-auto max-w-[1120px] px-5 py-10">
        <h2 id="how-heading" className="disp m-0 mb-[18px] text-3xl font-stretch-[110%]">
          How it works
        </h2>
        <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(100%,220px),1fr))] gap-3 p-0">
          {[
            ["Pick", "Choose a sport, a day and a time."],
            ["Hold", `We hold your slot for ${HOLD_MINUTES} minutes.`],
            ["Pay", "Pay on PayMongo's test checkout."],
            ["Show your reference", "Bring the KC- reference you get after paying."],
          ].map(([title, text], i) => (
            <li key={title} className="rounded-[14px] border border-line-soft bg-white p-5">
              <span className="block text-[34px] leading-none font-black text-court font-stretch-[115%]">
                {i + 1}
              </span>
              <h3 className="m-0 mt-3.5 mb-1.5 text-lg font-extrabold">{title}</h3>
              <p className="m-0 text-[15px] leading-normal text-slate-6">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section
        aria-labelledby="faq-heading"
        className="mx-auto grid max-w-[1120px] grid-cols-[repeat(auto-fit,minmax(min(100%,320px),1fr))] gap-10 px-5 py-10"
      >
        <div>
          <h2 id="faq-heading" className="disp m-0 mb-3 text-3xl font-stretch-[110%]">
            Questions
          </h2>
          <p className="m-0 max-w-[480px] leading-[1.55] text-slate-6">
            Open daily, {formatHour(HOURS.open)} to {formatHour(HOURS.close)}. Book up to{" "}
            {WINDOW_DAYS} days ahead, for 1 to {MAX_HOURS} hours, starting on the hour.
          </p>
        </div>
        <div className="border-t border-line-soft">
          {FAQ.map((item, i) => (
            <details key={item.question} open={i === 0} className="group border-b border-line-soft">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-[18px] text-base font-bold [&::-webkit-details-marker]:hidden">
                {item.question}
                <span aria-hidden="true" className="text-xl leading-none text-slate-4">
                  <span className="group-open:hidden">+</span>
                  <span className="hidden group-open:inline">−</span>
                </span>
              </summary>
              <p className="m-0 max-w-[560px] pb-[18px] text-[15.5px] leading-normal text-slate-6">
                {item.answer}
              </p>
            </details>
          ))}
        </div>
      </section>

      <section aria-labelledby="owners-heading" className="mx-auto max-w-[1120px] px-5 pt-10 pb-14">
        <div className="flex flex-wrap items-center justify-between gap-6 rounded-[18px] bg-ink p-8 text-paper">
          <div>
            <p className="m-0 mb-3 text-[12.5px] font-bold tracking-[0.14em] text-clay-light uppercase">
              For venue owners
            </p>
            <h2 id="owners-heading" className="m-0 text-[26px] leading-[1.1] font-extrabold">
              See the owner&apos;s side
            </h2>
            <p className="m-0 mt-2.5 max-w-[480px] text-line">
              See what staff see: live schedule, walk-ins, revenue.
            </p>
          </div>
          {/* A route handler redirect: a plain link, never prefetched. */}
          <Link href="/staff" prefetch={false} className="btn btn-accent">
            Open the staff dashboard
          </Link>
        </div>
      </section>
    </main>
  );
}

/** A table row per sport and coverage from the live catalog; any failure falls back to a link. */
async function Rates() {
  // Opt out of prerendering, so the build never calls the API.
  await connection();
  let catalog;
  try {
    catalog = await getLandingCatalog();
  } catch {
    // An ApiError, or the env error when API_URL / INTERNAL_API_TOKEN are unset. Code only.
    console.error("landing.rates_unavailable");
    return (
      <p className="m-0 w-full">
        <Link href="/book" className="font-bold text-court">
          See live rates on the booking page
        </Link>
      </p>
    );
  }

  return (
    <>
      <p className="m-0 flex flex-wrap gap-x-4 text-[13.5px] text-slate-6">
        <span>Per hour</span>
        <span>
          <b className="text-clay">Peak</b> = weekdays from{" "}
          {formatHour(catalog.peak.weekdays_from_hour)}
          {catalog.peak.weekends_all_day ? ", weekends all day" : ""}
        </span>
      </p>
      <div className="w-full overflow-hidden rounded-[14px] border border-line-soft bg-white">
        <table className="w-full table-fixed border-collapse text-left">
          <caption className="sr-only">Hourly rates by sport</caption>
          <thead>
            <tr className="border-b border-line-soft bg-paper text-xs tracking-[0.08em] text-slate-5 uppercase">
              <th scope="col" className="w-[40%] px-3 py-3 font-bold sm:px-5">
                Sport
              </th>
              <th scope="col" className="px-3 py-3 font-bold sm:px-5">
                Courts
              </th>
              <th scope="col" className="px-3 py-3 text-right font-bold sm:px-5">
                Off-peak
              </th>
              <th scope="col" className="px-3 py-3 text-right font-bold sm:px-5">
                Peak
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hair">
            {catalog.sports.flatMap((sport) =>
              sport.coverages.map((coverage) => {
                const rate = sport.rates[coverage];
                if (!rate) return null;
                return (
                  <tr key={`${sport.id}-${coverage}`}>
                    <th scope="row" className="px-3 py-4 text-left font-bold sm:px-5">
                      <span className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-base">
                        <span
                          aria-hidden="true"
                          className={`size-2.5 flex-none rounded-[3px] ${SPORT_BG[sport.id]}`}
                        />
                        {sport.label}
                        {sport.coverages.length > 1 ? (
                          <span className="text-sm font-medium text-slate-5">
                            {coverage === "half" ? "Half court" : "Full court"}
                          </span>
                        ) : null}
                      </span>
                    </th>
                    <td className="px-3 py-4 text-[15px] text-slate-6 sm:px-5">
                      {sport.court_count} {sport.court_count === 1 ? "court" : "courts"}
                    </td>
                    <td className="px-3 py-4 text-right font-semibold tabular-nums sm:px-5">
                      {formatPeso(rate.off_peak)}
                    </td>
                    <td className="px-3 py-4 text-right font-bold text-clay tabular-nums sm:px-5">
                      {formatPeso(rate.peak)}
                    </td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>
      <p className="m-0 w-full px-0.5 text-sm text-slate-5">
        Basketball and volleyball share the same two courts. Badminton and pickleball share 12
        multi-courts.
      </p>
    </>
  );
}

function RatesSkeleton() {
  return (
    <div
      aria-busy="true"
      className="h-72 w-full animate-pulse rounded-[14px] border border-line-soft bg-white"
    />
  );
}
