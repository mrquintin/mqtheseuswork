import { NextResponse } from "next/server";
import { withGated } from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";

export const POST = withGated("methods.document", async (req) => {
  const body = (await req.json()) as { name?: string; version?: string };
  if (!body.name || !body.version) {
    return NextResponse.json(
      { ok: false, error: "name and version are required" },
      { status: 400 },
    );
  }

  const result = await callNoosphereJson(
    ["docgen", "generate", `--method=${body.name}`, `--version=${body.version}`],
    "Documentation generation failed",
  );
  return NextResponse.json(result, { status: result.status });
});
