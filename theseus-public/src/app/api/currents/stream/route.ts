export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function forwardHeaders(req: Request): Record<string, string> {
  const out: Record<string, string> = {};
  const xff = req.headers.get("x-forwarded-for");
  if (xff) out["x-forwarded-for"] = xff;
  const ua = req.headers.get("user-agent");
  if (ua) out["user-agent"] = ua;
  const clientId = req.headers.get("x-client-id");
  if (clientId) out["x-client-id"] = clientId;
  return out;
}

const BACKEND = process.env.CURRENTS_API_URL ?? "http://127.0.0.1:8088";

export async function GET(req: Request) {
  const backend = new URL("/v1/currents/stream", BACKEND);
  const upstream = await fetch(backend, {
    headers: { Accept: "text/event-stream", ...forwardHeaders(req) },
  });
  if (!upstream.ok || !upstream.body) {
    return new Response(`upstream ${upstream.status}`, {
      status: upstream.status || 502,
    });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
