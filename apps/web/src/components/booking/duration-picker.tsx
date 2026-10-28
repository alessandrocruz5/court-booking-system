import Link from "next/link";
import { type BookingParams, bookingHref } from "@/lib/booking/params";

/** The length control: 1 to `maxHours` hours as a segmented row of links. Rendered inside the "Day & length" card. */
export function DurationPicker({ params, maxHours }: { params: BookingParams; maxHours: number }) {
  const options = Array.from({ length: maxHours }, (_, i) => i + 1);
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3.5">
      <span id="length-label" className="text-sm font-bold text-ink-3">
        Length
      </span>
      <div
        role="group"
        aria-labelledby="length-label"
        className="flex gap-1 rounded-[10px] bg-hair p-1"
      >
        {options.map((h) => {
          const on = params.hours === h;
          return (
            <Link
              key={h}
              href={bookingHref(params, { hours: h })}
              aria-current={on ? "true" : undefined}
              className={`inline-flex min-h-11 items-center rounded-[7px] px-3 py-[9px] text-[15px] font-bold no-underline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-court min-[420px]:px-[18px] ${
                on
                  ? "bg-white text-ink shadow-[0_1px_3px_#0f172a26]"
                  : "text-slate-5 hover:text-ink"
              }`}
            >
              {h} {h === 1 ? "hour" : "hours"}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
