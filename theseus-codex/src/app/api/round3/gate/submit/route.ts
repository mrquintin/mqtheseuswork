import { NextResponse } from "next/server";
import { withGated } from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";

export const POST = withGated("gate.submit", async (req) => {
  const body = (await req.json()) as {
    conclusionId?: string;
    kind?: string;
    notes?: string;
  };
  if (!body.conclusionId || !body.kind) {
    return NextResponse.json(
      { ok: false, error: "conclusionId and kind are required" },
      { status: 400 },
    );
  }

  const args = [
    "rigor-gate",
    "submit",
    `--kind=${body.kind}`,
    `--conclusion-id=${body.conclusionId}`,
    ...(body.notes ? [`--notes=${body.notes}`] : []),
  ];
  const result = await callNoosphereJson(args, "Gate submission failed");
  return NextResponse.json(result, { status: result.status });
});
