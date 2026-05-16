import { NextResponse, type NextRequest } from "next/server";

import { getFounder } from "@/lib/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Thin proxy backing the public `/knowledge-graph` page. Forwards GET
 * queries to the FastAPI surface at `/v1/knowledge-graph` and POSTs
 * (edge-reasoning, rebuild) to the matching write endpoints.
 *
 * The page is single-tenant in spirit — the org id is resolved from
 * the founder's auth session, falling back to PUBLIC_ORGANIZATION_ID
 * for anonymous reads.
 */

const BACKEND = (
  process.env.CURRENTS_API_URL ?? "http://127.0.0.1:8088"
).replace(/\/+$/, "");

async function resolveOrgId(): Promise<string> {
  const founder = await getFounder().catch(() => null);
  return (
    founder?.organizationId ??
    process.env.PUBLIC_ORGANIZATION_ID ??
    process.env.DEFAULT_ORGANIZATION_ID ??
    ""
  );
}

export async function GET(req: NextRequest) {
  const orgId = await resolveOrgId();
  if (!orgId) {
    return NextResponse.json({ ok: true, nodes: [], edges: [], snapshot: null });
  }
  const params = req.nextUrl.searchParams;
  const target = new URL(`${BACKEND}/v1/knowledge-graph`);
  target.searchParams.set("organization_id", orgId);
  for (const key of ["node_kind", "edge_kind", "include_provenance", "operator_override"]) {
    const value = params.get(key);
    if (value != null) target.searchParams.set(key, value);
  }
  try {
    const upstream = await fetch(target.toString(), { cache: "no-store" });
    const body = await upstream.json();
    return NextResponse.json(body, { status: upstream.status });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: `upstream failed: ${(err as Error).message}` },
      { status: 502 },
    );
  }
}

type ReasonRequestBody = {
  src: string;
  dst: string;
  edge_kind: string;
  use_llm?: boolean;
};

type BuildRequestBody = {
  action: "build";
};

export async function POST(req: NextRequest) {
  const orgId = await resolveOrgId();
  if (!orgId) {
    return NextResponse.json(
      { ok: false, error: "no organization context" },
      { status: 400 },
    );
  }
  let payload: ReasonRequestBody | BuildRequestBody;
  try {
    payload = (await req.json()) as ReasonRequestBody | BuildRequestBody;
  } catch {
    return NextResponse.json(
      { ok: false, error: "invalid JSON body" },
      { status: 400 },
    );
  }

  if ("action" in payload && payload.action === "build") {
    try {
      const upstream = await fetch(`${BACKEND}/v1/knowledge-graph/build`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ organization_id: orgId }),
        cache: "no-store",
      });
      const body = await upstream.json();
      return NextResponse.json(body, { status: upstream.status });
    } catch (err) {
      return NextResponse.json(
        { ok: false, error: `build proxy failed: ${(err as Error).message}` },
        { status: 502 },
      );
    }
  }

  const reasonBody = payload as ReasonRequestBody;
  if (!reasonBody.src || !reasonBody.dst || !reasonBody.edge_kind) {
    return NextResponse.json(
      { ok: false, error: "src, dst, and edge_kind are required" },
      { status: 400 },
    );
  }
  try {
    const upstream = await fetch(`${BACKEND}/v1/knowledge-graph/reason`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        organization_id: orgId,
        src: reasonBody.src,
        dst: reasonBody.dst,
        edge_kind: reasonBody.edge_kind,
        use_llm: reasonBody.use_llm !== false,
      }),
      cache: "no-store",
    });
    const body = await upstream.json();
    return NextResponse.json(body, { status: upstream.status });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: `reasoning proxy failed: ${(err as Error).message}` },
      { status: 502 },
    );
  }
}
