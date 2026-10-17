/**
 * Liveness only. Deliberately no DB ping: uptime probes must not keep Neon's compute awake.
 */
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" }, { headers: { "cache-control": "no-store" } });
}
