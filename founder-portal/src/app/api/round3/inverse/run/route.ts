import { NextResponse } from "next/server";
import { withGated } from "@/lib/api/round3";

export const POST = withGated("inverse.run", async (req) => {
  const body = (await req.json()) as { conclusionId?: string };
  if (!body.conclusionId) {
    return NextResponse.json(
      { ok: false, error: "conclusionId is required" },
      { status: 400 },
    );
  }

  const { spawn } = await import("child_process");
  const result = await new Promise<{ ok: boolean; data?: unknown; error?: string }>((resolve) => {
    const proc = spawn("python", [
      "-m", "noosphere", "inverse-inference", "--conclusion-id", body.conclusionId!,
    ]);
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });
    proc.stderr.on("data", (d: Buffer) => { stderr += d.toString(); });
    proc.on("close", (code) => {
      if (code === 0) {
        try {
          resolve({ ok: true, data: JSON.parse(stdout) });
        } catch {
          resolve({ ok: true, data: stdout });
        }
      } else {
        resolve({ ok: false, error: stderr || "Inverse inference failed" });
      }
    });
    proc.on("error", () => resolve({ ok: false, error: "Failed to spawn process" }));
  });

  return NextResponse.json(result, { status: result.ok ? 200 : 500 });
});
