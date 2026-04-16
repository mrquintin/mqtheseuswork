"""Scan MIP bundles for firm-private identifiers before distribution."""

from __future__ import annotations

from pathlib import Path

_DENY_PATTERNS: list[str] = [
    "THESEUS_INTERNAL",
    "theseus_secret",
    "FIRM_PRIVATE",
    "internal_only",
    "__theseus_private__",
    ".env.production",
    ".env.staging",
    "credentials.json",
    "secrets.yaml",
    "private_key.pem",
    "signing.key",
]

_DENY_FILENAMES: set[str] = {
    ".env",
    ".env.production",
    ".env.staging",
    "credentials.json",
    "secrets.yaml",
    "secrets.json",
    "private_key.pem",
    "signing.key",
    ".git-credentials",
    ".netrc",
}


class LeakDetected(Exception):
    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__(f"Leak check failed: {len(violations)} violation(s) found")


def leak_check(
    mip_dir: Path,
    *,
    extra_deny_patterns: list[str] | None = None,
    extra_deny_filenames: set[str] | None = None,
) -> None:
    deny_patterns = _DENY_PATTERNS + (extra_deny_patterns or [])
    deny_filenames = _DENY_FILENAMES | (extra_deny_filenames or set())

    violations: list[str] = []

    for p in sorted(mip_dir.rglob("*")):
        if p.name in deny_filenames:
            violations.append(f"Denied filename: {p.relative_to(mip_dir)}")

        if p.is_file() and _is_text(p):
            try:
                content = p.read_text(errors="replace")
            except Exception:
                continue
            for pattern in deny_patterns:
                if pattern in content:
                    violations.append(
                        f"Denied pattern '{pattern}' in {p.relative_to(mip_dir)}"
                    )

    if violations:
        raise LeakDetected(violations)


def _is_text(path: Path) -> bool:
    text_suffixes = {
        ".py", ".json", ".yaml", ".yml", ".md", ".txt", ".cfg",
        ".toml", ".ini", ".sh", ".cff", ".html", ".xml", ".csv",
    }
    return path.suffix.lower() in text_suffixes or path.suffix == ""
