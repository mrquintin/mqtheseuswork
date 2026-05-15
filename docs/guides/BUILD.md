# Building the Theseus user guides

The six PDF user guides under `docs/guides/` are compiled with
**pdflatex**. This matches the founder's standing rule for documents
in this repository.

## Quick build

From this directory:

```bash
./build_pdfs.sh
```

That compiles all six guides (twice each, so references and TOC
resolve), greps the LaTeX logs for errors, verifies each output PDF
is under 5 MB, and verifies that every relative `\href` target
resolves to a file that exists.

`make` (no argument) is equivalent to `./build_pdfs.sh`. `make
clean` removes the intermediate `.aux`, `.log`, `.out`, `.toc` files.
`make distclean` also removes the PDFs.

Per-guide rebuild during edits:

```bash
make 03_The_Oracle
```

## What the build needs

- **pdflatex** (TeX Live or MacTeX). The reference build is TeX
  Live 2024 or newer.
- The standard TeX Live packages: `geometry`, `mathpazo`, `helvet`,
  `microtype`, `parskip`, `enumitem`, `booktabs`, `longtable`,
  `titlesec`, `xcolor`, `fancyhdr`, `fancyvrb`, `graphicx`,
  `tcolorbox`, `hyperref`. All are present in TeX Live's `scheme-
  full` and in the GitHub-Actions setup we use in
  `.github/workflows/build-guides.yml`.
- Optional: `codespell` for the spell-check pass (run on the `.tex`
  source, not on the PDF). The CI workflow installs it when
  available.

## Why pdflatex (and not LuaLaTeX / XeLaTeX)

Two reasons:

1. The founder's standing preference is pdflatex for repository docs.
2. The guides use only the AMS, hyperref, tcolorbox, and pdflatex-
   compatible font packages (`mathpazo`, `helvet`). No system font
   substitution is required.

The house style asks for "11pt Charter or Palatino body." Charter is
not part of stock TeX Live distributions, so `_preamble.tex` uses
Palatino via `mathpazo`. If a host has Charter installed and we want
to switch, swap `\usepackage{mathpazo}` for the appropriate Charter
package; no other change is needed. This deviation from the house
style is documented here per the spec.

## Screenshots

Each guide references screenshots through a `\screenshot{file}{caption}{label}`
macro defined in `_preamble.tex`. The macro wraps the image in an
`\IfFileExists{...}` block, so the build does not fail before the
Playwright capture pass has produced the screenshots. Until then, the
guide PDFs render a small italic placeholder where the figure would
be.

Drop captured PNGs into `docs/guides/screenshots/` using the file
names referenced from the `.tex` sources. The build script reports
which screenshots are present and which are still missing.

## Cross-link check

The build script greps every `\href{...}{...}` in the `.tex` sources
and verifies that the target is either an absolute URL (`http://`,
`https://`, `mailto:`) or an existing file in `docs/guides/`. The
guides cross-link to each other through filenames like
`02_Knowledge_and_Principles.pdf`, so the check fires on a missing
or misnamed sibling guide.

## CI

`.github/workflows/build-guides.yml` runs `./build_pdfs.sh` on every
PR that touches `docs/guides/**`. The workflow uploads the resulting
PDFs as artifacts so they can be downloaded from the run page.

## Empty-state contract

The build must succeed against an "empty-state corpus" --- the repo
checked out fresh, no captured screenshots, no operator config. That
is enforced by the screenshot fallback macro and by avoiding any
bibliographic references that would need a `.bib` file.
