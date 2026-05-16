import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ALGORITHMS_BACKEND = (
  process.env.ALGORITHMS_API_URL ??
  process.env.FORECASTS_API_URL ??
  process.env.CURRENTS_API_URL ??
  "http://127.0.0.1:8088"
).replace(/\/+$/, "");

/**
 * SSE bridge to the FastAPI `/v1/algorithms/stream` endpoint.
 *
 * The Next.js route is the public touch-point; the in-process bus
 * lives in the Python service. We forward the request as-is,
 * including the `elevated=1` flag the operator surface uses to
 * subscribe to pause / unpause frames.
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const upstream = new URL(`${ALGORITHMS_BACKEND}/v1/algorithms/stream`);
  upstream.search = url.search;

  let response: Response;
  try {
    response = await fetch(upstream.toString(), {
      method: "GET",
      cache: "no-store",
      redirect: "manual",
      signal: req.signal,
      headers: {
        accept: "text/event-stream",
      },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: "upstream_unavailable",
        detail: error instanceof Error ? error.message : String(error),
      }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    return new Response(text || JSON.stringify({ error: "upstream_error" }), {
      status: response.status || 502,
      headers: {
        "content-type":
          response.headers.get("content-type") ?? "application/json",
      },
    });
  }

  return new Response(response.body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    },
  });
}
