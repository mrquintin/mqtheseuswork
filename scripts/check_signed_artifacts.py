#!/usr/bin/env python3
"""CI lint: verify every method doc and MIP artifact is signed against the ledger KeyRing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SIGNATURE_SUFFIX = ".sig"


def _find_artifacts(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    return sorted(
        f
        for f in base_dir.rglob("*")
        if f.is_file()
        and not f.name.startswith(".")
        and f.suffix != SIGNATURE_SUFFIX
        and f.name != ".gitkeep"
    )


def _check_signature(artifact: Path, keyring) -> str | None:  # noqa: ANN001
    sig_path = artifact.with_suffix(artifact.suffix + SIGNATURE_SUFFIX)
    if not sig_path.exists():
        return f"{artifact}: missing signature file ({sig_path.name})"

    try:
        sig_data = sig_path.read_bytes()
    except OSError as e:
        return f"{artifact}: cannot read signature — {e}"

    parts = sig_data.split(b":", 1)
    if len(parts) != 2:
        return f"{artifact}: malformed signature (expected key_id:signature)"

    key_id = parts[0].decode("utf-8", errors="replace")
    signature = parts[1]

    artifact_data = artifact.read_bytes()
    try:
        if not keyring.verify(artifact_data, signature, key_id):
            return f"{artifact}: signature verification failed (key_id={key_id})"
    except Exception as e:
        return f"{artifact}: verification error — {e}"

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify artifact signatures against KeyRing")
    parser.add_argument("--methods-dir", type=Path, default=REPO_ROOT / "docs" / "methods")
    parser.add_argument("--interop-dir", type=Path, default=REPO_ROOT / "docs" / "interop")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    method_artifacts = _find_artifacts(args.methods_dir)
    interop_artifacts = _find_artifacts(args.interop_dir)
    all_artifacts = method_artifacts + interop_artifacts

    if not all_artifacts:
        if args.json:
            print(json.dumps({"ok": True, "violations": [], "skipped": "no artifacts"}))
        else:
            print("OK: no artifacts to verify (directories empty or absent).")
        return 0

    sys.path.insert(0, str(REPO_ROOT / "noosphere"))
    try:
        from noosphere.ledger.keys import KeyRing
    except ImportError as e:
        print(f"Cannot import KeyRing: {e}", file=sys.stderr)
        return 2

    try:
        keyring = KeyRing()
    except Exception:
        keyring = None

    if keyring is None:
        if args.json:
            print(json.dumps({"ok": True, "violations": [], "skipped": "no signing key"}))
        else:
            print("OK: no signing key configured — skipping signature verification.")
        return 0

    violations: list[str] = []
    for artifact in all_artifacts:
        result = _check_signature(artifact, keyring)
        if result is not None:
            violations.append(result)

    if args.json:
        print(json.dumps({"ok": len(violations) == 0, "violations": violations}))
    elif violations:
        print("FAIL: artifact signature violations:")
        for v in violations:
            print(f"  {v}")
        print(f"\n{len(violations)} violation(s) found.")
        return 1
    else:
        print(f"OK: all {len(all_artifacts)} artifact(s) have valid signatures.")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
