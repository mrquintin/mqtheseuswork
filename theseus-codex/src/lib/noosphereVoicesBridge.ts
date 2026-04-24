import { spawn } from "child_process";
import { join } from "path";
import { isNoosphereLikelyUnavailable } from "./pythonRuntime";

const NOOSPHERE_PYTHON = process.env.NOOSPHERE_PYTHON || "python3";
const NOOSPHERE_SRC_ROOT =
  process.env.NOOSPHERE_SRC_ROOT || join(process.cwd(), "..", "noosphere");

const LIST_VOICES_SCRIPT = `
import json, os, sys
sys.path.insert(0, os.environ["NOOSPHERE_SRC"])
from noosphere.models import voice_canonical_key
from noosphere.store import Store

store = Store.from_database_url(os.environ["NOOSPHERE_DATABASE_URL"])
out = []
for v in store.list_voice_profiles(limit=400):
    cites = store.list_citations_for_voice(v.id)
    cl = store.list_claims_for_voice(v.id, limit=200)
    out.append(
        {
            "id": v.id,
            "canonicalName": v.canonical_name,
            "canonicalKey": voice_canonical_key(v.canonical_name),
            "traditions": v.traditions,
            "affiliations": v.affiliations,
            "corpusCount": len(v.corpus_artifact_ids),
            "citationCount": len(cites),
            "claimCount": len(cl),
            "corpusBoundaryNote": v.corpus_boundary_note,
            "copyrightStatus": v.copyright_status,
        }
    )
print(json.dumps(out))
`;

const VOICE_DETAIL_SCRIPT = `
import json, os, sys
sys.path.insert(0, os.environ["NOOSPHERE_SRC"])
from noosphere.store import Store

req = json.loads(sys.stdin.read())
vid = req.get("voice_id") or ""
if not vid:
    print(json.dumps({"error": "missing voice_id"}))
    sys.exit(0)

store = Store.from_database_url(os.environ["NOOSPHERE_DATABASE_URL"])
v = store.get_voice(vid)
if v is None:
    print(json.dumps({"error": "not_found", "voice_id": vid}))
    sys.exit(0)

claims = [
    {"id": c.id, "text": c.text[:800], "artifactId": c.source_id or ""}
    for c in store.list_claims_for_voice(vid, limit=80)
]
phases = [p.model_dump(mode="json") for p in store.list_voice_phases(vid)]
cites = [c.model_dump(mode="json") for c in store.list_citations_for_voice(vid)][:80]

firm_maps = []
for m in store.list_relative_position_maps(limit=400):
    mine = [e.model_dump(mode="json") for e in m.entries if e.voice_id == vid]
    if not mine:
        continue
    firm_maps.append(
        {
            "conclusionId": m.conclusion_id,
            "closestAgreeingVoiceId": m.closest_agreeing_voice_id,
            "closestOpposingVoiceId": m.closest_opposing_voice_id,
            "entries": mine,
        }
    )

print(
    json.dumps(
        {
            "voice": v.model_dump(mode="json"),
            "claims": claims,
            "phases": phases,
            "citations": cites,
            "relativeToFirm": firm_maps,
        }
    )
)
`;

function runPythonJson(script: string, stdin?: string): Promise<{
  ok: boolean;
  data: unknown;
  stderr: string;
}> {
  const dbUrl = process.env.NOOSPHERE_DATABASE_URL;
  if (!dbUrl) {
    return Promise.resolve({
      ok: true,
      data: { skipped: true, reason: "NOOSPHERE_DATABASE_URL unset" },
      stderr: "",
    });
  }
  // See noosphereLiteratureBridge.ts — we don't attempt Python spawn on
  // serverless runtimes even if the DB URL is set.
  if (isNoosphereLikelyUnavailable()) {
    return Promise.resolve({
      ok: true,
      data: { skipped: true, reason: "Noosphere CLI not available in this runtime" },
      stderr: "",
    });
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
    if (stdin != null) {
      proc.stdin.write(stdin);
    }
    proc.stdin.end();
  });
}

export type VoiceListRow = {
  id: string;
  canonicalName: string;
  canonicalKey: string;
  traditions: string[];
  affiliations: string[];
  corpusCount: number;
  citationCount: number;
  claimCount: number;
  corpusBoundaryNote: string;
  copyrightStatus: string;
};

export async function fetchVoicesFromNoosphere(): Promise<{
  rows: VoiceListRow[];
  skipped: boolean;
  message: string;
}> {
  const { ok, data, stderr } = await runPythonJson(LIST_VOICES_SCRIPT);
  if (!ok || data == null || typeof data !== "object") {
    return { rows: [], skipped: true, message: stderr || "voice list failed" };
  }
  if ("skipped" in data && (data as { skipped?: boolean }).skipped) {
    return {
      rows: [],
      skipped: true,
      message: (data as { reason?: string }).reason || "skipped",
    };
  }
  if (!Array.isArray(data)) {
    return { rows: [], skipped: true, message: "unexpected voice list payload" };
  }
  return { rows: data as VoiceListRow[], skipped: false, message: stderr };
}

export async function fetchVoiceDetailFromNoosphere(voiceId: string): Promise<{
  payload: Record<string, unknown> | null;
  error: string;
}> {
  const { ok, data, stderr } = await runPythonJson(
    VOICE_DETAIL_SCRIPT,
    JSON.stringify({ voice_id: voiceId }),
  );
  if (!ok || data == null || typeof data !== "object") {
    return { payload: null, error: stderr || "voice detail failed" };
  }
  const err = (data as { error?: string }).error;
  if (err === "not_found") {
    return { payload: null, error: "Voice not found in Noosphere store." };
  }
  if (err === "missing voice_id") {
    return { payload: null, error: "Missing voice id." };
  }
  return { payload: data as Record<string, unknown>, error: stderr };
}
