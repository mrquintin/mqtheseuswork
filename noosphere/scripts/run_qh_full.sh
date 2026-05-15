#!/usr/bin/env bash
# Run the Quintin Hypothesis benchmark v1 end-to-end and publish the result.
#
# The QH harness (Round 17 prompt 08) and the leaderboard page already
# exist. This script is the "actually run it" step: without a first real
# run, the benchmark is just code.
#
# Stages:
#   0. Pre-flight  — verify the dataset is at frozen v1 state, the
#      embedder is available, and a 100-item shard run succeeds.
#   1. Full run    — all three runners (random, cosine, firm probe) over
#      the frozen v1 dataset, with the run envelope (git SHA, embedder,
#      seeds, dataset sha256) recorded.
#   2. Analysis    — paired BCa bootstrap CIs (10k resamples) and McNemar
#      for the firm-vs-cosine differences; written to analysis.md.
#   3. Artifact    — render docs/research/QH_Benchmark_v1_Results.{tex,pdf}.
#   4. Publish     — mirror the run to theseus-codex/public/qh-benchmark/
#      so the public leaderboard page renders the live result.
#   5. Digest      — emit a publication DigestEvent so the Round 17
#      prompt 39 follow-digest picks up the new artifact.
#   6. Announce    — gate an X announcement on MQS-on-the-firm-probe:
#      a weak result is published but NOT promoted.
#
# Usage:
#   ./run_qh_full.sh [--shard N] [--no-pdf] [--no-publish]
#                    [--seed N] [--post-tweet] [--results-root DIR]
#
# --no-pdf skips the docs/research artifact entirely (.tex and .pdf are
# one artifact). --results-root redirects the run directory — used by
# the integration test to stay hermetic; a real run leaves it default.
#
# Every number lands in code-generated artifacts; no value is hand-edited.
# The first run sets the baseline — this script never re-rolls seeds to
# shop for a friendlier number. Each invocation writes a fresh,
# timestamped run directory; nothing is overwritten.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/noosphere:${PYTHONPATH:-}"

DATASET="$ROOT/benchmarks/quintin_hypothesis/v1/dataset.jsonl"
RESULTS_ROOT="$ROOT/benchmarks/quintin_hypothesis/v1/results"
TEX_PATH="$ROOT/docs/research/QH_Benchmark_v1_Results.tex"
PDF_PATH="$ROOT/docs/research/QH_Benchmark_v1_Results.pdf"
PUBLIC_DIR="$ROOT/theseus-codex/public/qh-benchmark"
PUBLIC_PDF_DIR="$ROOT/theseus-codex/public/research"

PY="${PYTHON:-python3}"
SHARD=""
SKIP_PDF=0
SKIP_PUBLISH=0
SEED=0
POST_TWEET=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --shard) SHARD="$2"; shift 2;;
    --no-pdf) SKIP_PDF=1; shift;;
    --no-publish) SKIP_PUBLISH=1; shift;;
    --seed) SEED="$2"; shift 2;;
    --post-tweet) POST_TWEET=1; shift;;
    --results-root) RESULTS_ROOT="$2"; shift 2;;
    -h|--help) sed -n '2,42p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
mkdir -p "$RESULTS_ROOT"

echo "=== QH Benchmark v1 — full run ==="
echo "  root      : $ROOT"
echo "  dataset   : $DATASET"
echo "  results   : $RESULTS_ROOT"
[[ -n "$SHARD" ]] && echo "  SHARD     : $SHARD (smoke run — not a baseline)"

# ---------------------------------------------------------------------------
# Stage 0 — pre-flight. The full-run entrypoint also runs pre-flight
# internally; doing it here first makes a failure fast and loud, and
# satisfies the "verify a test run succeeds on a 100-item shard"
# requirement as an explicit, separate gate.
echo
echo "--- Stage 0: pre-flight (dataset frozen, embedder, 100-item shard) ---"
ROOT="$ROOT" "$PY" - <<'PYEOF'
from pathlib import Path
import os, sys
from noosphere.benchmarks.qh_analysis import preflight_check
from noosphere.benchmarks.qh_runner import HashEmbedder

root = Path(os.environ["ROOT"])
dataset = root / "benchmarks" / "quintin_hypothesis" / "v1" / "dataset.jsonl"
report = preflight_check(dataset, HashEmbedder(), repo_root=root, shard_size=100)
print(f"  dataset items           : {report['dataset_n_items']}")
print(f"  dataset domains         : {report['dataset_domains']}")
print(f"  dataset v1 promises met : {report['dataset_v1_promises_met']}")
print(f"  dataset frozen check    : {report['dataset_frozen_check']}")
print(f"  embedder available      : {report['embedder_available']} "
      f"({report.get('embedder_id')}, dim {report.get('embedder_dim')})")
for runner, info in report["shard_run"].items():
    print(f"  shard[{runner:>24}] : {info['n_of_N']}  status={info['status']}")
if not report["dataset_v1_promises_met"]:
    sys.exit("pre-flight FAILED: dataset does not meet v1 promises")
print("  pre-flight OK")
PYEOF

# ---------------------------------------------------------------------------
# Stage 1+2+3 — full run, analysis, and (unless --no-pdf) the PDF artifact.
echo
echo "--- Stage 1-3: full run + statistical analysis + artifact ---"
RUN_LOG="$(mktemp)"
trap 'rm -f "$RUN_LOG"' EXIT

FULL_RUN_ARGS=(full-run --dataset "$DATASET" --results-root "$RESULTS_ROOT" \
  --repo-root "$ROOT" --seed "$SEED")
[[ -n "$SHARD" ]] && FULL_RUN_ARGS+=(--shard "$SHARD")
# --tex/--pdf are one artifact: --no-pdf skips both so a smoke run never
# clobbers the canonical docs/research files.
if [[ "$SKIP_PDF" == "0" ]]; then
  FULL_RUN_ARGS+=(--tex "$TEX_PATH" --pdf "$PDF_PATH")
fi

"$PY" -m noosphere.benchmarks.qh_analysis "${FULL_RUN_ARGS[@]}" | tee "$RUN_LOG"

# pdflatex leaves .aux/.log/.out build noise next to the .tex; the .tex
# and .pdf are the artifacts, the rest is not.
if [[ "$SKIP_PDF" == "0" ]]; then
  rm -f "${TEX_PATH%.tex}".aux "${TEX_PATH%.tex}".log "${TEX_PATH%.tex}".out
fi

RUN_STAMP="$(grep -E '^run_stamp: ' "$RUN_LOG" | head -1 | awk '{print $2}')"
MQS_LINE="$(grep -E '^MQS_FIRM_PROBE=' "$RUN_LOG" | head -1)"
ANY_PARTIAL="$(grep -E '^ANY_PARTIAL=' "$RUN_LOG" | head -1 | cut -d= -f2)"
if [[ -z "$RUN_STAMP" ]]; then
  echo "could not determine run stamp from full-run output" >&2
  exit 1
fi
RUN_DIR="$RESULTS_ROOT/$RUN_STAMP"
echo
echo "  run directory : $RUN_DIR"
echo "  $MQS_LINE"
[[ "$ANY_PARTIAL" == "1" ]] && echo "  NOTE: at least one runner was partial — see analysis.md (n=K of N)."

# Parse the MQS gate fields.
MQS_VALUE="$(echo "$MQS_LINE" | sed -E 's/.*MQS_FIRM_PROBE=([0-9.]+).*/\1/')"
MQS_THRESHOLD="$(echo "$MQS_LINE" | sed -E 's/.*THRESHOLD=([0-9.]+).*/\1/')"
MQS_CLEARS="$(echo "$MQS_LINE" | sed -E 's/.*CLEARS=([01]).*/\1/')"

# ---------------------------------------------------------------------------
# Stage 4 — publish to the public site so the leaderboard page goes live.
if [[ "$SKIP_PUBLISH" == "0" ]]; then
  echo
  echo "--- Stage 4: publish to the public leaderboard ---"
  mkdir -p "$PUBLIC_DIR/latest" "$PUBLIC_PDF_DIR"
  cp "$RUN_DIR/results.json"  "$PUBLIC_DIR/latest/results.json"
  cp "$RUN_DIR/envelope.json" "$PUBLIC_DIR/latest/envelope.json"
  cp "$RUN_DIR/analysis.md"   "$PUBLIC_DIR/latest/analysis.md"
  # Flat per-runner metrics for backward compatibility with the old
  # page reader and the nightly CI artifact layout.
  cp "$RUN_DIR"/metrics_*.json "$PUBLIC_DIR/"
  if [[ "$SKIP_PDF" == "0" ]] && [[ -f "$PDF_PATH" ]]; then
    cp "$PDF_PATH" "$PUBLIC_PDF_DIR/QH_Benchmark_v1_Results.pdf"
    echo "  mirrored PDF -> $PUBLIC_PDF_DIR/QH_Benchmark_v1_Results.pdf"
  fi
  echo "  published latest run -> $PUBLIC_DIR/latest/"
else
  echo
  echo "--- Stage 4: publish SKIPPED (--no-publish) ---"
fi

# ---------------------------------------------------------------------------
# Stage 5 — emit a follow-digest event (Round 17 prompt 39). We do not
# send email here: the codex app owns the subscriber list and the mail
# transport. We write a publication DigestEvent into the run directory;
# the scheduler picks it up on its next cycle and folds it into
# per-subscriber digests. If QH_DIGEST_INTAKE points at an existing
# scheduler intake JSON, the event is merged in directly.
echo
echo "--- Stage 5: queue follow-digest event ---"
RUN_STAMP="$RUN_STAMP" RUN_DIR="$RUN_DIR" "$PY" - <<'PYEOF'
import json, os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from noosphere.social.digest_builder import DigestEvent

run_dir = Path(os.environ["RUN_DIR"])
results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
lb = results.get("leaderboard", [])
firm = next((r for r in lb if r["runner"] == "contradiction_geometry"), None)
mqs = results.get("mqs_firm_probe", {})
n_findings = len(results.get("honest_findings", []))

summary = (
    f"First end-to-end run of the QH benchmark v1. "
    f"Firm contradiction-geometry probe: "
    f"accuracy {firm['accuracy']:.4f}, AUROC {firm['auroc']:.4f}. "
    f"{n_findings} slice(s) where a baseline beats the firm probe are "
    f"reported honestly. MQS-on-the-firm-probe {mqs.get('composite', float('nan')):.4f}."
)
event = DigestEvent(
    kind="publication",
    headline="QH Benchmark v1 — first real run results published",
    summary=summary,
    url="https://theseuscodex.com/methodology/benchmark/qh",
    occurred_at=datetime.now(timezone.utc),
    conclusion_slug="qh-benchmark-v1-first-run",
    methodology_names=("contradiction_geometry",),
    domain_tags=("physics", "economics", "ethics"),
    is_major=True,
)
ev = asdict(event)
ev["occurred_at"] = event.occurred_at.isoformat()

event_path = run_dir / "digest_event.json"
event_path.write_text(json.dumps(ev, indent=2), encoding="utf-8")
print(f"  wrote digest event -> {event_path}")

intake = os.environ.get("QH_DIGEST_INTAKE")
if intake and Path(intake).is_file():
    snap = json.loads(Path(intake).read_text(encoding="utf-8"))
    snap.setdefault("events", []).append(ev)
    Path(intake).write_text(json.dumps(snap, indent=2), encoding="utf-8")
    print(f"  merged event into scheduler intake -> {intake}")
else:
    print("  QH_DIGEST_INTAKE not set; event queued in the run dir for the "
          "next scheduler cycle.")
PYEOF

# ---------------------------------------------------------------------------
# Stage 6 — announcement gate. Tweet ONLY if MQS-on-the-firm-probe clears
# the threshold. A weak result is published (it is on the leaderboard and
# in the PDF) but it is NOT promoted. Actual posting is opt-in via
# --post-tweet; without it, a draft is written for human review.
echo
echo "--- Stage 6: announcement gate (MQS=$MQS_VALUE, threshold=$MQS_THRESHOLD) ---"
if [[ "$MQS_CLEARS" == "1" ]]; then
  TWEET_DRAFT="$RUN_DIR/tweet_draft.txt"
  RUN_DIR="$RUN_DIR" MQS_VALUE="$MQS_VALUE" "$PY" - <<'PYEOF'
import json, os
from pathlib import Path
run_dir = Path(os.environ["RUN_DIR"])
results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
firm = next(r for r in results["leaderboard"] if r["runner"] == "contradiction_geometry")
text = (
    "We ran our Quintin Hypothesis benchmark v1 end-to-end against our own "
    "contradiction-geometry probe and two baselines.\n"
    f"Firm probe: accuracy {firm['accuracy']:.3f}, AUROC {firm['auroc']:.3f}.\n"
    "Full results, calibration, and statistical analysis (paired BCa "
    "bootstrap + McNemar):\n"
    "https://theseuscodex.com/methodology/benchmark/qh"
)
Path(run_dir / "tweet_draft.txt").write_text(text, encoding="utf-8")
print(text)
PYEOF
  echo
  echo "  MQS cleared the threshold — tweet draft written to $TWEET_DRAFT"
  if [[ "$POST_TWEET" == "1" ]]; then
    echo "  --post-tweet set: posting via the firm's X bot ..."
    # The X live client lives in noosphere.social.x_live_client and reads
    # its credentials from the firm config. Posting is a real external
    # side effect, so it is strictly opt-in.
    RUN_DIR="$RUN_DIR" "$PY" - <<'PYEOF'
import os
from pathlib import Path
text = Path(os.environ["RUN_DIR"], "tweet_draft.txt").read_text(encoding="utf-8")
try:
    from noosphere.social.x_live_client import XLiveClient  # type: ignore
    client = XLiveClient.from_env()
    res = client.post(text)
    print(f"  posted: {res}")
except Exception as exc:  # noqa: BLE001
    print(f"  X post FAILED ({type(exc).__name__}: {exc}); draft retained.")
PYEOF
  else
    echo "  (--post-tweet not set: draft only, no external post.)"
  fi
else
  echo "  MQS-on-the-firm-probe ($MQS_VALUE) is below the threshold "
  echo "  ($MQS_THRESHOLD). Announcement tweet SUPPRESSED — the firm does"
  echo "  not promote a weak result. The run is still published in full:"
  echo "  leaderboard, calibration, per-domain breakdown, and PDF."
fi

echo
echo "=== QH Benchmark v1 full run complete ==="
echo "  run dir : $RUN_DIR"
echo "  results : $RUN_DIR/results.json"
echo "  envelope: $RUN_DIR/envelope.json"
echo "  analysis: $RUN_DIR/analysis.md"
[[ "$SKIP_PDF" == "0" ]] && echo "  pdf     : $PDF_PATH"
echo "  tex     : $TEX_PATH"
