import { NextResponse } from "next/server";
import { withGated } from "@/lib/api/round3";

export const POST = withGated("methods.package", async (req) => {
  const body = (await req.json()) as { name?: string; version?: string };
  if (!body.name || !body.version) {
    return NextResponse.json(
      { ok: false, error: "name and version are required" },
      { status: 400 },
    );
  }

  const { spawn } = await import("child_process");
  const result = await new Promise<{ ok: boolean; data?: unknown; error?: string }>((resolve) => {
    const proc = spawn("python", [
      "-m", "noosphere", "methods", "package",
      `--name=${body.name}`, `--version=${body.version}`,
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
        resolve({ ok: false, error: stderr || "Method packaging failed" });
      }
    });
    proc.on("error", () => resolve({ ok: false, error: "Failed to spawn process" }));
  });

  return NextResponse.json(result, { status: result.ok ? 200 : 500 });
});
