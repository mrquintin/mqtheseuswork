#!/usr/bin/env python3
"""CI lint: refuse to ship component files containing hardcoded colors.

Reads the design-system allow-list in
``theseus-codex/src/lib/design/tokens.ts`` (`APPROVED_CSS_VARS`) and the
CSS variables declared in ``theseus-codex/src/app/globals.css``. Any
``#rrggbb`` / ``#rgb`` literal or named CSS color (red, blue, etc.) found
in component sources that does *not* match an approved reference is a
violation.

The lint runs against:

  - ``theseus-codex/src/components/**/*.tsx``
  - ``theseus-codex/src/components/**/*.ts``

The token file itself, the global stylesheet, this script, and the test
``__tests__`` tree are intentionally exempt — that's where the canonical
declarations *live*.

Run:
    scripts/check_no_hardcoded_colors.py             # exits 1 if any hit
    scripts/check_no_hardcoded_colors.py --json      # JSON for CI

Per-line opt-out (only for documented exceptions, e.g. an inline
data-URI gradient swatch):

    // design-system: allow-color

"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP = REPO_ROOT / "theseus-codex"
COMPONENTS_DIR = APP / "src" / "components"
TOKENS_FILE = APP / "src" / "lib" / "design" / "tokens.ts"
GLOBALS_CSS = APP / "src" / "app" / "globals.css"

ALLOW_PRAGMA = "design-system: allow-color"

# Named CSS colors we treat as "color literals". Limited to the obvious
# ones — the Codex aesthetic forbids primaries by intent, so this list is
# tight on purpose.
NAMED_COLORS = {
    "red",
    "green",
    "blue",
    "yellow",
    "purple",
    "orange",
    "pink",
    "cyan",
    "magenta",
    "brown",
    "navy",
    "teal",
    "olive",
    "lime",
    "aqua",
    "fuchsia",
    "silver",
    "maroon",
    "gray",
    "grey",
    "white",
    "black",
}

HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
# named-color matcher: word boundary, lowercased, not inside an identifier
NAMED_RE = re.compile(
    r"(?<![\w-])(" + "|".join(sorted(NAMED_COLORS)) + r")(?![\w-])"
)
APPROVED_ARRAY_RE = re.compile(
    r"APPROVED_CSS_VARS\s*:\s*readonly\s+string\[\]\s*=\s*\[(.*?)\]",
    re.DOTALL,
)
CSS_VAR_DECL_RE = re.compile(r"(--[a-z][a-z0-9-]*)\s*:")
STRING_ITEM_RE = re.compile(r'"(--[a-z0-9-]+)"')


def load_approved_vars() -> set[str]:
    """Approved variables = `APPROVED_CSS_VARS` plus everything declared in
    globals.css (we trust the stylesheet itself as canonical)."""
    approved: set[str] = set()

    if TOKENS_FILE.exists():
        text = TOKENS_FILE.read_text(encoding="utf8")
        match = APPROVED_ARRAY_RE.search(text)
        if match:
            for item in STRING_ITEM_RE.finditer(match.group(1)):
                approved.add(item.group(1))

    if GLOBALS_CSS.exists():
        css = GLOBALS_CSS.read_text(encoding="utf8")
        # Strip CSS comments so commented-out tokens don't sneak in.
        css = re.sub(r"/\*[\s\S]*?\*/", "", css)
        for decl in CSS_VAR_DECL_RE.finditer(css):
            approved.add(decl.group(1))

    return approved


def iter_component_files() -> list[Path]:
    if not COMPONENTS_DIR.exists():
        return []
    files: list[Path] = []
    for path in COMPONENTS_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".ts", ".tsx"}:
            continue
        # Skip the design directory's own primitives — they *define* the
        # vocabulary and are allowed to reference `color.stone` etc.
        # (which lint-wise looks fine; the inline overrides for data-driven
        # pills are tagged with the pragma.)
        files.append(path)
    return files


def check_file(path: Path, approved: set[str]) -> list[tuple[int, str, str]]:
    """Return violations as (line_no, kind, snippet)."""
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf8")
    except (OSError, UnicodeDecodeError):
        return violations
    for line_no, line in enumerate(text.splitlines(), start=1):
        if ALLOW_PRAGMA in line:
            continue
        for hit in HEX_RE.finditer(line):
            value = hit.group(0)
            violations.append((line_no, "hex", value))
        for hit in NAMED_RE.finditer(line):
            value = hit.group(1)
            # Skip if it looks like part of a CSS property (color: red would
            # still trigger — that's intentional). The named-color list is
            # the noisy part; we tolerate `color:` etc., but the actual
            # value `red` is the violation.
            violations.append((line_no, "named", value))
    # The approved-set is only relevant to filter out *false* positives
    # for hex matches embedded inside `var(--foo, #fallback)`. If the
    # surrounding context references an approved var, drop the hex.
    if violations:
        approved_pattern = re.compile(
            r"var\((--[a-z0-9-]+)\s*,\s*(#[0-9a-fA-F]{3,8})"
        )
        # Build a set of (line, hex) pairs that are inside an approved fallback.
        text_lines = text.splitlines()
        forgiven: set[tuple[int, str]] = set()
        for line_no, line in enumerate(text_lines, start=1):
            for hit in approved_pattern.finditer(line):
                var_name, fallback = hit.group(1), hit.group(2)
                if var_name in approved:
                    forgiven.add((line_no, fallback))
        violations = [v for v in violations if (v[0], v[2]) not in forgiven]
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    approved = load_approved_vars()
    all_violations: dict[str, list[tuple[int, str, str]]] = {}
    for path in iter_component_files():
        hits = check_file(path, approved)
        if hits:
            rel = path.relative_to(REPO_ROOT)
            all_violations[str(rel)] = hits

    if args.json:
        payload = {
            "approved_count": len(approved),
            "violations": {
                path: [
                    {"line": line, "kind": kind, "value": val}
                    for line, kind, val in hits
                ]
                for path, hits in all_violations.items()
            },
        }
        print(json.dumps(payload, indent=2))
    else:
        if not all_violations:
            print(
                f"OK — no hardcoded colors in {COMPONENTS_DIR.relative_to(REPO_ROOT)}; "
                f"{len(approved)} approved CSS vars."
            )
        else:
            total = sum(len(v) for v in all_violations.values())
            print(
                f"FAIL — {total} hardcoded color reference(s) outside the design-system "
                f"allow-list:\n"
            )
            for path, hits in sorted(all_violations.items()):
                for line, kind, value in hits:
                    print(f"  {path}:{line}: {kind} {value}")
            print(
                "\nFix: route the color through `tokens.color.*` (see "
                "`theseus-codex/src/lib/design/tokens.ts`) or, if the value "
                "is a documented data-driven exception, add a "
                f"`{ALLOW_PRAGMA}` comment on the same line."
            )

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
