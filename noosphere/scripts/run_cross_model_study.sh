#!/usr/bin/env bash
# Run the cross-model QH benchmark end-to-end.
#
# Usage:
#   ./run_cross_model_study.sh [--models a,b,c] [--budget N] [--dry-run]
#
# Reads API keys from the environment; missing keys cause that adapter
# to fail loud (the runner records the failure in the manifest and
# proceeds with the remaining models). Embedding vectors are written
# to ``$THESEUS_CROSS_MODEL_ROOT`` (default ~/.theseus/data/cross_model)
# and never committed to git. Only aggregate metrics and parquet
# prediction tables land under benchmarks/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATASET="$ROOT/benchmarks/quintin_hypothesis/v1/dataset.jsonl"
OUT_DIR="$ROOT/benchmarks/quintin_hypothesis/v1/results/cross_model"
FIG_DIR="$ROOT/docs/research/figures/cross_model"
PUBLIC_DIR="$ROOT/theseus-codex/public/qh-benchmark/cross-model"

MODELS_DEFAULT="hash-det,minilm-l6,bge-large,openai-3-large,voyage-3,cohere-en-v3"
MODELS="${MODELS:-$MODELS_DEFAULT}"
BUDGET="${THESEUS_CROSS_MODEL_BUDGET:-200}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --models) MODELS="$2"; shift 2;;
    --budget) BUDGET="$2"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    -h|--help)
      sed -n '2,12p' "$0"; exit 0;;
    *)
      echo "unknown arg: $1" >&2; exit 2;;
  esac
done

mkdir -p "$OUT_DIR" "$FIG_DIR" "$PUBLIC_DIR"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "would run: models=$MODELS budget=$BUDGET dataset=$DATASET out=$OUT_DIR"
  exit 0
fi

export THESEUS_CROSS_MODEL_BUDGET="$BUDGET"

# Stage 1 — embed + predict per model
python -c "
from pathlib import Path
from noosphere.benchmarks.cross_model_runner import CrossModelConfig, run_cross_model
models = '${MODELS}'.split(',')
cfg = CrossModelConfig(
    model_names=[m.strip() for m in models if m.strip()],
    dataset_path=Path('${DATASET}'),
    output_dir=Path('${OUT_DIR}'),
)
reports = run_cross_model(cfg)
for r in reports:
    print(f'  {r.model_name}: embedded {r.items_embedded}/{r.items_total}'
          + (f'  ERROR: {r.error}' if r.error else ''))
"

# Stage 2 — analyse and produce figures + JSON/MD
python -m noosphere.benchmarks.cross_model_analysis \
  --predictions-dir "$OUT_DIR" \
  --out-dir "$OUT_DIR" \
  --figures-dir "$FIG_DIR"

# Stage 3 — copy artefacts to the public site for the page to read
cp "$OUT_DIR/cross_model_analysis.json" "$PUBLIC_DIR/" 2>/dev/null || true
cp "$OUT_DIR/run_index.json" "$PUBLIC_DIR/" 2>/dev/null || true
cp "$FIG_DIR"/*.png "$PUBLIC_DIR/" 2>/dev/null || true

# Stage 4 — build the PDF (auto-generated numbers from analysis JSON)
python "$ROOT/noosphere/scripts/build_cross_model_pdf.py" \
  --analysis "$OUT_DIR/cross_model_analysis.json" \
  --figures "$FIG_DIR" \
  --tex "$ROOT/docs/research/Cross_Model_Geometry_Study.tex" \
  --pdf "$ROOT/docs/research/Cross_Model_Geometry_Study.pdf"

# Mirror the PDF to the public site so the download link works
cp "$ROOT/docs/research/Cross_Model_Geometry_Study.pdf" "$PUBLIC_DIR/" 2>/dev/null || true

echo "cross-model study complete."
echo "  results : $OUT_DIR"
echo "  figures : $FIG_DIR"
echo "  pdf     : $ROOT/docs/research/Cross_Model_Geometry_Study.pdf"
