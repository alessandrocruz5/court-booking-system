import type { MetadataRoute } from "next";
import { getSiteUrl } from "@/content/site";

// SITE_URL is read per request, never at build time.
export const dynamic = "force-dynamic";

// Each crawl of the booking and staff pages wakes the backend and Neon, so they are disallowed.
export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl();
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/book", "/booking", "/staff"] },
    host: siteUrl,
  };
}
