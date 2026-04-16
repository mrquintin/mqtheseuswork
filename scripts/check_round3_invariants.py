#!/usr/bin/env python3
"""Umbrella CI runner: invoke every round-3 sub-check and report a single pass/fail."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CHECKS: list[dict] = [
    {"name": "methods-gated", "script": "scripts/check_methods_gated.py"},
    {"name": "no-hidden-globals", "script": "scripts/check_no_hidden_globals.py"},
    {"name": "gated-decorator-present", "script": "scripts/check_gated_decorator_present.py"},
    {"name": "public-store-only-gated", "script": "scripts/check_public_store_only_gated.py"},
    {
        "name": "packaging-selfcontainment",
        "script": "scripts/check_packaging_selfcontainment.py",
        "requires_dir": "out_dir",
    },
    {"name": "mip-versioning", "script": "scripts/check_mip_versioning.py"},
    {"name": "doc-drift", "script": "scripts/check_doc_drift.py"},
    {"name": "no-phone-home", "script": "scripts/check_no_phone_home.py"},
    {"name": "signed-artifacts", "script": "scripts/check_signed_artifacts.py"},
    {"name": "ui-uses-gated-api", "script": "scripts/check_ui_uses_gated_api.py"},
]


def _run_check(check: dict, python: str, timeout: int) -> dict:
    script = REPO_ROOT / check["script"]
    if not script.exists():
        return {
            "name": check["name"],
            "status": "skip",
            "exit_code": None,
            "duration_s": 0.0,
            "output": f"Script not found: {script}",
        }

    requires_dir = check.get("requires_dir")
    if requires_dir:
        target = REPO_ROOT / requires_dir
        if not target.exists() or not any(target.iterdir()):
            return {
                "name": check["name"],
                "status": "skip",
                "exit_code": None,
                "duration_s": 0.0,
                "output": f"Skipped: {requires_dir}/ does not exist or is empty",
            }

    cmd = [python, str(script)]
    if requires_dir:
        cmd.append(str(REPO_ROOT / requires_dir))

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(REPO_ROOT),
            env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "noosphere")},
        )
        elapsed = time.monotonic() - start
        return {
            "name": check["name"],
            "status": "pass" if result.returncode == 0 else "fail",
            "exit_code": result.returncode,
            "duration_s": round(elapsed, 2),
            "output": (result.stdout + result.stderr).strip(),
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return {
            "name": check["name"],
            "status": "timeout",
            "exit_code": None,
            "duration_s": round(elapsed, 2),
            "output": f"Timed out after {timeout}s",
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "name": check["name"],
            "status": "error",
            "exit_code": None,
            "duration_s": round(elapsed, 2),
            "output": str(e),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all round-3 CI invariant checks")
    parser.add_argument("--json", action="store_true", help="Output JSON summary")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter path")
    parser.add_argument("--timeout", type=int, default=120, help="Per-check timeout in seconds")
    parser.add_argument(
        "--check",
        action="append",
        dest="only_checks",
        help="Run only named check(s); can repeat",
    )
    args = parser.parse_args()

    checks = CHECKS
    if args.only_checks:
        names = set(args.only_checks)
        checks = [c for c in CHECKS if c["name"] in names]
        if not checks:
            print(f"No checks matched: {args.only_checks}", file=sys.stderr)
            return 2

    results: list[dict] = []
    for check in checks:
        r = _run_check(check, args.python, args.timeout)
        results.append(r)

    passed = sum(1 for r in results if r["status"] == "pass")
    skipped = sum(1 for r in results if r["status"] == "skip")
    failed = sum(1 for r in results if r["status"] not in ("pass", "skip"))
    total = len(results)

    if args.json:
        summary = {
            "total": total,
            "passed": passed,
            "skipped": skipped,
            "failed": failed,
            "ok": failed == 0,
            "checks": results,
        }
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n{'='*60}")
        print("Round-3 Invariant Check Summary")
        print(f"{'='*60}")
        for r in results:
            icon = {"pass": "+", "skip": "~", "fail": "X", "timeout": "!", "error": "!"}
            status_char = icon.get(r["status"], "?")
            print(f"  [{status_char}] {r['name']:<30s} {r['status']:<8s} ({r['duration_s']:.1f}s)")
            if r["status"] not in ("pass", "skip"):
                for line in r["output"].splitlines()[:5]:
                    print(f"      {line}")
        print(f"{'='*60}")
        print(f"  Total: {total}  Passed: {passed}  Skipped: {skipped}  Failed: {failed}")
        if failed == 0:
            print("  Result: ALL CHECKS PASSED")
        else:
            print("  Result: CHECKS FAILED")
        print(f"{'='*60}\n")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
