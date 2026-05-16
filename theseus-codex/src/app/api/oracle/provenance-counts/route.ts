import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = (
  process.env.ORACLE_API_URL ??
  process.env.CURRENTS_API_URL ??
  "http://127.0.0.1:8088"
).replace(/\/+$/, "");

/**
 * Proxy for the Oracle provenance-counts endpoint (prompt 09).
 * The Oracle client reads this on mount to populate the count chips
 * next to each provenance checkbox.
 */
export async function GET(_req: NextRequest) {
  try {
    const upstream = await fetch(`${BACKEND}/v1/oracle/provenance-counts`, {
      cache: "no-store",
    });
    const body = await upstream.text();
    return new Response(body, {
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
