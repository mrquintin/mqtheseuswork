#!/usr/bin/env python3
"""CI lint: refuse to ship if anything resembling a secret is committed.

Pattern catalogue, kept deliberately conservative so the false-positive
rate doesn't train operators to ignore the alert. We watch for:

  - AWS-style access keys (AKIA…, ASIA…)
  - GitHub tokens (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_)
  - Theseus API keys (`tcx_<12>_<48>` from `apiKeyAuth.ts`)
  - PEM private-key headers (RSA, EC, generic, OpenSSH, PGP)
  - Slack tokens (xoxb-, xoxp-, xoxa-, xoxr-)
  - Google API keys (AIza…)
  - Stripe keys (sk_live_, rk_live_)
  - Generic high-entropy `(password|secret|token|api[_-]?key)` literals

Run:
    scripts/check_no_secrets_in_code.py            # exits 1 if any hit
    scripts/check_no_secrets_in_code.py --json     # JSON for CI
    scripts/check_no_secrets_in_code.py --planted PATH  # test mode

Allow-list:
  - test fixtures with names matching `test_*`, `*.test.*`, `__tests__`
  - any line annotated with `# pragma: allowlist secret` (or `// pragma:`)
  - the file `docs/security/Threat_Model.md` (this catalogue itself)
  - this script (the catalogue lives here)

The script is the source of truth, not the docs; if you add a pattern,
the threat model must be updated to match (`docs/security/Threat_Model.md`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs",
    ".json", ".env", ".sh", ".yaml", ".yml", ".toml", ".ini",
    ".md", ".txt", ".html", ".pem",
}

SKIP_DIRS = {
    "node_modules", "__pycache__", ".next", ".git", ".venv", "venv",
    "dist", "build", "out", ".cache", ".turbo", ".pytest_cache",
    "test-results", "playwright-report", "coverage",
    ".venv-currents", ".venv-noosphere",
}

# Files that legitimately discuss the patterns themselves.
ALLOWLIST_FILES = {
    "docs/security/Threat_Model.md",
    "scripts/check_no_secrets_in_code.py",
    "scripts/check_signing_key_not_in_web.py",
}

ALLOWLIST_PRAGMA = re.compile(r"(?:#|//|/\*)\s*pragma:\s*allowlist\s+secret", re.I)

# Each pattern: (id, regex). We deliberately keep regexes anchored
# enough to avoid matching ordinary prose mentioning "password".
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:gh[psoaur]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("theseus_api_key", re.compile(r"\btcx_[a-z0-9]{12}_[a-z0-9]{40,}\b")),
    ("pem_private_key", re.compile(r"-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED|PRIVATE)\s+(?:PRIVATE\s+)?KEY-----")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("stripe_secret", re.compile(r"\b(?:sk|rk)_live_[0-9a-zA-Z]{24,}\b")),
    # Generic: "secret" / "password" / "token" / "api_key" assigned to a
    # high-entropy literal of >= 24 chars. Matches `FOO_SECRET = "…"` in
    # both Python and TS; allow-listed via the pragma above.
    ("generic_high_entropy", re.compile(
        r"""(?xi)
        \b(?:secret|password|passwd|token|api[_-]?key)\s*[=:]\s*
        ["']
        (?P<val>[A-Za-z0-9+/_=\-]{24,})
        ["']
        """
    )),
]

# Heuristic: skip generic matches whose value is obviously a placeholder.
PLACEHOLDER_VALUES = {
    "change-me", "change-me-to-a-random-hex-string",
    "your-secret-here", "YOUR_API_KEY_HERE",
    "REPLACE_ME", "REPLACE-ME", "xxx", "TODO",
    "dev-insecure-session-secret-do-not-use",
    "dev-insecure-csrf-secret-do-not-use",
    "dev-insecure-challenge-secret",
}

# Regex to detect "obviously a placeholder" by structure.
PLACEHOLDER_RE = re.compile(
    r"^(?:[xX]+|change[-_]?me\b|placeholder|example|dummy|insert[-_]?here)",
    re.I,
)


def _should_skip_dir(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _is_test_path(path: Path) -> bool:
    parts = set(path.parts)
    if "__tests__" in parts or "tests" in parts:
        return True
    name = path.name
    if name.startswith("test_"):
        return True
    if ".test." in name or ".spec." in name:
        return True
    return False


def _allowlisted_file(rel: Path) -> bool:
    return rel.as_posix() in ALLOWLIST_FILES


def _is_placeholder(val: str) -> bool:
    if val in PLACEHOLDER_VALUES:
        return True
    if PLACEHOLDER_RE.match(val):
        return True
    # repeated chars (e.g. "aaaa…")
    if len(set(val)) <= 2:
        return True
    return False


def scan_text(text: str, rel: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOWLIST_PRAGMA.search(line):
            continue
        for pattern_id, regex in PATTERNS:
            for m in regex.finditer(line):
                if pattern_id == "generic_high_entropy":
                    val = m.group("val")
                    if _is_placeholder(val):
                        continue
                # Skip test fixtures for the patterns whose "matches" are
                # routinely faked in unit tests. Real provider tokens
                # (AWS, Stripe, Slack, GitHub, Theseus) are flagged
                # everywhere — committing one in a test fixture is just
                # as catastrophic as committing it in prod code.
                if _is_test_path(rel) and pattern_id in {
                    "generic_high_entropy",
                    "pem_private_key",
                }:
                    continue
                findings.append(
                    {
                        "file": rel.as_posix(),
                        "line": lineno,
                        "pattern": pattern_id,
                        "match": m.group(0)[:80],
                    }
                )
    return findings


def scan_repo(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip_dir(path.relative_to(root)):
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        rel = path.relative_to(root)
        if _allowlisted_file(rel):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        # Skip very large generated files (e.g. lock files we did not exclude
        # by extension already — none today, but cheap guard).
        if len(text) > 2_000_000:
            continue
        findings.extend(scan_text(text, rel))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Refuse to ship if a secret is committed.")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--planted",
        type=Path,
        default=None,
        help="For CI smoke tests: scan a single file (planted secret) and exit nonzero on hit.",
    )
    args = parser.parse_args()

    if args.planted:
        text = args.planted.read_text(errors="replace")
        findings = scan_text(text, args.planted)
    else:
        findings = scan_repo(REPO_ROOT)

    if args.json:
        print(json.dumps({"ok": len(findings) == 0, "findings": findings}, indent=2))
    elif findings:
        print(f"FAIL: {len(findings)} candidate secret(s) detected:")
        for f in findings:
            print(f"  {f['file']}:{f['line']}  [{f['pattern']}]  {f['match']}")
        print(
            "\nIf any of these are intentional fixtures, add a `# pragma: allowlist secret`\n"
            "comment on the same line. If a real secret leaked, rotate it before committing."
        )
    else:
        print("OK: no secrets detected.")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
