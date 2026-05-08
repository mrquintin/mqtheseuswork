#!/usr/bin/env python3
"""CI lint: refuse to ship if the publication signing key is reachable from the web app.

The publication signing key (`~/.theseus/keys/publication/`) lives
strictly on the noosphere CLI side. Only the CLI signs; the web app
serves the public artefact (the `PublicationSignature` row + the
signature.json endpoint). If anything under `theseus-codex/` ever
imports `noosphere.ledger.publication_signing` (or names the key
directory), an attacker who pivoted from a web RCE could mint a
signature directly. This check prevents that regression.

Forbidden in `theseus-codex/`:
  - imports of `noosphere.ledger.publication_signing` (Python or TS shim)
  - imports of `noosphere/ledger/keys` (Python helper that touches the dir)
  - references to the env var `THESEUS_PUBLICATION_KEY_DIR`
  - references to the literal `.theseus/keys/publication`

The check intentionally does *not* flag the public signature endpoint
(`src/app/api/public/signature/[slug]/route.ts`) — that route reads
the public artefact from the DB and is the legitimate public-facing
serving path.

Run:
    scripts/check_signing_key_not_in_web.py            # CI mode
    scripts/check_signing_key_not_in_web.py --json     # JSON output

Exits 0 if clean, 1 on any violation.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_APP_ROOT = REPO_ROOT / "theseus-codex"

SCAN_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"}

SKIP_DIRS = {
    "node_modules", ".next", "dist", "build", "out", "__pycache__",
    "test-results", "playwright-report", "coverage",
}

FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("publication_signing_import", re.compile(
        r"""(?xi)
        (?:
            from\s+["']?noosphere(?:[./])ledger(?:[./])publication_signing["']? |
            require\(\s*["']noosphere(?:[./])ledger(?:[./])publication_signing["']\s*\) |
            import\s+["']noosphere(?:[./])ledger(?:[./])publication_signing["']
        )
        """
    )),
    ("ledger_keys_import", re.compile(
        r"""(?xi)
        (?:
            from\s+["']?noosphere(?:[./])ledger(?:[./])keys["']? |
            require\(\s*["']noosphere(?:[./])ledger(?:[./])keys["']\s*\) |
            import\s+["']noosphere(?:[./])ledger(?:[./])keys["']
        )
        """
    )),
    ("key_dir_env", re.compile(r"\bTHESEUS_PUBLICATION_KEY_DIR\b")),
    ("key_dir_literal", re.compile(r"\.theseus[/\\]keys[/\\]publication\b")),
    ("nacl_signing_key_constructor", re.compile(r"\bSigningKey\s*\(")),
]

# Files that are *allowed* to mention the patterns (the threat model
# itself, this CI script, the public signature route — which reads the
# public artefact, not the key).
ALLOWLIST_SUFFIXES = {
    "src/app/api/public/signature/[slug]/route.ts",
}

ALLOWLIST_PRAGMA = re.compile(
    r"(?:#|//|/\*)\s*pragma:\s*signing[-_]key[-_]allowed",
    re.I,
)


def _should_skip(path: Path, web_root: Path) -> bool:
    rel_parts = path.relative_to(web_root).parts
    return any(part in SKIP_DIRS for part in rel_parts)


def scan_repo(web_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    if not web_root.exists():
        return findings
    for path in web_root.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip(path, web_root):
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        rel = path.relative_to(REPO_ROOT)
        if any(rel.as_posix().endswith(s) for s in ALLOWLIST_SUFFIXES):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if ALLOWLIST_PRAGMA.search(line):
                continue
            for pattern_id, regex in FORBIDDEN_PATTERNS:
                if regex.search(line):
                    findings.append(
                        {
                            "file": rel.as_posix(),
                            "line": lineno,
                            "pattern": pattern_id,
                            "snippet": line.strip()[:120],
                        }
                    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refuse to ship if the publication signing key is reachable from the web app.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--web-root",
        type=Path,
        default=WEB_APP_ROOT,
        help="Root of the web app to scan (default: theseus-codex/)",
    )
    args = parser.parse_args()

    findings = scan_repo(args.web_root)

    if args.json:
        print(json.dumps({"ok": len(findings) == 0, "findings": findings}, indent=2))
    elif findings:
        print(f"FAIL: web app references the publication signing key in {len(findings)} place(s):")
        for f in findings:
            print(f"  {f['file']}:{f['line']}  [{f['pattern']}]  {f['snippet']}")
        print(
            "\nThe publication signing key must NEVER be importable from the web app.\n"
            "Move the offending logic into the noosphere CLI, or expose it via a\n"
            "ledger artefact (PublicationSignature row) the web app reads on GET."
        )
    else:
        print("OK: web app does not reference the publication signing key.")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
