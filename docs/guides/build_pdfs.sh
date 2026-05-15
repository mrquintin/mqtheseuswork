#!/usr/bin/env bash
# Build all Theseus user guides with pdflatex.
#
# House rule: documents compile with pdflatex (not LuaLaTeX, not XeLaTeX).
# Each guide is run through pdflatex twice so references and the TOC
# resolve. The script:
#   1. compiles each .tex in this directory whose filename starts with
#      NN_<name>.tex (so the preamble file _preamble.tex is skipped);
#   2. greps the log for unrecoverable error markers and fails on any;
#   3. verifies each resulting PDF is under 5 MB;
#   4. verifies every \href target either resolves to an existing file
#      in this directory or is an absolute URL.
#
# Run from anywhere; the script cd's into its own directory.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

if ! command -v pdflatex >/dev/null 2>&1; then
  echo "build_pdfs.sh: pdflatex not found on PATH" >&2
  exit 2
fi

shopt -s nullglob
tex_files=(0[1-9]_*.tex 1[0-9]_*.tex)
shopt -u nullglob

if [[ ${#tex_files[@]} -eq 0 ]]; then
  echo "build_pdfs.sh: no guide .tex files found" >&2
  exit 2
fi

failed=()
for tex in "${tex_files[@]}"; do
  base="${tex%.tex}"
  echo ">>> compiling ${tex}"
  # Two passes so refs/TOC resolve. -halt-on-error so the first hard
  # failure stops that file's compilation immediately.
  pdflatex -interaction=nonstopmode -halt-on-error "$tex" >/dev/null
  pdflatex -interaction=nonstopmode -halt-on-error "$tex" >/dev/null

  log="${base}.log"
  # The pdflatex log uses '! ' as the marker for an unrecoverable error.
  # We also fail if any LaTeX Error / Emergency stop appears.
  if grep -E -i '^! |LaTeX Error|Emergency stop' "$log" >/dev/null; then
    echo "build_pdfs.sh: errors found in ${log}" >&2
    grep -E -i '^! |LaTeX Error|Emergency stop' "$log" >&2 || true
    failed+=("$tex")
    continue
  fi

  # Size guard: PDFs must be under 5 MB.
  pdf="${base}.pdf"
  if [[ ! -f "$pdf" ]]; then
    echo "build_pdfs.sh: ${pdf} not produced" >&2
    failed+=("$tex")
    continue
  fi
  bytes=$(wc -c <"$pdf" | tr -d ' ')
  if (( bytes >= 5 * 1024 * 1024 )); then
    echo "build_pdfs.sh: ${pdf} is ${bytes} bytes, over the 5 MB limit" >&2
    failed+=("$tex")
    continue
  fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
  echo "build_pdfs.sh: failed: ${failed[*]}" >&2
  exit 1
fi

# Cross-link check. Every \href{target}{...} that points at a relative
# path must resolve to an existing file in this directory. URLs (http,
# https, mailto) are skipped.
echo ">>> verifying \\href targets"
bad_links=()
while IFS= read -r line; do
  # line is "file:target"
  file="${line%%:*}"
  target="${line#*:}"
  # Strip in-document anchors and query strings.
  target="${target%%#*}"
  target="${target%%\?*}"
  case "$target" in
    http://*|https://*|mailto:*) continue ;;
  esac
  if [[ -z "$target" ]]; then continue; fi
  if [[ ! -e "$target" ]]; then
    bad_links+=("${file}: ${target}")
  fi
done < <(grep -oE '\\href\{[^}]+\}' *.tex | sed -E 's/\\href\{([^}]+)\}/\1/')

if [[ ${#bad_links[@]} -gt 0 ]]; then
  echo "build_pdfs.sh: broken \\href targets:" >&2
  printf '  %s\n' "${bad_links[@]}" >&2
  exit 1
fi

# Screenshot existence check. Every \screenshot{file}{...}{...} reference
# either has the file in screenshots/, or relies on the \IfFileExists
# fallback in _preamble.tex (which prints a stub line in the PDF). The
# build script treats a missing screenshot as a soft warning, since the
# empty-state corpus is allowed to ship without them.
echo ">>> screenshot inventory"
missing=()
present=()
while IFS= read -r line; do
  file="${line%%:*}"
  arg="${line#*:}"
  if [[ -e "screenshots/${arg}" ]]; then
    present+=("$arg")
  else
    missing+=("${file}: ${arg}")
  fi
done < <(grep -oE '\\screenshot\{[^}]+\}' *.tex | sed -E 's/\\screenshot\{([^}]+)\}/\1/')

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "build_pdfs.sh: ${#missing[@]} screenshots not yet captured (build proceeds):"
  printf '  %s\n' "${missing[@]}"
fi
echo "build_pdfs.sh: ${#present[@]} screenshots present"

echo ">>> build OK"
