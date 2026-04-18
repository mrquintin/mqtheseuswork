import { NextResponse } from "next/server";
import { withGated } from "@/lib/api/round3";
import { callNoosphereJson } from "@/lib/pythonRuntime";

export const POST = withGated(
  "gate.override",
  async (req, ctx) => {
    const { id } = await ctx!.params;
    const body = (await req.json()) as {
      verdict?: "approved" | "rejected";
      reason?: string;
    };
    if (!body.verdict || !["approved", "rejected"].includes(body.verdict)) {
      return NextResponse.json(
        { ok: false, error: "verdict must be 'approved' or 'rejected'" },
        { status: 400 },
      );
    }

    const args = [
      "rigor-gate",
      "override",
      `--submission-id=${id}`,
      `--verdict=${body.verdict}`,
      ...(body.reason ? [`--reason=${body.reason}`] : []),
    ];
    const result = await callNoosphereJson(args, "Gate override failed");
    return NextResponse.json(result, { status: result.status });
  },
);
