import { spawn } from "child_process";
import { join } from "path";
import { isNoosphereLikelyUnavailable } from "./pythonRuntime";

const NOOSPHERE_PYTHON = process.env.NOOSPHERE_PYTHON || "python3";
const NOOSPHERE_SRC_ROOT =
  process.env.NOOSPHERE_SRC_ROOT || join(process.cwd(), "..", "noosphere");

const REPLAY_CONCLUSIONS_SCRIPT = `
import json, os, sys
sys.path.insert(0, os.environ["NOOSPHERE_SRC"])
from noosphere.store import Store
from noosphere.temporal_replay import list_conclusions_replay_consistent, parse_cutoff_date

req = json.loads(sys.stdin.read())
store = Store.from_database_url(os.environ["NOOSPHERE_DATABASE_URL"])
d = parse_cutoff_date(req["as_of"])
cons = list_conclusions_replay_consistent(store, d)
print(json.dumps([c.model_dump(mode="json") for c in cons], default=str))
`;

function runPythonJson(script: string, stdin: string): Promise<{
  ok: boolean;
  data: unknown;
  stderr: string;
}> {
  const dbUrl = process.env.NOOSPHERE_DATABASE_URL;
  if (!dbUrl) {
    return Promise.resolve({ ok: true, data: [], stderr: "" });
  }
  // See noosphereLiteratureBridge.ts.
  if (isNoosphereLikelyUnavailable()) {
    return Promise.resolve({ ok: true, data: [], stderr: "" });
  }
  return new Promise((resolve) => {
    const proc = spawn(NOOSPHERE_PYTHON, ["-c", script], {
      env: {
        ...process.env,
        NOOSPHERE_DATABASE_URL: dbUrl,
        NOOSPHERE_SRC: NOOSPHERE_SRC_ROOT,
        PYTHONPATH: NOOSPHERE_SRC_ROOT,
      },
      cwd: join(process.cwd(), ".."),
    });
    let out = "";
    let err = "";
    proc.stdout.on("data", (d: Buffer) => {
      out += d.toString();
    });
    proc.stderr.on("data", (d: Buffer) => {
      err += d.toString();
    });
    proc.on("close", (code) => {
      if (code !== 0) {
        resolve({ ok: false, data: null, stderr: err || out || `exit ${code}` });
        return;
      }
      try {
        resolve({ ok: true, data: JSON.parse(out), stderr: err });
      } catch {
        resolve({ ok: false, data: null, stderr: (err || "") + out });
      }
    });
    proc.on("error", (e) => resolve({ ok: false, data: null, stderr: String(e) }));
    proc.stdin.write(stdin);
    proc.stdin.end();
  });
}

export type ReplayConclusionRow = {
  id: string;
  text: string;
  confidence_tier?: string;
  rationale?: string;
  created_at?: string;
};

export async function fetchReplayConclusions(asOf: string): Promise<{
  rows: ReplayConclusionRow[];
  error: string;
}> {
  const { ok, data, stderr } = await runPythonJson(
    REPLAY_CONCLUSIONS_SCRIPT,
    JSON.stringify({ as_of: asOf }),
  );
  if (!ok || !Array.isArray(data)) {
    return { rows: [], error: stderr || "replay query failed" };
  }
  return { rows: data as ReplayConclusionRow[], error: stderr };
}
