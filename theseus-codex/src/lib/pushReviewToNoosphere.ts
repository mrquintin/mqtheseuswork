import { spawn } from "child_process";
import { join } from "path";
import { isNoosphereLikelyUnavailable } from "./pythonRuntime";

const NOOSPHERE_PYTHON = process.env.NOOSPHERE_PYTHON || "python3";
const NOOSPHERE_SRC_ROOT =
  process.env.NOOSPHERE_SRC_ROOT || join(process.cwd(), "..", "noosphere");

/**
 * Persist human resolution into the Noosphere SQLite store (same schema as
 * `noosphere.store.put_review_item`). Skips if NOOSPHERE_DATABASE_URL is unset.
 */
export function pushReviewResolutionToNoosphere(payload: {
  reviewId: string;
  verdict: "cohere" | "contradict" | "unresolved";
  overrule: boolean;
  aggregatorVerdict?: string | null;
  founderId: string;
  note: string;
}): Promise<{ ok: boolean; stderr: string }> {
  const dbUrl = process.env.NOOSPHERE_DATABASE_URL;
  if (!dbUrl) {
    return Promise.resolve({ ok: true, stderr: "" });
  }
  // Same rationale as the other bridges: don't even attempt `spawn` on
  // serverless runtimes. The resolution has already been persisted to
  // the Codex Postgres; the Noosphere side-channel is a cache-warm,
  // not a write-through.
  if (isNoosphereLikelyUnavailable()) {
    return Promise.resolve({
      ok: true,
      stderr: "skipped: Noosphere CLI not available in this runtime",
    });
  }

  const script = `
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.environ["NOOSPHERE_SRC"])
from noosphere.store import Store
from noosphere.models import ReviewItem, CoherenceVerdict

payload = json.loads(sys.stdin.read())
store = Store.from_database_url(os.environ["NOOSPHERE_DATABASE_URL"])
item = store.get_review_item(payload["reviewId"])
if item is None:
    print("missing", file=sys.stderr)
    sys.exit(2)

v = CoherenceVerdict(payload["verdict"])
item.human_verdict = v
item.human_overrule = bool(payload["overrule"])
item.resolved_by_founder_id = payload.get("founderId") or ""
item.resolution_note = payload.get("note") or ""
item.resolved_at = datetime.now(timezone.utc)
item.status = "done"
ag = payload.get("aggregatorVerdict")
if ag:
    item.aggregator_verdict = CoherenceVerdict(ag)
store.put_review_item(item)
print("ok")
`;

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
    let stderr = "";
    proc.stderr.on("data", (d: Buffer) => {
      stderr += d.toString();
    });
    proc.on("close", (code) => resolve({ ok: code === 0, stderr }));
    proc.on("error", (e) => resolve({ ok: false, stderr: String(e) }));
    proc.stdin.write(JSON.stringify(payload));
    proc.stdin.end();
  });
}
