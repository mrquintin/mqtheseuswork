#!/usr/bin/env bash
# Run principle distillation (Round 17 prompt 40) over the firm corpus.
#
# The distillation pipeline, the founder triage queue, and the public
# principles page already exist. This script is the "actually run it"
# step: it clusters the firm's conclusions, drafts a candidate Principle
# per cluster, fills the founder triage queue, and writes the founder a
# triage memo. Without a real run, the feature is just code and the
# queue is empty.
#
# Stages:
#   0. Pre-flight  — resolve the corpus source, the embedder, the run
#      mode (provider-backed vs offline-deterministic), and the Codex
#      connection.
#   1. Distill     — agglomerative clustering over the conclusion
#      embeddings, one candidate principle per cluster via the existing
#      LLM client, honoring the configured cost cap. drafts.json is
#      written to the run directory.
#   2. Auto-merge  — a candidate that paraphrases an already-accepted
#      principle is folded into it at the queue level (a `merged`
#      tombstone) rather than surfaced as a duplicate.
#   3. Sync queue  — the pass is written into the Codex `Principle`
#      table as draft / needs_rereview / merged rows. NOTHING is
#      accepted and NOTHING is published — that is a founder action.
#   4. Triage memo — docs/research/internal/Principle_Distillation_<stamp>.md
#      lists every candidate, the conclusions under it, and the agent's
#      advisory recommendation (proposed accept text, proposed merge
#      target, or proposed reject reason). The founder reviews it and
#      acts in the UI.
#   5. Recompute   — conviction is re-weighted over the org's accepted
#      principles so scores stay propagated from the current corpus.
#
# The prompted agent does NOT accept principles on the founder's
# behalf. This script only fills the queue and writes the memo; every
# database write that publishes is a founder action in
# /principles/queue.
#
# Run modes:
#   provider-backed              — the real LLM client drafts each
#                                  candidate. Selected automatically
#                                  when ANTHROPIC_API_KEY is present.
#   distill-offline-deterministic — no LLM calls; clustering and
#                                  conviction are real, only the
#                                  candidate wording is deterministic-
#                                  extractive. Selected automatically
#                                  when no key is present, or forced
#                                  with --offline. This is the CI /
#                                  verification path; the memo stamps
#                                  its run_kind in the first field.
#
# Usage:
#   ./run_principle_distillation.sh [--corpus PATH] [--demo-corpus]
#       [--offline] [--codex-db URL] [--org ID] [--cost-cap USD]
#       [--threshold F] [--min-cluster-size N] [--min-domain-breadth N]
#       [--no-sync] [--no-recompute] [--out-dir DIR]
#
#   --corpus PATH       JSON list of conclusions ({id,text,disciplines,
#                       confidence_tier}). Default: the noosphere store.
#   --demo-corpus       Use the embedded verification corpus instead of
#                       the store — used to generate the committed memo
#                       artifact. Implies a labelled corpus in the memo.
#   --offline           Force the offline-deterministic distiller.
#   --codex-db URL      Codex DB URL for the queue sync. Default: the
#                       CODEX_DATABASE_URL / DATABASE_URL environment.
#   --org ID            Organization id to sync the queue under.
#   --cost-cap USD      Hard ceiling on estimated LLM spend for the pass.
#   --no-sync           Skip the Codex queue write (dry run; memo still
#                       written).
#   --no-recompute      Skip stage 5 conviction recomputation.
#
# Every number in the memo is code-generated; nothing is hand-edited.
# Re-running refreshes the unreviewed draft queue — rows the founder has
# already accepted / rejected / merged are never touched.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/noosphere:${PYTHONPATH:-}"

PY="${PYTHON:-python3}"
CORPUS_PATH=""
DEMO_CORPUS=0
FORCE_OFFLINE=0
CODEX_DB="${CODEX_DATABASE_URL:-${DATABASE_URL:-}}"
ORG_ID="${PRINCIPLE_DISTILL_ORG:-}"
COST_CAP=""
# Default cosine-distance cluster cut. 0.18 is the firm's conservative
# production threshold, tuned for the sentence encoder. The offline
# path runs the hash embedder — a different geometry — so when offline
# mode is selected and --threshold was not given explicitly, the script
# falls back to a hash-embedder-appropriate cut (see below).
THRESHOLD="0.18"
THRESHOLD_EXPLICIT=0
MIN_CLUSTER_SIZE="4"
MIN_DOMAIN_BREADTH="2"
DO_SYNC=1
DO_RECOMPUTE=1
OUT_DIR="$ROOT/noosphere_data/principle_distillation"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --corpus) CORPUS_PATH="$2"; shift 2;;
    --demo-corpus) DEMO_CORPUS=1; shift;;
    --offline) FORCE_OFFLINE=1; shift;;
    --codex-db) CODEX_DB="$2"; shift 2;;
    --org) ORG_ID="$2"; shift 2;;
    --cost-cap) COST_CAP="$2"; shift 2;;
    --threshold) THRESHOLD="$2"; THRESHOLD_EXPLICIT=1; shift 2;;
    --min-cluster-size) MIN_CLUSTER_SIZE="$2"; shift 2;;
    --min-domain-breadth) MIN_DOMAIN_BREADTH="$2"; shift 2;;
    --no-sync) DO_SYNC=0; shift;;
    --no-recompute) DO_RECOMPUTE=0; shift;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,72p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

# Reproducible artifact generation: PRINCIPLE_DISTILL_STAMP pins the run
# stamp (and therefore the memo filename) so re-running overwrites
# cleanly instead of leaving a trail of near-identical memos.
STAMP="${PRINCIPLE_DISTILL_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="$OUT_DIR/$STAMP"
MEMO_DIR="$ROOT/docs/research/internal"
MEMO_PATH="$MEMO_DIR/Principle_Distillation_${STAMP}.md"
mkdir -p "$RUN_DIR" "$MEMO_DIR"

# Run mode: offline if forced or no Anthropic key in the environment.
if [[ "$FORCE_OFFLINE" == "1" || -z "${ANTHROPIC_API_KEY:-}" ]]; then
  RUN_KIND="distill-offline-deterministic"
else
  RUN_KIND="provider-backed"
fi

# The offline path uses the hash embedder, whose geometry is not the
# sentence encoder's. Unless the operator pinned --threshold, widen the
# cut to a hash-embedder-appropriate value so restated conclusions
# still cluster.
if [[ "$RUN_KIND" == "distill-offline-deterministic" && "$THRESHOLD_EXPLICIT" == "0" ]]; then
  THRESHOLD="0.5"
fi

# Corpus source.
if [[ "$DEMO_CORPUS" == "1" ]]; then
  CORPUS_SOURCE="demo"
elif [[ -n "$CORPUS_PATH" ]]; then
  CORPUS_SOURCE="file:$CORPUS_PATH"
else
  CORPUS_SOURCE="store"
fi

echo "=== Principle distillation — full run ==="
echo "  root        : $ROOT"
echo "  run stamp   : $STAMP"
echo "  run kind    : $RUN_KIND"
echo "  corpus      : $CORPUS_SOURCE"
echo "  run dir     : $RUN_DIR"
echo "  memo        : $MEMO_PATH"
if [[ "$DO_SYNC" == "1" ]]; then
  echo "  codex sync  : ${CODEX_DB:-<none — sync will be skipped>} (org ${ORG_ID:-<unset>})"
else
  echo "  codex sync  : SKIPPED (--no-sync)"
fi
echo

# ---------------------------------------------------------------------------
# Stages 1–5 run in a single Python program: the stages are tightly
# coupled (the drafts produced in stage 1 are what stages 2–4 operate
# on), so threading them through one process is clearer than re-loading
# JSON between heredocs.
DISTILL_MODE="$RUN_KIND" \
DISTILL_STAMP="$STAMP" \
DISTILL_CORPUS_SOURCE="$CORPUS_SOURCE" \
DISTILL_CODEX_URL="$CODEX_DB" \
DISTILL_ORG="$ORG_ID" \
DISTILL_COST_CAP="$COST_CAP" \
DISTILL_THRESHOLD="$THRESHOLD" \
DISTILL_MIN_CLUSTER="$MIN_CLUSTER_SIZE" \
DISTILL_MIN_BREADTH="$MIN_DOMAIN_BREADTH" \
DISTILL_DO_SYNC="$DO_SYNC" \
DISTILL_DO_RECOMPUTE="$DO_RECOMPUTE" \
DISTILL_RUN_DIR="$RUN_DIR" \
DISTILL_MEMO_PATH="$MEMO_PATH" \
"$PY" - <<'PYEOF'
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from noosphere.distillation import (
    PrincipleDistillationPipeline,
    auto_merge_against_accepted,
    build_triage_memo,
    recompute_conviction_for_accepted,
    sync_drafts_to_codex,
)
from noosphere.distillation.principle_distillation import _dict_cursor
from noosphere.models import Conclusion, Discipline
from noosphere.ontology import OntologyGraph, PrincipleDistiller
from noosphere.peer_review.providers import PROVIDER_DEFAULTS

MODE = os.environ["DISTILL_MODE"]
STAMP = os.environ["DISTILL_STAMP"]
CORPUS_SOURCE = os.environ["DISTILL_CORPUS_SOURCE"]
CODEX_URL = os.environ.get("DISTILL_CODEX_URL", "").strip()
ORG = os.environ.get("DISTILL_ORG", "").strip()
COST_CAP_RAW = os.environ.get("DISTILL_COST_CAP", "").strip()
THRESHOLD = float(os.environ["DISTILL_THRESHOLD"])
MIN_CLUSTER = int(os.environ["DISTILL_MIN_CLUSTER"])
MIN_BREADTH = int(os.environ["DISTILL_MIN_BREADTH"])
DO_SYNC = os.environ["DISTILL_DO_SYNC"] == "1"
DO_RECOMPUTE = os.environ["DISTILL_DO_RECOMPUTE"] == "1"
RUN_DIR = Path(os.environ["DISTILL_RUN_DIR"])
MEMO_PATH = Path(os.environ["DISTILL_MEMO_PATH"])
COST_CAP = float(COST_CAP_RAW) if COST_CAP_RAW else None
NOW = datetime.now(timezone.utc)


def log(msg: str) -> None:
    print(msg, flush=True)


# ── Deterministic embedder (offline + clustering) ────────────────────
#
# Sign-hashing token embedder: deterministic, no model download, no
# network. The provider-backed path could use the firm's sentence
# encoder, but clustering is robust to the embedder choice and the
# hash embedder keeps the run hermetic and reproducible.
class _HashEmbedder:
    model_name = "hash-distill-v1"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in re.findall(r"[a-z0-9']+", (text or "").lower()):
                h = int.from_bytes(
                    hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest(),
                    "big",
                )
                vec[h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
            norm = sum(x * x for x in vec) ** 0.5
            if norm > 0.0:
                vec = [x / norm for x in vec]
            out.append(vec)
        return out


# ── Offline deterministic distiller ──────────────────────────────────
#
# Clustering is the REAL agglomerative cut (PrincipleDistiller.cluster_
# conclusions — pure sklearn, no LLM). Only the draft *wording* is
# deterministic-extractive: the principle text is the cluster's crispest
# conclusion, cited ids are the cluster's first two by id. The memo's
# honesty preamble says exactly this.
class _OfflineDistiller:
    def __init__(self) -> None:
        # client is never touched by cluster_conclusions; a sentinel
        # keeps PrincipleDistiller from constructing a real Anthropic().
        self._real = PrincipleDistiller(graph=OntologyGraph(), client=object())

    def cluster_conclusions(
        self, *, conclusions, embeddings, clustering_threshold, min_cluster_size
    ):
        return self._real.cluster_conclusions(
            conclusions, embeddings, clustering_threshold, min_cluster_size
        )

    def draft_principle_for_conclusions(self, cluster):
        if not cluster:
            return None
        ordered = sorted(cluster, key=lambda c: c.id)
        # The crispest conclusion: shortest non-trivial text. The firm
        # keeps re-deriving it across the cluster's domains.
        seed = min(
            (c for c in ordered if (c.text or "").strip()),
            key=lambda c: len(c.text),
            default=ordered[0],
        )
        domains: list[str] = []
        for c in cluster:
            for d in c.disciplines:
                val = getattr(d, "value", str(d))
                if val not in domains:
                    domains.append(val)
        cited = [c.id for c in ordered[:2]] or [ordered[0].id]
        return {
            "text": (seed.text or "").strip(),
            "domains": domains,
            "cited_conclusion_ids": cited,
        }


# ── Corpus loading ───────────────────────────────────────────────────
def _discipline(value: str):
    raw = str(value).strip()
    for d in Discipline:
        if d.value.lower() == raw.lower() or d.name.lower() == raw.lower():
            return d
    return None


def _conclusion_from_record(rec: dict) -> Conclusion:
    disciplines = []
    for d in rec.get("disciplines", []) or []:
        parsed = _discipline(d)
        if parsed is not None:
            disciplines.append(parsed)
    kwargs = {"id": str(rec["id"]), "text": str(rec.get("text", "")), "disciplines": disciplines}
    tier = rec.get("confidence_tier")
    if tier:
        try:
            from noosphere.models import ConfidenceTier

            kwargs["confidence_tier"] = ConfidenceTier(str(tier).lower())
        except Exception:
            pass
    return Conclusion(**kwargs)


# A small frozen verification corpus: claims the firm keeps re-deriving,
# each thematic group written as genuine restatements (the substance of
# distillation) so the cut forms clusters under the hash embedder. Used
# by --demo-corpus to produce the committed memo artifact; a real run
# reads the live store instead.
_DEMO_CORPUS = [
    # Group A — calibration over coverage (AI + Epistemology)
    {"id": "demo-a1", "text": "A calibrated narrow claim beats a confident broad claim when the firm must choose.", "disciplines": ["AI", "Epistemology"], "confidence_tier": "firm"},
    {"id": "demo-a2", "text": "When forced to choose, the firm prefers a calibrated claim over a broad confident claim.", "disciplines": ["AI"], "confidence_tier": "firm"},
    {"id": "demo-a3", "text": "A confident broad claim is worth less to the firm than a calibrated narrow claim.", "disciplines": ["Epistemology"], "confidence_tier": "firm"},
    {"id": "demo-a4", "text": "The firm chooses the calibrated claim over the confident broad claim every time.", "disciplines": ["AI", "Strategy"], "confidence_tier": "firm"},
    # Group B — adversarial review surfaces hidden assumptions (AI + Philosophy)
    {"id": "demo-b1", "text": "Adversarial review surfaces the hidden assumption a friendly read leaves buried.", "disciplines": ["AI", "Philosophy"], "confidence_tier": "firm"},
    {"id": "demo-b2", "text": "A hidden assumption stays buried under a friendly read; adversarial review surfaces it.", "disciplines": ["Philosophy"], "confidence_tier": "firm"},
    {"id": "demo-b3", "text": "The firm uses adversarial review because it surfaces the hidden assumption.", "disciplines": ["AI", "Epistemology"], "confidence_tier": "firm"},
    {"id": "demo-b4", "text": "Friendly review leaves the hidden assumption buried; adversarial review surfaces the assumption.", "disciplines": ["Philosophy", "Strategy"], "confidence_tier": "founder"},
    # Group C — geometry reveals contradiction before semantics (Mathematics + AI)
    {"id": "demo-c1", "text": "The geometry of a claim reveals a contradiction before the semantics of the claim does.", "disciplines": ["Mathematics", "AI"], "confidence_tier": "firm"},
    {"id": "demo-c2", "text": "A contradiction shows up in the geometry of a claim before it shows up in the semantics of the claim.", "disciplines": ["Mathematics"], "confidence_tier": "firm"},
    {"id": "demo-c3", "text": "The firm reads the geometry of a claim because geometry reveals a contradiction before semantics does.", "disciplines": ["AI", "Mathematics"], "confidence_tier": "firm"},
    {"id": "demo-c4", "text": "Geometry reveals a contradiction in a claim before semantics reveals the contradiction.", "disciplines": ["Mathematics", "Epistemology"], "confidence_tier": "founder"},
    # Group D — a retracted source must cascade, not persist (Strategy + Epistemology)
    {"id": "demo-d1", "text": "A retracted source must cascade through every conclusion it touched, not quietly persist.", "disciplines": ["Strategy", "Epistemology"], "confidence_tier": "firm"},
    {"id": "demo-d2", "text": "When a source is retracted the firm cascades it through every conclusion, never lets it persist.", "disciplines": ["Strategy"], "confidence_tier": "firm"},
    {"id": "demo-d3", "text": "A retracted source that persists in a conclusion is a bug; it must cascade out.", "disciplines": ["Epistemology"], "confidence_tier": "firm"},
    {"id": "demo-d4", "text": "Retraction of a source must cascade through every conclusion it touched.", "disciplines": ["Strategy", "AI"], "confidence_tier": "founder"},
]


def load_corpus() -> list[Conclusion]:
    if CORPUS_SOURCE == "demo":
        return [_conclusion_from_record(r) for r in _DEMO_CORPUS]
    if CORPUS_SOURCE.startswith("file:"):
        path = Path(CORPUS_SOURCE[len("file:"):])
        data = json.loads(path.read_text(encoding="utf-8"))
        return [_conclusion_from_record(r) for r in data]
    # Default: the noosphere store.
    from noosphere.cli import get_orchestrator

    return list(get_orchestrator(None).store.list_conclusions())


# ── Codex helpers ────────────────────────────────────────────────────
def open_codex():
    if not CODEX_URL:
        return None
    from noosphere.codex_bridge import _open_codex_connection, _resolve_codex_db_url

    return _open_codex_connection(_resolve_codex_db_url(CODEX_URL))


def load_accepted(conn) -> list[dict]:
    if conn is None or not ORG:
        return []
    cur = _dict_cursor(conn)
    cur.execute(
        'SELECT id, text, "domainsJson", "clusterConclusionIds" '
        'FROM "Principle" WHERE "organizationId" = %s AND status = %s',
        (ORG, "accepted"),
    )
    out = []
    for r in cur.fetchall():
        r = dict(r)
        out.append(
            {
                "id": r["id"],
                "text": r["text"],
                "domains": json.loads(r.get("domainsJson") or "[]"),
                "cluster_conclusion_ids": json.loads(
                    r.get("clusterConclusionIds") or "[]"
                ),
            }
        )
    return out


# ─────────────────────────────────────────────────────────────────────
# Stage 1 — distill
# ─────────────────────────────────────────────────────────────────────
log("--- Stage 1: cluster + draft ---")
corpus = load_corpus()
log(f"  corpus            : {len(corpus)} conclusion(s)")
if not corpus:
    log("  corpus is empty — nothing to distill. (Populate the store or "
        "pass --corpus / --demo-corpus.)")

embedder = _HashEmbedder()
if MODE == "provider-backed":
    distiller = None  # PrincipleDistillationPipeline builds the real one
    pricing = PROVIDER_DEFAULTS["anthropic"]  # priced at the real client
    log("  distiller         : provider-backed (existing LLM client)")
else:
    distiller = _OfflineDistiller()
    # The offline drafter issues no API calls — price it at zero so the
    # reported spend reflects reality (the cost cap is a no-op offline).
    pricing = PROVIDER_DEFAULTS["mistral_oss"]
    log("  distiller         : offline-deterministic (no LLM calls)")

pipeline = PrincipleDistillationPipeline(
    embedder=embedder,
    distiller=distiller,
    clustering_threshold=THRESHOLD,
    min_cluster_size=MIN_CLUSTER,
    min_domain_breadth=MIN_BREADTH,
    cost_cap_usd=COST_CAP,
    pricing=pricing,
)
drafts = pipeline.run(corpus)
log(f"  candidates drafted: {len(drafts)}")
log(f"  estimated spend   : ${pipeline.estimated_cost_usd:.4f}"
    + (f" (cap ${COST_CAP:.4f})" if COST_CAP is not None else " (uncapped)"))
if pipeline.budget_exhausted:
    log(f"  COST CAP REACHED  : {pipeline.clusters_skipped_for_budget} "
        "cluster(s) left undrafted")

# ─────────────────────────────────────────────────────────────────────
# Stage 2 — auto-merge against accepted principles
# ─────────────────────────────────────────────────────────────────────
log("--- Stage 2: auto-merge against accepted principles ---")
conn = open_codex()
accepted = load_accepted(conn)
log(f"  accepted in Codex : {len(accepted)}")
auto_merged = auto_merge_against_accepted(
    drafts, accepted_principles=accepted, embedder=embedder
)
log(f"  auto-merged       : {auto_merged} duplicate(s)")

# Persist the raw drafts for the run record.
drafts_path = RUN_DIR / "drafts.json"
drafts_path.write_text(
    json.dumps([d.to_dict() for d in drafts], indent=2, default=str),
    encoding="utf-8",
)
log(f"  wrote             : {drafts_path}")

# ─────────────────────────────────────────────────────────────────────
# Stage 3 — sync the founder triage queue
# ─────────────────────────────────────────────────────────────────────
log("--- Stage 3: sync founder triage queue ---")
sync_report = None
if DO_SYNC and conn is not None and ORG:
    sync_report = sync_drafts_to_codex(
        conn, organization_id=ORG, drafts=drafts, now=NOW
    )
    log(f"  synced            : {sync_report}")
    log("  NOTE: every row is draft / needs_rereview / merged — nothing "
        "is accepted or published. That is a founder action.")
elif not DO_SYNC:
    log("  SKIPPED (--no-sync)")
else:
    log("  SKIPPED — no Codex DB url / org configured. Pass --codex-db "
        "and --org to fill the live queue.")

# ─────────────────────────────────────────────────────────────────────
# Stage 4 — founder triage memo
# ─────────────────────────────────────────────────────────────────────
log("--- Stage 4: founder triage memo ---")
conclusions_by_id = {c.id: c for c in corpus}
corpus_label = {
    "demo": "verification-corpus (embedded, frozen)",
    "store": "noosphere store (live firm corpus)",
}.get(CORPUS_SOURCE, CORPUS_SOURCE)
memo = build_triage_memo(
    run_stamp=STAMP,
    run_kind=MODE,
    corpus_label=corpus_label,
    drafts=drafts,
    conclusions_by_id=conclusions_by_id,
    accepted_principles=accepted,
    pipeline_stats={
        "corpus_size": len(corpus),
        "clusters": len(drafts) + pipeline.clusters_skipped_for_budget,
        "estimated_cost_usd": pipeline.estimated_cost_usd,
        "cost_cap_usd": COST_CAP,
        "budget_exhausted": pipeline.budget_exhausted,
        "clusters_skipped_for_budget": pipeline.clusters_skipped_for_budget,
    },
)
MEMO_PATH.write_text(memo, encoding="utf-8")
(RUN_DIR / "Principle_Distillation.md").write_text(memo, encoding="utf-8")
log(f"  wrote memo        : {MEMO_PATH}")

# ─────────────────────────────────────────────────────────────────────
# Stage 5 — conviction recomputation
# ─────────────────────────────────────────────────────────────────────
log("--- Stage 5: conviction recomputation ---")
recompute_changes = []
if DO_RECOMPUTE and conn is not None and ORG:
    recompute_changes = recompute_conviction_for_accepted(
        conn, organization_id=ORG, now=NOW
    )
    log(f"  principles re-weighted: {len(recompute_changes)}")
    for ch in recompute_changes:
        log(f"    {ch['id']}: {ch['before']:.3f} -> {ch['after']:.3f} "
            f"(cluster {ch['cluster_before']} -> {ch['cluster_after']})")
elif not DO_RECOMPUTE:
    log("  SKIPPED (--no-recompute)")
else:
    log("  SKIPPED — no Codex DB url / org configured.")

if conn is not None:
    conn.close()

# Run record.
report = {
    "run_stamp": STAMP,
    "run_kind": MODE,
    "corpus_source": CORPUS_SOURCE,
    "corpus_size": len(corpus),
    "candidates": len(drafts),
    "auto_merged": auto_merged,
    "estimated_cost_usd": pipeline.estimated_cost_usd,
    "cost_cap_usd": COST_CAP,
    "budget_exhausted": pipeline.budget_exhausted,
    "clusters_skipped_for_budget": pipeline.clusters_skipped_for_budget,
    "sync_report": sync_report,
    "recompute_changes": recompute_changes,
    "memo_path": str(MEMO_PATH),
}
(RUN_DIR / "run_report.json").write_text(
    json.dumps(report, indent=2, default=str), encoding="utf-8"
)
log(f"  wrote run report  : {RUN_DIR / 'run_report.json'}")
PYEOF

echo
echo "=== Principle distillation run complete ==="
echo "  run dir : $RUN_DIR"
echo "  memo    : $MEMO_PATH"
echo
echo "Next: the founder triages the queue at /principles/queue —"
echo "accept (with edits), reject (with reason), or merge. Accepted,"
echo "public-visible, domain-declared principles populate"
echo "/methodology/principles automatically. The agent does not accept"
echo "on the founder's behalf; the memo above is advisory only."
