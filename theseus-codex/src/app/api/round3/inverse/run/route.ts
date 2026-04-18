import { NextResponse } from "next/server";
import { withGated } from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";

export const POST = withGated("inverse.run", async (req) => {
  const body = (await req.json()) as { conclusionId?: string };
  if (!body.conclusionId) {
    return NextResponse.json(
      { ok: false, error: "conclusionId is required" },
      { status: 400 },
    );
  }

  // Previously this route did its own spawn("python", ...) and returned
  // `Failed to spawn process` on Vercel. `callNoosphereJson` centralises
  // that handling: 501 + a clear message when the CLI isn't reachable,
  // 200 + parsed JSON on success, 500 on non-zero exit.
  const result = await callNoosphereJson(
    ["inverse-inference", "--conclusion-id", body.conclusionId],
    "Inverse inference failed",
  );
  return NextResponse.json(result, { status: result.status });
});
