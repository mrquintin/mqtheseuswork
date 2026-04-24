import { spawn } from "child_process";
import { join } from "path";
import { isNoosphereLikelyUnavailable } from "./pythonRuntime";

const NOOSPHERE_PYTHON = process.env.NOOSPHERE_PYTHON || "python3";
const NOOSPHERE_SRC_ROOT =
  process.env.NOOSPHERE_SRC_ROOT || join(process.cwd(), "..", "noosphere");

const BRIDGE_SCRIPT = `
import json, os, sys
sys.path.insert(0, os.environ["NOOSPHERE_SRC"])
from noosphere.store import Store

req = json.loads(sys.stdin.read())
store = Store.from_database_url(os.environ["NOOSPHERE_DATABASE_URL"])
op = req.get("op")
if op == "literature":
    arts = store.list_literature_artifacts(limit=200)
    out = [
        {
            "id": a.id,
            "title": a.title,
            "author": a.author,
            "license": a.license_status,
            "connector": a.literature_connector,
            "uri": a.uri,
        }
        for a in arts
    ]
elif op == "reading_queue":
    rows = store.list_reading_queue_entries(limit=200)
    out = [e.model_dump(mode="json") for e in rows]
elif op == "reading_queue_update":
    ok = store.update_reading_queue_status(req["id"], req["status"], notes=req.get("notes") or "")
    out = {"ok": bool(ok)}
else:
    out = {"error": "unknown op"}
print(json.dumps(out, default=str))
`;

function runBridge(stdin: string): Promise<{ ok: boolean; data: unknown; stderr: string }> {
  const dbUrl = process.env.NOOSPHERE_DATABASE_URL;
  if (!dbUrl) {
    return Promise.resolve({ ok: true, data: [], stderr: "" });
  }
  // Belt-and-suspenders: even if NOOSPHERE_DATABASE_URL is set, don't
  // attempt a Python spawn on a runtime that has no interpreter (Vercel,
  // Netlify). Return empty data so calling pages render their empty state
  // instead of surfacing an ENOENT to the user.
  if (isNoosphereLikelyUnavailable()) {
    return Promise.resolve({ ok: true, data: [], stderr: "" });
  }
  return new Promise((resolve) => {
    const proc = spawn(NOOSPHERE_PYTHON, ["-c", BRIDGE_SCRIPT], {
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

export type LiteratureRow = {
  id: string;
  title: string;
  author: string;
  license: string;
  connector: string;
  uri: string;
};

export type ReadingQueueRow = {
  id: string;
  session_id: string;
  grounding_claim_id: string;
  artifact_id: string;
  title: string;
  author: string;
  rationale: string;
  status: string;
};

export async function fetchLiteratureArtifacts(): Promise<{ rows: LiteratureRow[]; message: string }> {
  const { ok, data, stderr } = await runBridge(JSON.stringify({ op: "literature" }));
  if (!ok || !Array.isArray(data)) {
    return { rows: [], message: stderr || "literature bridge failed" };
  }
  return { rows: data as LiteratureRow[], message: stderr };
}

export async function fetchReadingQueue(): Promise<{ rows: ReadingQueueRow[]; message: string }> {
  const { ok, data, stderr } = await runBridge(JSON.stringify({ op: "reading_queue" }));
  if (!ok || !Array.isArray(data)) {
    return { rows: [], message: stderr || "reading queue failed" };
  }
  return { rows: data as ReadingQueueRow[], message: stderr };
}

export async function updateReadingQueueStatus(
  id: string,
  status: ReadingQueueRow["status"],
  notes?: string,
): Promise<{ ok: boolean; error: string }> {
  const { ok, data, stderr } = await runBridge(
    JSON.stringify({ op: "reading_queue_update", id, status, notes: notes || "" }),
  );
  if (!ok || data == null || typeof data !== "object") {
    return { ok: false, error: stderr || "update failed" };
  }
  return { ok: Boolean((data as { ok?: boolean }).ok), error: stderr };
}
