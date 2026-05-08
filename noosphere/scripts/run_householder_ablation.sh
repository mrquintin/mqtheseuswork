#!/usr/bin/env bash
# Run the Householder-reflection ablation against the frozen QH-v1 dataset.
#
# Usage:
#   ./run_householder_ablation.sh [--dataset PATH] [--out DIR] [--no-pdf]
#
# Produces:
#   - benchmarks/quintin_hypothesis/v1/results/householder_ablation/ablation_results.json
#   - docs/research/Householder_Ablation.tex
#   - docs/research/Householder_Ablation.pdf
#   - theseus-codex/public/research/Householder_Ablation.pdf (mirrored
#     so the methodology page can link to it without extra serving setup)
#
# Numbers are regenerated from code on every run; no number is hand-edited.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATASET="$ROOT/benchmarks/quintin_hypothesis/v1/dataset.jsonl"
OUT_DIR="$ROOT/benchmarks/quintin_hypothesis/v1/results/householder_ablation"
TEX_PATH="$ROOT/docs/research/Householder_Ablation.tex"
PDF_PATH="$ROOT/docs/research/Householder_Ablation.pdf"
PUBLIC_PDF_DIR="$ROOT/theseus-codex/public/research"
PUBLIC_PDF_PATH="$PUBLIC_PDF_DIR/Householder_Ablation.pdf"
SKIP_PDF=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset) DATASET="$2"; shift 2;;
    --out) OUT_DIR="$2"; shift 2;;
    --no-pdf) SKIP_PDF=1; shift;;
    -h|--help) sed -n '2,15p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

mkdir -p "$OUT_DIR" "$(dirname "$TEX_PATH")" "$PUBLIC_PDF_DIR"

python -c "
from pathlib import Path
from noosphere.benchmarks.qh_ablations import run_ablation, write_tex_and_pdf

payload = run_ablation(
    Path(r'''$DATASET'''),
    output_dir=Path(r'''$OUT_DIR'''),
    repo_root=Path(r'''$ROOT'''),
)
if not $SKIP_PDF:
    tex_p, pdf_p, compiled = write_tex_and_pdf(
        payload,
        tex_path=Path(r'''$TEX_PATH'''),
        pdf_path=Path(r'''$PDF_PATH'''),
    )
    print(f'wrote {tex_p} (pdf compiled={compiled})')
else:
    print('skipped PDF render (--no-pdf)')
"

if [[ "$SKIP_PDF" == "0" ]] && [[ -f "$PDF_PATH" ]]; then
  cp "$PDF_PATH" "$PUBLIC_PDF_PATH"
  echo "mirrored PDF to $PUBLIC_PDF_PATH"
fi
