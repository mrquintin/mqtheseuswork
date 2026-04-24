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

type Ctx =
  | { params: Promise<{ id: string }> }
  | { params: { id: string } };

async function resolveParams(ctx: Ctx): Promise<{ id: string }> {
  const raw = ctx.params as unknown;
  if (raw && typeof (raw as { then?: unknown }).then === "function") {
    return await (raw as Promise<{ id: string }>);
  }
  return raw as { id: string };
}

export async function POST(req: Request, ctx: Ctx) {
  const params = await resolveParams(ctx);
  const backend = new URL(
    `/v1/currents/${encodeURIComponent(params.id)}/follow-up`,
    BACKEND,
  );
  const bodyText = await req.text();
  const upstream = await fetch(backend, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "text/event-stream",
      ...forwardHeaders(req),
    },
    body: bodyText,
  });
  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text(), {
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
