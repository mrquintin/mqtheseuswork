#!/usr/bin/env bash
# Build docs/architecture/Theseus_Architecture.pdf from the .tex distribution
# variant. The PDF is NOT canonical --- the Markdown
# (docs/architecture/Theseus_Architecture.md) is. This script exists only to
# produce the printable / distributable PDF.
#
# pdflatex is run twice so the table of contents and longtable references
# settle. If pdflatex is not installed the script skips cleanly (exit 0) and
# names the source of truth, matching scripts/build_robustness_ledger_pdf.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCH_DIR="$ROOT/docs/architecture"
TEX="$ARCH_DIR/Theseus_Architecture.tex"
PDF="$ARCH_DIR/Theseus_Architecture.pdf"

if [ ! -f "$TEX" ]; then
  echo "missing $TEX" >&2
  exit 1
fi

if ! command -v pdflatex >/dev/null 2>&1; then
  echo "pdflatex not installed; skipping PDF build." >&2
  echo "Source of truth remains the Markdown: $ARCH_DIR/Theseus_Architecture.md" >&2
  exit 0
fi

cd "$ARCH_DIR"
pdflatex -interaction=nonstopmode -halt-on-error Theseus_Architecture.tex >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error Theseus_Architecture.tex >/dev/null

# Clean the LaTeX intermediates; keep only the PDF.
rm -f Theseus_Architecture.aux Theseus_Architecture.log Theseus_Architecture.out \
      Theseus_Architecture.toc

if [ -f "$PDF" ]; then
  echo "Wrote $PDF"
else
  echo "pdflatex ran but $PDF was not produced" >&2
  exit 1
fi
