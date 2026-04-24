import { NextResponse } from "next/server";
import { withGated } from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";

export const POST = withGated("peer_review.run", async (req) => {
  const body = (await req.json()) as { conclusionId?: string };
  if (!body.conclusionId) {
    return NextResponse.json(
      { ok: false, error: "conclusionId is required" },
      { status: 400 },
    );
  }

  const result = await callNoosphereJson(
    ["peer-review", "--conclusion-id", body.conclusionId],
    "Peer review run failed",
  );
  return NextResponse.json(result, { status: result.status });
});
