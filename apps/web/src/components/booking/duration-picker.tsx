import Link from "next/link";
import { type BookingParams, bookingHref } from "@/lib/booking/params";

/** Step 2: 1 to `maxHours` hours, as links. */
export function DurationPicker({ params, maxHours }: { params: BookingParams; maxHours: number }) {
  const options = Array.from({ length: maxHours }, (_, i) => i + 1);
  return (
    <section aria-labelledby="duration-heading">
      <h2 id="duration-heading" className="disp text-xl">
        Duration
      </h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {options.map((h) => {
          const on = params.hours === h;
          return (
            <Link
              key={h}
              href={bookingHref(params, { hours: h })}
              aria-current={on ? "true" : undefined}
              className={`inline-flex min-h-11 min-w-20 items-center justify-center rounded-lg border-2 px-4 font-bold no-underline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court ${
                on ? "border-court bg-court text-white" : "border-line text-ink hover:bg-line"
              }`}
            >
              {h} {h === 1 ? "hour" : "hours"}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
