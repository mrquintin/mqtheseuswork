#!/usr/bin/env bash
# build_memo_pdf.sh — the canonical entrypoint for rendering an
# Investment-memo LaTeX file to PDF (Round 19 prompt 11).
#
# Usage:
#     bash docs/memos/build_memo_pdf.sh <path/to/memo.tex>
#
# Two-pass pdflatex run to resolve references; logs go to the .log
# next to the .tex. Exits non-zero on failure so Python callers can
# detect it.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $(basename "$0") <memo.tex>" >&2
    exit 2
fi

TEX_PATH="$1"
if [[ ! -f "$TEX_PATH" ]]; then
    echo "build_memo_pdf: tex file not found: $TEX_PATH" >&2
    exit 2
fi

if ! command -v pdflatex >/dev/null 2>&1; then
    echo "build_memo_pdf: pdflatex not on PATH" >&2
    exit 3
fi

TEX_DIR="$(cd "$(dirname "$TEX_PATH")" && pwd)"
TEX_FILE="$(basename "$TEX_PATH")"

# Two-pass compile so refs (and any future bibliography) resolve.
for pass in 1 2; do
    (
        cd "$TEX_DIR"
        pdflatex -interaction=nonstopmode -halt-on-error \
            -output-directory="$TEX_DIR" "$TEX_FILE" >/dev/null
    )
done

# Best-effort cleanup of LaTeX aux files. Keep the .log for debugging.
for ext in aux toc out fls fdb_latexmk; do
    rm -f "${TEX_PATH%.tex}.${ext}"
done

PDF_PATH="${TEX_PATH%.tex}.pdf"
if [[ ! -f "$PDF_PATH" ]]; then
    echo "build_memo_pdf: pdflatex finished but $PDF_PATH is missing" >&2
    exit 4
fi
