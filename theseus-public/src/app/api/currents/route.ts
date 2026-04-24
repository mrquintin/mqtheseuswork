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
  const incoming = new URL(req.url);
  const backend = new URL("/v1/currents" + incoming.search, BACKEND);
  const resp = await fetch(backend, {
    headers: forwardHeaders(req),
    cache: "no-store",
  });
  return new Response(await resp.text(), {
    status: resp.status,
    headers: { "content-type": "application/json" },
  });
}
