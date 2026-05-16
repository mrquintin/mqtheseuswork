import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = (
  process.env.ORACLE_API_URL ??
  process.env.CURRENTS_API_URL ??
  "http://127.0.0.1:8088"
).replace(/\/+$/, "");

/**
 * Proxy for the Oracle ask endpoint (prompt 09).
 * The page-side client posts the question + ProvenanceFilter; we
 * forward as-is to the FastAPI service.
 */
export async function POST(req: NextRequest) {
  let body: string;
  try {
    body = await req.text();
  } catch {
    return new Response(JSON.stringify({ error: "bad_request" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }
  try {
    const upstream = await fetch(`${BACKEND}/v1/oracle/ask`, {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json" },
      body,
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: "upstream_unavailable", detail: String(error) }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }
}
