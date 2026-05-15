#!/usr/bin/env python3
"""CI lint: assert every method RATIONALE has the stable section structure
and that its paper citations cross-link to ``docs/methods/References.bib``.

Round 17 extended many methods (domain bounds, failure-mode catalogs,
severity inputs) without always updating the hand-authored
``<method>.RATIONALE.md`` next to the method source. Round 17's
``scripts/check_doc_drift.py`` catches ``depends_on`` drift and (now) the
FAILURES cross-link; this script enforces the two things doc-drift cannot:

1. **Structure.** Every RATIONALE adopts the seven-section contract:
   Purpose, Inputs, Outputs, Algorithm, Domain, Failure Modes, References.
   A missing section fails CI. Stable structure is what lets the seasonal
   review and the auto-paper generator consume RATIONALEs mechanically.

2. **Cross-link audit.** Every ``[@bibkey]`` citation in a References
   section must resolve to an entry in ``docs/methods/References.bib``, and
   every entry there must carry a usable locator — a well-formed URL, DOI,
   or arXiv id. A broken DOI (or a citation with no entry) fails CI.

Usage:
    python scripts/check_rationale_structure.py
    python scripts/check_rationale_structure.py --methods-dir <dir> --bib <file>

The check functions (:func:`check_structure`, :func:`audit_crosslinks`,
:func:`audit_bib_entries`, :func:`parse_bib`) are importable so tests can
exercise them against synthetic RATIONALEs without touching the repo tree.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The seven required sections, in their canonical order. A RATIONALE is
# "structurally valid" iff every one of these appears as a `## ` heading.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "Purpose",
    "Inputs",
    "Outputs",
    "Algorithm",
    "Domain",
    "Failure Modes",
    "References",
)

RATIONALE_SUFFIX = ".RATIONALE.md"

# `[@bibkey]` — the citation form used inside a References section.
_CITATION_RE = re.compile(r"\[@([A-Za-z0-9_:.\-]+)\]")
# `## Heading` — level-2 markdown headings only.
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
# `@type{key,` — the head of a BibTeX entry.
_BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
# `field = {value}` or `field = "value"` inside a BibTeX entry.
_BIB_FIELD_RE = re.compile(
    r"(\w+)\s*=\s*(?:\{(.*?)\}|\"(.*?)\")\s*,?\s*$",
    re.MULTILINE | re.DOTALL,
)

# Locator validators. Kept deliberately offline — CI must not depend on the
# network — so "working" means "well-formed", not "resolves right now".
_URL_RE = re.compile(r"^https?://\S+$")
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


# ── Structure check ─────────────────────────────────────────────────────────


def section_headings(text: str) -> list[str]:
    """Return the ordered list of `## ` headings in a RATIONALE body."""
    return [m.group(1).strip() for m in _H2_RE.finditer(text)]


def check_structure(path: Path) -> list[str]:
    """Return structural violations for one RATIONALE file.

    A violation is a required section that is absent. Order is reported as
    a separate (non-fatal-by-itself but still failing) violation so authors
    keep the canonical sequence the downstream generators expect.
    """
    violations: list[str] = []
    text = path.read_text(encoding="utf-8")
    headings = section_headings(text)
    heading_set = set(headings)

    missing = [s for s in REQUIRED_SECTIONS if s not in heading_set]
    for s in missing:
        violations.append(f"{path.name}: missing required section '## {s}'")

    # Order check only when all sections are present — otherwise the
    # missing-section violations above are the actionable signal.
    if not missing:
        present_in_order = [h for h in headings if h in REQUIRED_SECTIONS]
        if present_in_order != list(REQUIRED_SECTIONS):
            violations.append(
                f"{path.name}: sections out of order — expected "
                f"{list(REQUIRED_SECTIONS)}, found {present_in_order}"
            )
    return violations


# ── Bibliography parsing + audit ────────────────────────────────────────────


def parse_bib(path: Path) -> dict[str, dict[str, str]]:
    """Parse a BibTeX file into ``{key: {field: value}}``.

    Intentionally small: it understands ``@type{key, field = {..}, ...}``
    well enough for the audit. It is not a general BibTeX parser.
    """
    entries: dict[str, dict[str, str]] = {}
    if not path.exists():
        return entries
    raw = path.read_text(encoding="utf-8")
    # Strip line comments (`%` to end of line) the way BibTeX does.
    raw = re.sub(r"(?m)%.*$", "", raw)

    starts = [(m.start(), m.group(2)) for m in _BIB_ENTRY_RE.finditer(raw)]
    for i, (start, key) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(raw)
        body = raw[start:end]
        fields: dict[str, str] = {}
        for fm in _BIB_FIELD_RE.finditer(body):
            name = fm.group(1).lower()
            value = (fm.group(2) or fm.group(3) or "").strip()
            # Collapse internal whitespace from wrapped values.
            fields[name] = re.sub(r"\s+", " ", value)
        entries[key] = fields
    return entries


def _locator_status(fields: dict[str, str]) -> str | None:
    """Return ``None`` if the entry carries a usable, well-formed locator,
    else a human-readable reason it does not."""
    url = fields.get("url", "")
    doi = fields.get("doi", "")
    eprint = fields.get("eprint", "")

    if doi and not _DOI_RE.match(doi):
        return f"malformed DOI {doi!r}"
    if eprint and not _ARXIV_RE.match(eprint):
        return f"malformed arXiv id {eprint!r}"
    if url and not _URL_RE.match(url):
        return f"malformed URL {url!r}"

    if (url and _URL_RE.match(url)) or (doi and _DOI_RE.match(doi)) or (
        eprint and _ARXIV_RE.match(eprint)
    ):
        return None
    return "no usable locator (needs a well-formed url, doi, or eprint)"


def audit_bib_entries(bib_entries: dict[str, dict[str, str]]) -> list[str]:
    """Every bib entry must carry a working URL / DOI / arXiv id."""
    violations: list[str] = []
    for key in sorted(bib_entries):
        reason = _locator_status(bib_entries[key])
        if reason is not None:
            violations.append(f"References.bib: entry '{key}' — {reason}")
    return violations


def references_section(text: str) -> str:
    """Return the body of the `## References` section, or '' if absent."""
    headings = list(_H2_RE.finditer(text))
    for i, m in enumerate(headings):
        if m.group(1).strip() == "References":
            start = m.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            return text[start:end]
    return ""


def extract_citations(text: str) -> set[str]:
    """Return the set of `[@bibkey]` citation keys in a RATIONALE's
    References section. Citations outside that section are ignored — the
    section is the contract surface the audit governs."""
    return set(_CITATION_RE.findall(references_section(text)))


def audit_crosslinks(
    rationale_text: str,
    bib_entries: dict[str, dict[str, str]],
    *,
    label: str = "<rationale>",
) -> list[str]:
    """Return cross-link violations for one RATIONALE.

    A violation is a ``[@key]`` citation whose key has no entry in the
    bibliography. (Whether the *entry* is well-formed is
    :func:`audit_bib_entries`' job — kept separate so the synthetic test
    can target one without the other.)
    """
    violations: list[str] = []
    for key in sorted(extract_citations(rationale_text)):
        if key not in bib_entries:
            violations.append(
                f"{label}: citation '[@{key}]' has no entry in References.bib"
            )
    return violations


# ── Driver ──────────────────────────────────────────────────────────────────


def collect_rationales(methods_dir: Path) -> list[Path]:
    return sorted(methods_dir.glob(f"*{RATIONALE_SUFFIX}"))


def run(methods_dir: Path, bib_path: Path) -> list[str]:
    """Run both checks across every RATIONALE. Returns all violations."""
    violations: list[str] = []
    bib_entries = parse_bib(bib_path)

    if not bib_path.exists():
        violations.append(f"missing bibliography: {bib_path}")
    else:
        violations.extend(audit_bib_entries(bib_entries))

    rationales = collect_rationales(methods_dir)
    if not rationales:
        violations.append(f"no RATIONALE files found under {methods_dir}")

    for path in rationales:
        violations.extend(check_structure(path))
        violations.extend(
            audit_crosslinks(
                path.read_text(encoding="utf-8"), bib_entries, label=path.name
            )
        )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check method RATIONALE structure + citation cross-links"
    )
    parser.add_argument(
        "--methods-dir",
        type=Path,
        default=Path("noosphere/noosphere/methods"),
        help="Directory holding *.RATIONALE.md files.",
    )
    parser.add_argument(
        "--bib",
        type=Path,
        default=Path("docs/methods/References.bib"),
        help="Centralized BibTeX bibliography.",
    )
    args = parser.parse_args()

    violations = run(args.methods_dir, args.bib)
    if violations:
        print("RATIONALE structure / cross-link check failed:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nEvery RATIONALE needs the seven sections "
            f"({', '.join(REQUIRED_SECTIONS)}) and every [@key] citation "
            "must resolve to docs/methods/References.bib.",
            file=sys.stderr,
        )
        return 1

    print(
        f"RATIONALE structure OK: {len(collect_rationales(args.methods_dir))} "
        "files, all seven sections present, all citations cross-linked."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
