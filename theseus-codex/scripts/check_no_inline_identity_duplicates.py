#!/usr/bin/env python3
"""Refuse commits that hardcode the canonical "Philosopher in a Box"
strings outside of `theseus-codex/src/lib/copy/identity.ts`.

The four canonical strings are parsed directly out of the identity
module so this lint stays in sync as the module evolves. Any TS/TSX
file under `theseus-codex/src/` other than the identity module that
contains a verbatim match exits the script non-zero with the matching
file paths.

Scope:
  * Only TS/TSX source files are inspected — they are the files that
    can `import` from the identity module. Markdown (README), LaTeX
    (pitch deck), and other static documents are intentionally
    excluded; they cannot import.
  * The identity module itself is excluded.
  * The companion test (`__tests__/identity_copy.test.ts`) is excluded
    because it asserts the canonical strings as a contract.

Run from anywhere; the script resolves paths relative to itself.

Exit codes:
  0  no inline duplicates detected
  1  one or more offenders
  2  the identity module could not be parsed (run from a checkout)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
THESEUS_CODEX_ROOT = HERE.parent
SRC_ROOT = THESEUS_CODEX_ROOT / "src"
IDENTITY_MODULE = SRC_ROOT / "lib" / "copy" / "identity.ts"
TEST_FILE = THESEUS_CODEX_ROOT / "__tests__" / "identity_copy.test.ts"

CANONICAL_EXPORT_NAMES = (
    "THESEUS_TAGLINE",
    "THESEUS_ONE_PARAGRAPH",
    "THESEUS_LOGIC_VS_QUANT",
    "THESEUS_NOT_COMMERCIAL",
)

# Match `export const NAME = "..."` (single line) or
# `export const NAME =\n  "..."` (multi-line indented), with double or
# single quotes. Backtick template strings are also picked up — the
# identity module currently uses plain string literals, but the regex
# tolerates them so the lint does not break the moment someone adds a
# template literal.
EXPORT_RE_TEMPLATE = (
    r'export\s+const\s+{name}\s*(?::\s*[A-Za-z<>,\[\]\s]+)?\s*=\s*'
    r'(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|`((?:\\.|[^`\\])*)`)'
)


def parse_canonical_strings(identity_source: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in CANONICAL_EXPORT_NAMES:
        pattern = EXPORT_RE_TEMPLATE.format(name=name)
        match = re.search(pattern, identity_source)
        if not match:
            raise LookupError(
                f"could not parse export `{name}` from {IDENTITY_MODULE}. "
                "Did the declaration shape change?"
            )
        for group in match.groups():
            if group is not None:
                out[name] = _decode_string_literal(group)
                break
    return out


def _decode_string_literal(value: str) -> str:
    # Handle the small subset of escapes that appear in the identity
    # module's string literals (\", \\, \n, \t, \', \`). We don't need
    # full JS string semantics for canonical-string detection.
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            replacement = {
                '"': '"',
                "'": "'",
                "`": "`",
                "\\": "\\",
                "n": "\n",
                "t": "\t",
                "r": "\r",
            }.get(nxt)
            if replacement is not None:
                out.append(replacement)
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def iter_source_files() -> list[Path]:
    out: list[Path] = []
    for path in SRC_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".ts", ".tsx"}:
            continue
        out.append(path)
    return out


def main() -> int:
    if not IDENTITY_MODULE.exists():
        sys.stderr.write(
            f"check_no_inline_identity_duplicates: identity module not found at {IDENTITY_MODULE}\n"
        )
        return 2

    identity_source = IDENTITY_MODULE.read_text(encoding="utf-8")
    try:
        canonical = parse_canonical_strings(identity_source)
    except LookupError as exc:
        sys.stderr.write(f"check_no_inline_identity_duplicates: {exc}\n")
        return 2

    skip = {IDENTITY_MODULE.resolve(), TEST_FILE.resolve()}
    offenders: list[tuple[Path, str]] = []
    for path in iter_source_files():
        if path.resolve() in skip:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, literal in canonical.items():
            if literal and literal in text:
                offenders.append((path, name))

    if offenders:
        sys.stderr.write(
            "check_no_inline_identity_duplicates: canonical identity strings "
            "found outside the identity module. Import them from "
            "@/lib/copy/identity instead.\n"
        )
        for path, name in offenders:
            rel = path.relative_to(THESEUS_CODEX_ROOT)
            sys.stderr.write(f"  {rel} :: {name}\n")
        return 1

    sys.stdout.write(
        "check_no_inline_identity_duplicates: OK — no inline duplicates of "
        f"{len(canonical)} canonical strings across "
        f"{len(iter_source_files())} TS/TSX files.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
