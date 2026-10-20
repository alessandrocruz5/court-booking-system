import type { Metadata } from "next";
import type { ReactNode } from "react";
import { RETENTION_DAYS, SITE } from "@/content/site";

export const metadata: Metadata = { title: "Privacy notice" };

/**
 * The RA 10173 notice. It states what the backend stores and for how long, and nothing more: a
 * change to what is stored or logged updates this page in the same PR.
 */
export default function PrivacyPage() {
  return (
    <main className="wrap">
      <p className="eyebrow">Privacy notice</p>
      <h1 className="disp text-4xl sm:text-5xl">How {SITE.name} handles your data</h1>
      <p className="mt-4 max-w-2xl text-lg">
        This is a notice under the Data Privacy Act of 2012 (RA 10173), in plain language.
      </p>

      <div className="mt-8 grid max-w-2xl gap-8">
        <Section title="Who we are">
          <p>
            {SITE.name} is a fictional sports complex: a portfolio demo. It uses dummy data and
            PayMongo test mode, and it never takes real payments. Nobody here runs a real venue.
          </p>
        </Section>

        <Section title="What we collect, and why">
          <p>To make and show a booking, the app stores:</p>
          <ul>
            <li>your name, email and mobile number;</li>
            <li>the booking details: court, date, time, and the amount;</li>
            <li>the payment reference and payment method; and</li>
            <li>the time you gave your consent.</li>
          </ul>
          <p>
            It does not store card or wallet details. PayMongo handles those on its own checkout. No
            email or SMS is sent, so your contact details are only used to find your booking again.
          </p>
        </Section>

        <Section title="Legal basis: your consent">
          <p>
            We store your details only because you agreed to this notice when you booked. The time
            you agreed is recorded with your booking.
          </p>
        </Section>

        <Section title="Who we share it with">
          <p>
            PayMongo processes the payment, in test mode. We send PayMongo the booking ID, the
            booking reference, the court, sport, date, time and amount, never your name, email or
            mobile. Whatever you enter on PayMongo&apos;s checkout (card or wallet details, billing
            name or email) is handled by PayMongo under its own privacy policy.
          </p>
          <p>
            Your booking is stored with our hosting providers, Neon (database) and Google Cloud
            (Cloud Run), in Singapore.
          </p>
        </Section>

        <Section title="How long we keep it">
          <p>
            {`A nightly job anonymizes a visitor booking once ${RETENTION_DAYS} days have passed since it ended, so within ${RETENTION_DAYS + 1} days. `}
            Your name, email and mobile are removed. The court, time and amount stay, for the
            venue&apos;s statistics. Demo bookings use fake @example.com people.
          </p>
        </Section>

        <Section title="Logs">
          <p>
            The app&apos;s own logs keep the request path without query strings, and no IP address.
            Google Cloud Run&apos;s platform request logs (Cloud Logging) do record the IP address,
            user agent and URL, and keep them for 30 days by default.
          </p>
          <p>
            To limit repeated attempts, the app keeps a one-way (keyed) hash of your IP address,
            never the IP address itself. A nightly job deletes these within a day.
          </p>
        </Section>

        <Section title="Your rights under RA 10173">
          <p>
            You have the right to be informed, to access your data, to object, to correct it, to
            have it erased or blocked, to data portability, to be indemnified for damages, and to
            complain to the National Privacy Commission (privacy.gov.ph).
          </p>
        </Section>

        <Section title="This is a demo">
          <p>
            Please don&apos;t enter details you wouldn&apos;t want a demo to hold. Use a fake name
            and an @example.com email if you like.
          </p>
        </Section>
      </div>
    </main>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="[&_p]:mt-3 [&_p]:mb-0 [&_ul]:mt-3 [&_ul]:mb-0 [&_ul]:list-disc [&_ul]:pl-6">
      <h2 className="disp m-0 text-2xl">{title}</h2>
      {children}
    </section>
  );
}
