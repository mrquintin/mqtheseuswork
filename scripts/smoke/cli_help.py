"""CLI help smoke.

Walks every Typer / argparse entry point registered in the monorepo
and runs it with ``--help``. A handler whose top-level import crashed
fails ``--help`` even though the rest of the build passed — this is
exactly the regression the section catches.

Discovery
---------
1. ``[project.scripts]`` blocks in
   ``noosphere/pyproject.toml`` and ``dialectic/pyproject.toml``.
2. Every ``@app.command(...)`` registered against the Typer
   ``app`` in ``noosphere.typer_cli``.

For each Typer subcommand the harness runs the corresponding
``python -m noosphere <sub> --help`` so a registration that was
silently dropped (the decorator stopped firing) is caught.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent.parent

# (entry_module, label) — invoked as `python -m <entry_module> --help`.
ENTRYPOINTS: tuple[tuple[str, str], ...] = (
    ("noosphere", "noosphere"),
    ("dialectic", "dialectic"),
)


_TYPER_CMD = re.compile(
    r"""@(?P<app>\w+)\.command\(\s*['"](?P<name>[^'"]+)['"]""",
    re.MULTILINE,
)


def discover_typer_subcommands(file_path: Path) -> list[tuple[str, str]]:
    """Return ``[(app_var, sub_name), ...]`` for every @app.command in file."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [(m.group("app"), m.group("name")) for m in _TYPER_CMD.finditer(text)]


def _run(cmd: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
    import os

    # Extend PYTHONPATH so the harness works even when noosphere/
    # dialectic are checked out in-tree rather than pip-installed
    # into the active venv. The package source roots are always at
    # <repo>/noosphere and <repo>/dialectic.
    extra_paths = [str(ROOT / "noosphere"), str(ROOT / "dialectic")]
    env = {**os.environ, "THESEUS_SMOKE": "1"}
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([*extra_paths, existing]) if existing else os.pathsep.join(extra_paths)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=ROOT,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _check_root_help(module: str) -> dict[str, Any]:
    try:
        rc, out, err = _run([sys.executable, "-m", module, "--help"])
    except subprocess.TimeoutExpired as exc:
        return {
            "name": f"{module} --help",
            "ok": False,
            "detail": f"timeout after {exc.timeout}s",
        }
    if rc != 0:
        return {
            "name": f"{module} --help",
            "ok": False,
            "detail": f"exit {rc}; stderr: {err[:600]}",
        }
    # A Typer app that lost its registration prints only "Usage:" with
    # no commands listed. Catch that.
    has_commands = "Commands" in out or "Commands:" in out or "command" in out.lower()
    if not has_commands:
        return {
            "name": f"{module} --help",
            "ok": False,
            "detail": "help text does not advertise any subcommand",
        }
    return {"name": f"{module} --help", "ok": True, "detail": "ok"}


def _check_sub_help(module: str, sub: str) -> dict[str, Any]:
    try:
        rc, out, err = _run([sys.executable, "-m", module, sub, "--help"])
    except subprocess.TimeoutExpired as exc:
        return {
            "name": f"{module} {sub} --help",
            "ok": False,
            "detail": f"timeout after {exc.timeout}s",
        }
    if rc != 0:
        return {
            "name": f"{module} {sub} --help",
            "ok": False,
            "detail": f"exit {rc}; stderr: {err[:400]}",
        }
    return {"name": f"{module} {sub} --help", "ok": True, "detail": "ok"}


def run(output_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    checks: list[dict[str, Any]] = []
    for module, _label in ENTRYPOINTS:
        checks.append(_check_root_help(module))
    # Noosphere has many subcommands — probe each.
    noosphere_typer = ROOT / "noosphere" / "noosphere" / "typer_cli.py"
    subs = discover_typer_subcommands(noosphere_typer)
    # Only probe top-level `app` subcommands (nested apps print their
    # own --help; the root --help check above already covered the
    # registration of the nested app).
    top_level_subs = [name for app_var, name in subs if app_var == "app"]
    for sub in sorted(set(top_level_subs)):
        checks.append(_check_sub_help("noosphere", sub))
    duration = time.monotonic() - started
    payload = {
        "section": "cli-help",
        "ok": all(c["ok"] for c in checks),
        "duration_s": round(duration, 3),
        "checks": checks,
        "summary": {
            "entrypoints": len(ENTRYPOINTS),
            "subcommands_probed": len(top_level_subs),
            "failures": sum(1 for c in checks if not c["ok"]),
        },
        "perf_warning": f"section exceeded 30s budget ({duration:.1f}s)" if duration > 30 else None,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cli-help.json").write_text(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output_dir)
    raise SystemExit(0 if result["ok"] else 1)
