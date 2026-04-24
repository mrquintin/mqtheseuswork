#!/usr/bin/env bash
# Build docs/Robustness_Ledger.pdf from docs/Robustness_Ledger.md when pandoc is available.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MD="$ROOT/docs/Robustness_Ledger.md"
PDF="$ROOT/docs/Robustness_Ledger.pdf"
if ! command -v pandoc >/dev/null 2>&1; then
  echo "pandoc not installed; skipping PDF. Source of truth remains: $MD" >&2
  exit 0
fi
pandoc "$MD" -o "$PDF" --pdf-engine=pdflatex 2>/dev/null || pandoc "$MD" -o "$PDF"
echo "Wrote $PDF"
