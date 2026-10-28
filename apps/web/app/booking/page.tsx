import type { Metadata } from "next";
import { LookupForm } from "@/components/booking/lookup-form";

export const metadata: Metadata = { title: "Find your booking", robots: { index: false } };

export default function BookingLookupPage() {
  return (
    <main className="wrap">
      <div className="mx-auto max-w-[640px]">
        <p className="eyebrow">Your booking</p>
        <h1 className="m-0 mb-2.5 text-[clamp(34px,5vw,48px)] leading-[1.1] font-black tracking-[-0.03em] font-stretch-[112%]">
          Find your booking
        </h1>
        <p className="m-0 mb-6 text-[16.5px] leading-[1.55] text-slate-6">
          Enter the reference you got after paying and the email you booked with.
        </p>
        <LookupForm />
      </div>
    </main>
  );
}
