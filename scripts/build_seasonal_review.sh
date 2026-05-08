#!/usr/bin/env bash
# Build the PDF for a quarterly seasonal review from its .tex source.
#
# Usage:
#   scripts/build_seasonal_review.sh <slug>
#   scripts/build_seasonal_review.sh docs/seasonal/<slug>/review.tex
#
# The .tex is the source of truth; this script re-runs pdflatex twice
# (the second pass settles refs/TOC) and leaves the PDF next to the
# .tex. If pdflatex is not on PATH, exits 0 with a notice — the .tex
# remains usable on its own.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARG="${1:-}"

if [[ -z "$ARG" ]]; then
  echo "Usage: $0 <slug-or-tex-path>" >&2
  exit 2
fi

if [[ -f "$ARG" ]]; then
  TEX_PATH="$ARG"
else
  TEX_PATH="$ROOT/docs/seasonal/$ARG/review.tex"
fi

if [[ ! -f "$TEX_PATH" ]]; then
  echo "tex not found: $TEX_PATH" >&2
  exit 2
fi

OUT_DIR="$(cd "$(dirname "$TEX_PATH")" && pwd)"

if ! command -v pdflatex >/dev/null 2>&1; then
  echo "pdflatex not on PATH; .tex is the source of truth: $TEX_PATH" >&2
  exit 0
fi

cd "$OUT_DIR"
pdflatex -interaction=nonstopmode -halt-on-error "$(basename "$TEX_PATH")" >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error "$(basename "$TEX_PATH")" >/dev/null

PDF="${TEX_PATH%.tex}.pdf"
if [[ -f "$PDF" ]]; then
  echo "Wrote $PDF"
else
  echo "pdflatex did not produce a PDF for $TEX_PATH" >&2
  exit 1
fi
