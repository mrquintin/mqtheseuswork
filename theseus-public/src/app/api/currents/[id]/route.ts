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
    return (await (raw as Promise<{ id: string }>));
  }
  return raw as { id: string };
}

export async function GET(req: Request, ctx: Ctx) {
  const params = await resolveParams(ctx);
  const backend = new URL(
    `/v1/currents/${encodeURIComponent(params.id)}`,
    BACKEND,
  );
  const resp = await fetch(backend, {
    headers: forwardHeaders(req),
    cache: "no-store",
  });
  return new Response(await resp.text(), {
    status: resp.status,
    headers: { "content-type": "application/json" },
  });
}
