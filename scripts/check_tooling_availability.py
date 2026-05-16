#!/usr/bin/env python3
"""Tooling-availability pre-flight check.

Probes each tool we depend on by running its ``--version`` and
classifies the result as FOUND / MISSING / TOO_OLD. Critical tools
fail the check; optional tools are reported as warnings with a note
about which prompts or scripts are affected.

Output is a markdown table written to
``docs/verification/tooling/<UTC-timestamp>.md`` AND echoed to
stdout. Exit 0 on clean (or warnings-only), non-zero if any critical
tool is MISSING / TOO_OLD — unless ``--warnings-only`` is given, in
which case the script always exits 0 (this is the mode CI uses on
macOS-specific tools like pdflatex; the operator gets the report).

Designed to be quick — each probe has a hard timeout of 5 seconds.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = REPO_ROOT / "docs" / "verification" / "tooling"


@dataclasses.dataclass
class ToolSpec:
    name: str
    command: list[str]
    critical: bool
    min_version: str | None
    notes: str

    def display(self) -> str:
        return self.name


# Minimum versions are advisory — many tools have several supported
# majors. Bump these only when an explicit incompatibility is hit.
TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="python3",
        command=["python3", "--version"],
        critical=True,
        min_version="3.11",
        notes="Canonical interpreter; .venv-currents preferred but not required.",
    ),
    ToolSpec(
        name="pip",
        command=["python3", "-m", "pip", "--version"],
        critical=True,
        min_version=None,
        notes="pip is invoked via `python -m pip` in every workflow.",
    ),
    ToolSpec(
        name="node",
        command=["node", "--version"],
        critical=True,
        min_version="20.0.0",
        notes="theseus-codex (Next.js 16 / React 19) requires Node 20+.",
    ),
    ToolSpec(
        name="npm",
        command=["npm", "--version"],
        critical=True,
        min_version="10.0.0",
        notes="theseus-codex install / build entrypoint.",
    ),
    ToolSpec(
        name="npx",
        command=["npx", "--version"],
        critical=True,
        min_version=None,
        notes="Invokes prisma, vitest, playwright from theseus-codex/.",
    ),
    ToolSpec(
        name="prisma",
        command=["npx", "--no-install", "prisma", "--version"],
        critical=True,
        min_version=None,
        notes="theseus-codex Prisma client + migrations. Run from theseus-codex/.",
    ),
    ToolSpec(
        name="alembic",
        command=["python3", "-m", "alembic", "--version"],
        critical=True,
        min_version=None,
        notes="noosphere/alembic migrations. Optional if you never touch noosphere.",
    ),
    ToolSpec(
        name="git",
        command=["git", "--version"],
        critical=True,
        min_version="2.30.0",
        notes="Required for every workflow.",
    ),
    ToolSpec(
        name="pdflatex",
        command=["pdflatex", "-version"],
        critical=False,
        min_version=None,
        notes=(
            "Required to build coding_prompts 11, 17, 67 and the PDF "
            "memos. Install via MacTeX (mac) or texlive-full (linux)."
        ),
    ),
    ToolSpec(
        name="gh",
        command=["gh", "--version"],
        critical=False,
        min_version="2.40.0",
        notes="GitHub CLI — required by the live-trading rotation flow.",
    ),
    ToolSpec(
        name="vercel",
        command=["vercel", "--version"],
        critical=False,
        min_version=None,
        notes="Vercel CLI — required by docs/Vercel_Supabase_Deploy.md flows.",
    ),
    ToolSpec(
        name="docker",
        command=["docker", "--version"],
        critical=False,
        min_version=None,
        notes="Required by docker-compose-based dev environments.",
    ),
]


@dataclasses.dataclass
class ProbeResult:
    tool: ToolSpec
    status: str  # FOUND, MISSING, TOO_OLD, ERROR
    version: str | None
    detail: str


_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def _parse_version(text: str) -> str | None:
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def _cmp_version(a: str, b: str) -> int:
    """Compare dotted versions. Returns -1, 0, 1."""
    pa = [int(x) for x in a.split(".")]
    pb = [int(x) for x in b.split(".")]
    # Pad to equal length.
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def _probe(tool: ToolSpec, timeout: float = 5.0) -> ProbeResult:
    # Quick existence check first for the head binary.
    head = tool.command[0]
    if head not in {"python3", "npx"} and shutil.which(head) is None:
        return ProbeResult(tool, "MISSING", None, f"{head} not on PATH")
    try:
        proc = subprocess.run(
            tool.command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return ProbeResult(tool, "MISSING", None, f"{head} not found")
    except subprocess.TimeoutExpired:
        return ProbeResult(
            tool, "ERROR", None, f"`{' '.join(tool.command)}` timed out"
        )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    version = _parse_version(out)
    if proc.returncode != 0 and version is None:
        first_line = (out.strip().splitlines() or [""])[0]
        return ProbeResult(tool, "MISSING", None, f"exit={proc.returncode}: {first_line[:160]}")
    if tool.min_version and version and _cmp_version(version, tool.min_version) < 0:
        return ProbeResult(
            tool,
            "TOO_OLD",
            version,
            f"{version} < required {tool.min_version}",
        )
    return ProbeResult(tool, "FOUND", version, "")


def probe_all(specs: list[ToolSpec] = TOOLS) -> list[ProbeResult]:
    return [_probe(t) for t in specs]


def _render_markdown(results: list[ProbeResult]) -> str:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    lines = [
        "# Tooling availability report",
        "",
        f"_Generated: {now}_",
        "",
        "| Tool | Critical | Status | Version | Notes |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        crit = "yes" if r.tool.critical else "no"
        ver = r.version or "—"
        detail = r.detail or r.tool.notes
        # Escape pipes inside cells.
        detail = detail.replace("|", "\\|").splitlines()[0]
        lines.append(
            f"| `{r.tool.name}` | {crit} | **{r.status}** | `{ver}` | {detail} |"
        )
    lines.append("")
    lines.append("## Affected surfaces (optional tools)")
    lines.append("")
    for r in results:
        if r.tool.critical or r.status == "FOUND":
            continue
        lines.append(f"- `{r.tool.name}` ({r.status}): {r.tool.notes}")
    lines.append("")
    return "\n".join(lines)


def _summary(results: list[ProbeResult]) -> dict:
    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tools": [
            {
                "name": r.tool.name,
                "critical": r.tool.critical,
                "status": r.status,
                "version": r.version,
                "detail": r.detail,
            }
            for r in results
        ],
        "critical_missing": [
            r.tool.name
            for r in results
            if r.tool.critical and r.status in {"MISSING", "TOO_OLD", "ERROR"}
        ],
        "optional_missing": [
            r.tool.name
            for r in results
            if not r.tool.critical and r.status in {"MISSING", "TOO_OLD", "ERROR"}
        ],
    }


def write_report(
    results: list[ProbeResult],
    report_dir: pathlib.Path = DEFAULT_REPORT_DIR,
) -> pathlib.Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = report_dir / f"{ts}.md"
    out_path.write_text(_render_markdown(results))
    return out_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory to write the timestamped markdown report.",
    )
    p.add_argument(
        "--warnings-only",
        action="store_true",
        help=(
            "Always exit 0 — useful in CI where missing optional tools "
            "should not fail the run. Pre-commit uses default gating."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Also emit the machine-readable summary to stdout (JSON).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Skip writing the timestamped report file.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the markdown table on stdout.",
    )
    args = p.parse_args(argv)
    results = probe_all()
    md = _render_markdown(results)
    if not args.quiet:
        print(md)
    if not args.no_write:
        path = write_report(results, pathlib.Path(args.report_dir))
        if not args.quiet:
            print(f"\nReport written to: {path}")
    summary = _summary(results)
    if args.json:
        print(json.dumps(summary, indent=2))
    if args.warnings_only:
        return 0
    return 1 if summary["critical_missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
