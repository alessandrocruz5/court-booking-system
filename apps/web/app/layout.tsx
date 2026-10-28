import type { Metadata } from "next";
import { Archivo, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { TestModeBanner } from "@/components/test-mode-banner";
import { getSiteUrl, HOURS, SITE } from "@/content/site";
import { formatHour } from "@/lib/booking/params";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin", "latin-ext"],
  axes: ["wdth"],
  variable: "--font-archivo",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500", "700"],
  variable: "--font-jetbrains",
});

const title = `${SITE.name} · ${SITE.tagline}`;

// SITE_URL is read per request (connection() opts out of prerendering), never at build time.
export async function generateMetadata(): Promise<Metadata> {
  await connection();
  return {
    metadataBase: new URL(getSiteUrl()),
    title: { default: title, template: `%s · ${SITE.name}` },
    description: SITE.description,
    openGraph: {
      type: "website",
      siteName: SITE.name,
      title,
      description: SITE.description,
      locale: "en_PH",
    },
  };
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${archivo.variable} ${jetbrains.variable}`}>
      <body className="min-h-dvh antialiased">
        <TestModeBanner />
        <header className="sticky top-0 z-20 border-b border-line-soft bg-white">
          <div className="mx-auto flex max-w-[1120px] items-center justify-between gap-4 px-5 py-3.5">
            <Link href="/" className="flex items-center gap-2.5 text-ink no-underline">
              <span
                aria-hidden="true"
                className="grid size-[30px] place-items-center rounded-lg bg-court text-base leading-none font-black text-white font-stretch-[115%]"
              >
                K
              </span>
              <span className="text-[19px] leading-[1.12] font-extrabold tracking-[-0.02em] font-stretch-[112%]">
                {SITE.name}
              </span>
            </Link>
            <nav aria-label="Main" className="flex items-center gap-1.5">
              <Link
                href="/booking"
                className="rounded-lg px-3 py-[9px] text-[15px] font-semibold text-ink-3 no-underline hover:bg-hair"
              >
                Find booking
              </Link>
              <Link
                href="/book"
                className="rounded-lg bg-ink px-4 py-[9px] text-[15px] font-bold text-white no-underline hover:bg-ink-2"
              >
                Book
              </Link>
            </nav>
          </div>
        </header>
        {children}
        <footer className="border-t border-line-soft">
          <div className="mx-auto flex max-w-[1120px] flex-wrap justify-between gap-3 px-5 py-[22px] text-[13.5px] text-slate-5">
            <span>{SITE.name} is a fictional venue. Test mode, no real payments.</span>
            <span>
              Open daily · {formatHour(HOURS.open)} – {formatHour(HOURS.close)}
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
