import type { Metadata } from "next";
import { LookupForm } from "@/components/booking/lookup-form";

export const metadata: Metadata = { title: "Find your booking", robots: { index: false } };

export default function BookingLookupPage() {
  return (
    <main className="wrap">
      <p className="eyebrow">Your booking</p>
      <h1 className="disp text-4xl sm:text-5xl">Find your booking</h1>
      <p className="mt-4 max-w-xl">
        Enter the reference you were shown after paying and the email you booked with.
      </p>
      <div className="mt-8 max-w-xl">
        <LookupForm />
      </div>
    </main>
  );
}
