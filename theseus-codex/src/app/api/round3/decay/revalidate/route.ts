import { NextResponse } from "next/server";
import { withGated } from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";

export const POST = withGated("decay.revalidate", async (req) => {
  const body = (await req.json()) as { conclusionId?: string };
  if (!body.conclusionId) {
    return NextResponse.json(
      { ok: false, error: "conclusionId is required" },
      { status: 400 },
    );
  }

  const result = await callNoosphereJson(
    ["decay", "revalidate", "--conclusion-id", body.conclusionId],
    "Decay revalidation failed",
  );
  return NextResponse.json(result, { status: result.status });
});
