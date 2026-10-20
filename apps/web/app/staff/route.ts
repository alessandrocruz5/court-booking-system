import { getDashboardUrl } from "@/content/site";

/** Read per request: `DASHBOARD_URL` is never needed at build time. */
export const dynamic = "force-dynamic";

/** Sends owners to the Django staff dashboard (a fresh sign-in there). */
export function GET() {
  let url: string;
  try {
    url = getDashboardUrl();
  } catch {
    return new Response("Staff dashboard isn't configured.", {
      status: 500,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }
  return Response.redirect(url, 307);
}
