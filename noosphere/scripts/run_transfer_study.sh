#!/usr/bin/env bash
# Run the Cross-Domain Method Transfer Study v1 end-to-end and publish it.
#
# The study asks: when a method has a strong, large-n track record in
# domain D, does that capability transfer to a neighboring domain D' the
# method has no track record in? `noosphere.transfer.study` is the
# experiment; this script is the "actually run it, render it, publish
# it" wrapper.
#
# Stages:
#   0. Pre-flight — verify pyyaml + scipy import, the pairs manifest
#      parses, and every frozen dataset's sha256 matches the manifest.
#      A re-curated held-out set fails here, loudly.
#   1. Run + analysis + artifact — run all 3 method/domain pairs
#      (in-domain CV, transfer eval, domain-naive D'-trained baseline,
#      unpaired bootstrap CIs, two-proportion tests, Cohen's h, outcome
#      taxonomy) and render docs/research/Cross_Domain_Transfer_Study.{tex,pdf}.
#   2. Publish — mirror the run to theseus-codex/public/transfer-study/
#      so the public page renders the live result, and mirror the PDF.
#
# Every number lands in code-generated artifacts; no value is hand-edited.
# The held-out target sets are frozen and hash-pinned; this script never
# re-curates them to chase a friendlier number. Each invocation writes a
# fresh, timestamped run directory; nothing is overwritten.
#
# Usage:
#   ./run_transfer_study.sh [--no-pdf] [--no-publish] [--seed N]
#                           [--results-root DIR]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/noosphere:${PYTHONPATH:-}"

PAIRS="$ROOT/benchmarks/transfer/v1/pairs.yaml"
RESULTS_ROOT="$ROOT/benchmarks/transfer/v1/results"
TEX_PATH="$ROOT/docs/research/Cross_Domain_Transfer_Study.tex"
PDF_PATH="$ROOT/docs/research/Cross_Domain_Transfer_Study.pdf"
PUBLIC_DIR="$ROOT/theseus-codex/public/transfer-study"
PUBLIC_PDF_DIR="$ROOT/theseus-codex/public/research"

PY="${PYTHON:-python3}"
SKIP_PDF=0
SKIP_PUBLISH=0
SEED=17

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-pdf) SKIP_PDF=1; shift;;
    --no-publish) SKIP_PUBLISH=1; shift;;
    --seed) SEED="$2"; shift 2;;
    --results-root) RESULTS_ROOT="$2"; shift 2;;
    -h|--help) sed -n '2,27p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
mkdir -p "$RESULTS_ROOT"

echo "=== Cross-Domain Transfer Study v1 — full run ==="
echo "  root      : $ROOT"
echo "  pairs     : $PAIRS"
echo "  results   : $RESULTS_ROOT"

# ---------------------------------------------------------------------------
# Stage 0 — pre-flight. The study entrypoint re-verifies hashes itself;
# doing it here first makes a frozen-set tamper fail fast and loud.
echo
echo "--- Stage 0: pre-flight (deps, manifest, frozen-set hashes) ---"
ROOT="$ROOT" PAIRS="$PAIRS" "$PY" - <<'PYEOF'
import hashlib, os, sys
from pathlib import Path
import yaml  # noqa: F401  (pre-flight: must be importable)
import scipy  # noqa: F401
from noosphere.transfer.study import load_pairs

root = Path(os.environ["ROOT"])
pairs_path = Path(os.environ["PAIRS"])
manifest = load_pairs(pairs_path)
print(f"  manifest parses        : {len(manifest['pairs'])} pairs, "
      f"frozen {manifest.get('frozen_at')}")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


ok = True
src = manifest.get("source_dataset", {})
if src.get("sha256"):
    actual = _sha(root / src["path"])
    match = actual == src["sha256"]
    ok &= match
    print(f"  source dataset frozen  : {match}  ({src['path']})")
for pair in manifest["pairs"]:
    tgt = pair["target"]
    actual = _sha(root / tgt["eval_set"])
    match = actual == tgt.get("sha256")
    ok &= match
    print(f"  target frozen [{pair['id']:>22}] : {match}  (n={tgt.get('n')})")
if not ok:
    sys.exit("pre-flight FAILED: a frozen dataset hash does not match the manifest")
print("  pre-flight OK")
PYEOF

# ---------------------------------------------------------------------------
# Stage 1 — run, analyse, and (unless --no-pdf) render the PDF artifact.
echo
echo "--- Stage 1: run + statistical analysis + artifact ---"
RUN_LOG="$(mktemp)"
trap 'rm -f "$RUN_LOG"' EXIT

STUDY_ARGS=(--pairs "$PAIRS" --results-root "$RESULTS_ROOT" \
  --repo-root "$ROOT" --seed "$SEED")
if [[ "$SKIP_PDF" == "0" ]]; then
  STUDY_ARGS+=(--tex "$TEX_PATH" --pdf "$PDF_PATH")
fi

"$PY" -m noosphere.transfer.study "${STUDY_ARGS[@]}" | tee "$RUN_LOG"

# pdflatex build noise (.aux/.log/.out) is cleaned up by study.py itself;
# the .tex and .pdf are the artifacts.

RUN_STAMP="$(grep -E '^RUN_STAMP=' "$RUN_LOG" | head -1 | cut -d= -f2)"
OUTCOMES="$(grep -E '^OUTCOMES=' "$RUN_LOG" | head -1 | cut -d= -f2-)"
if [[ -z "$RUN_STAMP" ]]; then
  echo "could not determine run stamp from study output" >&2
  exit 1
fi
RUN_DIR="$RESULTS_ROOT/$RUN_STAMP"
echo
echo "  run directory : $RUN_DIR"
echo "  outcomes      : $OUTCOMES"

# ---------------------------------------------------------------------------
# Stage 2 — publish to the public site so the methodology page goes live.
if [[ "$SKIP_PUBLISH" == "0" ]]; then
  echo
  echo "--- Stage 2: publish to the public methodology page ---"
  mkdir -p "$PUBLIC_DIR/latest" "$PUBLIC_PDF_DIR"
  cp "$RUN_DIR/results.json"  "$PUBLIC_DIR/latest/results.json"
  cp "$RUN_DIR/envelope.json" "$PUBLIC_DIR/latest/envelope.json"
  cp "$RUN_DIR/analysis.md"   "$PUBLIC_DIR/latest/analysis.md"
  if [[ "$SKIP_PDF" == "0" ]] && [[ -f "$PDF_PATH" ]]; then
    cp "$PDF_PATH" "$PUBLIC_PDF_DIR/Cross_Domain_Transfer_Study.pdf"
    echo "  mirrored PDF -> $PUBLIC_PDF_DIR/Cross_Domain_Transfer_Study.pdf"
  fi
  echo "  published latest run -> $PUBLIC_DIR/latest/"
else
  echo
  echo "--- Stage 2: publish SKIPPED (--no-publish) ---"
fi

echo
echo "=== Cross-Domain Transfer Study v1 full run complete ==="
echo "  run dir : $RUN_DIR"
echo "  results : $RUN_DIR/results.json"
echo "  analysis: $RUN_DIR/analysis.md"
[[ "$SKIP_PDF" == "0" ]] && echo "  pdf     : $PDF_PATH"
echo "  tex     : $TEX_PATH"
