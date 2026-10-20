import Link from "next/link";
import { Suspense } from "react";
import { connection } from "next/server";
import { FAQ, HOURS, MAX_HOURS, SITE, WINDOW_DAYS } from "@/content/site";
import { getCatalog } from "@/lib/api/client";
import { formatHour, formatPeso } from "@/lib/booking/params";

// Dynamic: the rates are fetched per request, and the client reads env per call, never at build.
export default function HomePage() {
  return (
    <main>
      <section className="wrap" aria-labelledby="hero-heading">
        <p className="eyebrow">
          Open daily · {formatHour(HOURS.open)}–{formatHour(HOURS.close)}
        </p>
        <h1 id="hero-heading" className="disp text-5xl sm:text-6xl">
          {SITE.name}
        </h1>
        <p className="mt-4 max-w-xl text-lg">{SITE.tagline}</p>
        <div className="row items-center">
          <Link href="/book" className="btn btn-accent">
            Book a court
          </Link>
          <span className="rounded-full border-2 border-clay px-3 py-1 text-sm font-bold text-clay">
            Fictional venue
          </span>
        </div>
      </section>

      <section className="wrap pt-0" aria-labelledby="rates-heading">
        <h2 id="rates-heading" className="disp text-3xl">
          Sports &amp; rates
        </h2>
        <Suspense fallback={<RatesSkeleton />}>
          <Rates />
        </Suspense>
      </section>

      <section className="wrap pt-0" aria-labelledby="how-heading">
        <h2 id="how-heading" className="disp text-3xl">
          How it works
        </h2>
        <ol className="m-0 mt-4 grid list-none gap-3 p-0 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Pick", "Choose a sport, a day and a time."],
            ["Hold", "We hold your slot for 20 minutes."],
            ["Pay", "Pay on PayMongo's test checkout."],
            ["Show your reference", "Bring the KC- reference you get after paying."],
          ].map(([title, text], i) => (
            <li key={title} className="rounded-xl border-2 border-line bg-white p-4">
              <p className="eyebrow m-0">Step {i + 1}</p>
              <h3 className="disp m-0 mt-1 text-lg">{title}</h3>
              <p className="mt-2 mb-0 text-sm">{text}</p>
            </li>
          ))}
        </ol>
        <p className="mt-4 mb-0">
          <Link href="/booking" className="font-bold text-court">
            Find a booking
          </Link>
        </p>
      </section>

      <section className="wrap pt-0" aria-labelledby="hours-heading">
        <h2 id="hours-heading" className="disp text-3xl">
          Hours
        </h2>
        <p className="mt-3 mb-0 max-w-xl">
          Open daily, {formatHour(HOURS.open)} to {formatHour(HOURS.close)}. Book up to{" "}
          {WINDOW_DAYS} days ahead, for 1 to {MAX_HOURS} hours, starting on the hour.
        </p>
      </section>

      <section className="wrap pt-0" aria-labelledby="faq-heading">
        <h2 id="faq-heading" className="disp text-3xl">
          Questions
        </h2>
        <div className="mt-4 grid gap-2">
          {FAQ.map((item) => (
            <details key={item.question} className="rounded-xl border-2 border-line bg-white p-4">
              <summary className="cursor-pointer font-bold">{item.question}</summary>
              <p className="mt-2 mb-0">{item.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="wrap pt-0" aria-labelledby="owners-heading">
        <div className="rounded-xl bg-ink p-6 text-paper sm:p-8">
          <p className="eyebrow">For venue owners</p>
          <h2 id="owners-heading" className="disp text-3xl">
            See the owner&apos;s side
          </h2>
          <p className="mt-3 mb-0 max-w-xl">
            See what staff see: live schedule, walk-ins, revenue.
          </p>
          <div className="row">
            {/* A route handler redirect: a plain link, never prefetched. */}
            <Link href="/staff" prefetch={false} className="btn btn-accent">
              Open the staff dashboard
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}

/** A card per sport from the live catalog; any failure falls back to a link to the booking page. */
async function Rates() {
  // Opt out of prerendering, so the build never calls the API.
  await connection();
  let catalog;
  try {
    catalog = await getCatalog();
  } catch {
    // An ApiError, or the env error when API_URL / INTERNAL_API_TOKEN are unset. Code only.
    console.error("landing.rates_unavailable");
    return (
      <p className="mt-4 mb-0">
        <Link href="/book" className="font-bold text-court">
          See live rates on the booking page
        </Link>
      </p>
    );
  }

  const fromHour = catalog.peak.weekdays_from_hour;
  return (
    <>
      <ul className="m-0 mt-4 grid list-none gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {catalog.sports.map((sport) => (
          <li key={sport.id} className="rounded-xl border-2 border-line bg-white p-4">
            <h3 className="disp m-0 text-xl">{sport.label}</h3>
            <p className="mt-1 mb-0 text-sm text-ink/70">
              {sport.court_count} {sport.court_count === 1 ? "court" : "courts"}
            </p>
            <dl className="m-0 mt-3 grid gap-2 text-sm">
              {sport.coverages.map((coverage) => {
                const rate = sport.rates[coverage];
                if (!rate) return null;
                return (
                  <div key={coverage}>
                    {sport.coverages.length > 1 ? (
                      <dt className="font-bold">
                        {coverage === "half" ? "Half court" : "Full court"}
                      </dt>
                    ) : null}
                    <dd className="m-0">
                      {formatPeso(rate.off_peak)} off-peak · {formatPeso(rate.peak)} peak
                      <span className="text-ink/70"> per hour</span>
                    </dd>
                  </div>
                );
              })}
            </dl>
          </li>
        ))}
      </ul>
      <p className="mt-3 mb-0 text-sm text-ink/70">
        Peak is weekdays from {formatHour(fromHour)}
        {catalog.peak.weekends_all_day ? " and all day on weekends" : ""}. Basketball and volleyball
        share the same two courts.
      </p>
    </>
  );
}

function RatesSkeleton() {
  return (
    <div aria-busy="true" className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="h-28 animate-pulse rounded-xl border-2 border-line bg-white" />
      ))}
    </div>
  );
}
