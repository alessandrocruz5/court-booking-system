import Link from "next/link";
import { SITE } from "@/content/site";

// Placeholder hero: the real landing page is built later.
export default function HomePage() {
  return (
    <main className="wrap">
      <p className="eyebrow">Open daily · 7 AM–11 PM</p>
      <h1 className="disp text-5xl sm:text-6xl">{SITE.name}</h1>
      <p className="mt-4 max-w-xl text-lg">{SITE.tagline}</p>
      <div className="row">
        <Link href="/book" className="btn btn-accent">
          Book a court
        </Link>
      </div>
    </main>
  );
}
