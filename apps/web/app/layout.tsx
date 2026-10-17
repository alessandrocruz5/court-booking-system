import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import Link from "next/link";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { TestModeBanner } from "@/components/test-mode-banner";
import { getSiteUrl, SITE } from "@/content/site";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin", "latin-ext"],
  axes: ["wdth"],
  variable: "--font-archivo",
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
    <html lang="en" className={archivo.variable}>
      <body className="min-h-dvh antialiased">
        <TestModeBanner />
        <header className="border-b border-line">
          <div className="mx-auto max-w-5xl px-5 py-4">
            <Link href="/" className="disp text-xl text-ink no-underline">
              {SITE.name}
            </Link>
          </div>
        </header>
        {children}
        <footer className="border-t border-line">
          <p className="mx-auto max-w-5xl px-5 py-6 text-sm text-ink/70">
            {SITE.name} is a fictional venue. {SITE.testModeNotice}.
          </p>
        </footer>
      </body>
    </html>
  );
}
