#!/usr/bin/env python3
"""CI workflow integrity check.

Walks every ``.github/workflows/*.yml`` and asserts:

* The file parses as YAML.
* Every ``uses:`` reference is either:
    - a local workflow (``./.github/workflows/foo.yml``) that exists,
      or
    - a third-party action whose ``owner/repo`` is listed in
      ``.github/action_pins.yml`` with the cited ref on the
      ``allowed_refs`` list.
* Every ``run:`` line that names a script under ``scripts/`` points
  at a file that exists. Executable bit is required for ``.sh`` and
  ``.py`` invoked via the bare path.
* Every ``run:`` line that names a path under ``tests/`` (e.g.,
  ``pytest tests/safety``) points at an existing target.
* Every ``needs:`` reference inside a job points at a job defined
  in the same workflow.
* Matrix dimensions, if present, are bounded (no ``*`` includes
  that would expand to an unbounded set).

Output is a structured report on stdout (plain text, one section
per workflow). Exit 0 on clean, non-zero on any drift.

Designed for sub-second-per-workflow execution; no network, no
process spawns.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import re
import sys
from typing import Iterable

try:
    import yaml  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover - dep missing message
    print(f"check_ci_workflow_integrity: pyyaml required ({exc})", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
PINS_FILE = REPO_ROOT / ".github" / "action_pins.yml"


@dataclasses.dataclass
class Finding:
    workflow: str
    severity: str  # "error" or "warning"
    code: str
    message: str

    def render(self) -> str:
        return f"  [{self.severity.upper()}] {self.code}: {self.message}"


def _load_pins(pins_path: pathlib.Path) -> dict[str, set[str]]:
    """Return ``{ "owner/repo": {"v4", "abc123..."} }``."""
    if not pins_path.is_file():
        return {}
    data = yaml.safe_load(pins_path.read_text()) or {}
    out: dict[str, set[str]] = {}
    for entry in data.get("actions", []) or []:
        owner = (entry.get("owner") or "").strip()
        repo = (entry.get("repo") or "").strip()
        if not owner or not repo:
            continue
        refs = {str(r).strip() for r in (entry.get("allowed_refs") or [])}
        out[f"{owner}/{repo}"] = refs
    return out


def _iter_uses(node: object) -> Iterable[str]:
    """Yield every ``uses:`` string value found anywhere in the tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "uses" and isinstance(v, str):
                yield v
            else:
                yield from _iter_uses(v)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_uses(item)


def _iter_steps(node: object) -> Iterable[dict]:
    """Yield each step mapping (so we can read its working-directory)."""
    if isinstance(node, dict):
        # A step is a dict that lives under a `steps:` list. The
        # structure is jobs.<name>.steps[*]. We discover steps by
        # looking at any list under the key `steps`.
        steps = node.get("steps")
        if isinstance(steps, list):
            for s in steps:
                if isinstance(s, dict):
                    yield s
        for v in node.values():
            if isinstance(v, (dict, list)):
                yield from _iter_steps(v)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_steps(item)


def _step_working_dir(step: dict, job_defaults: str | None) -> str | None:
    wd = step.get("working-directory")
    if isinstance(wd, str):
        return wd
    return job_defaults


def _job_default_wd(job: dict) -> str | None:
    defaults = job.get("defaults") or {}
    if not isinstance(defaults, dict):
        return None
    run = defaults.get("run") or {}
    if not isinstance(run, dict):
        return None
    wd = run.get("working-directory")
    return wd if isinstance(wd, str) else None


def _validate_uses(
    workflow: pathlib.Path,
    data: dict,
    pins: dict[str, set[str]],
) -> list[Finding]:
    out: list[Finding] = []
    name = workflow.name
    for ref in _iter_uses(data):
        # Local reusable workflow.
        if ref.startswith("./"):
            target = REPO_ROOT / ref[2:]
            if not target.is_file():
                out.append(
                    Finding(
                        name,
                        "error",
                        "USES_LOCAL_MISSING",
                        f"local workflow {ref!r} does not exist at {target}",
                    )
                )
            continue
        # Third-party action: owner/repo[/path]@ref.
        if "@" not in ref:
            out.append(
                Finding(
                    name,
                    "error",
                    "USES_UNVERSIONED",
                    f"uses: {ref!r} is missing an @version; pin in action_pins.yml",
                )
            )
            continue
        action_part, _, version = ref.partition("@")
        owner_repo = "/".join(action_part.split("/")[:2])
        if owner_repo not in pins:
            out.append(
                Finding(
                    name,
                    "error",
                    "USES_NOT_PINNED",
                    f"{owner_repo!r} not listed in .github/action_pins.yml",
                )
            )
            continue
        if version not in pins[owner_repo]:
            out.append(
                Finding(
                    name,
                    "error",
                    "USES_REF_DRIFT",
                    f"{owner_repo}@{version} not in allowed_refs "
                    f"({sorted(pins[owner_repo])})",
                )
            )
    return out


_RUN_SCRIPT_RE = re.compile(r"(?:^|\s|[`'\"&|;\(])(\./)?(scripts/[A-Za-z0-9_./\-]+)")
_RUN_TESTS_RE = re.compile(r"(?:^|\s|[`'\"&|;\(])(tests/[A-Za-z0-9_./\-]+)")


def _resolve_under(working_dir: str | None, ref: str) -> pathlib.Path:
    if working_dir:
        return REPO_ROOT / working_dir / ref
    return REPO_ROOT / ref


def _validate_run_refs(workflow: pathlib.Path, data: dict) -> list[Finding]:
    out: list[Finding] = []
    name = workflow.name
    jobs = data.get("jobs") or {}
    if not isinstance(jobs, dict):
        return out
    for _job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        job_wd = _job_default_wd(job)
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if not isinstance(run, str):
                continue
            wd = _step_working_dir(step, job_wd)
            # scripts/...
            for match in _RUN_SCRIPT_RE.finditer(run):
                ref = match.group(2).rstrip(".,;:)\"'`")
                # Try (a) relative to working_dir, (b) repo root.
                target_a = _resolve_under(wd, ref)
                target_b = REPO_ROOT / ref
                target = (
                    target_a
                    if target_a.exists()
                    else (target_b if target_b.exists() else target_a)
                )
                if not target.exists():
                    out.append(
                        Finding(
                            name,
                            "error",
                            "RUN_SCRIPT_MISSING",
                            f"run: references missing path {ref!r}"
                            + (f" (working-directory: {wd})" if wd else ""),
                        )
                    )
                    continue
                if target.suffix in {".sh", ".py"} and target.is_file():
                    if not os.access(target, os.X_OK):
                        out.append(
                            Finding(
                                name,
                                "warning",
                                "RUN_SCRIPT_NOT_EXECUTABLE",
                                f"{ref} is not executable (chmod +x recommended)",
                            )
                        )
            # tests/...
            for match in _RUN_TESTS_RE.finditer(run):
                ref = match.group(1).rstrip(".,;:)\"'`")
                # Skip lines whose ref is a glob — those won't resolve
                # at static time.
                if "*" in ref:
                    continue
                target_a = _resolve_under(wd, ref)
                target_b = REPO_ROOT / ref
                if not (target_a.exists() or target_b.exists()):
                    out.append(
                        Finding(
                            name,
                            "error",
                            "RUN_TEST_PATH_MISSING",
                            f"run: references missing test path {ref!r}"
                            + (f" (working-directory: {wd})" if wd else ""),
                        )
                    )
    return out


def _validate_needs(workflow: pathlib.Path, data: dict) -> list[Finding]:
    out: list[Finding] = []
    name = workflow.name
    jobs = data.get("jobs") or {}
    if not isinstance(jobs, dict):
        return out
    job_names = set(jobs.keys())
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        needs = job.get("needs")
        if needs is None:
            continue
        if isinstance(needs, str):
            needs_list = [needs]
        elif isinstance(needs, list):
            needs_list = [str(n) for n in needs]
        else:
            continue
        for dep in needs_list:
            if dep not in job_names:
                out.append(
                    Finding(
                        name,
                        "error",
                        "NEEDS_UNDEFINED",
                        f"job {job_name!r} needs {dep!r} which is not "
                        f"defined in this workflow",
                    )
                )
    return out


def _validate_matrix(workflow: pathlib.Path, data: dict) -> list[Finding]:
    out: list[Finding] = []
    name = workflow.name
    jobs = data.get("jobs") or {}
    if not isinstance(jobs, dict):
        return out
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        strategy = job.get("strategy")
        if not isinstance(strategy, dict):
            continue
        matrix = strategy.get("matrix")
        if not isinstance(matrix, dict):
            continue
        size = 1
        for dim_name, dim_val in matrix.items():
            if dim_name in {"include", "exclude"}:
                continue
            if isinstance(dim_val, list):
                size *= max(1, len(dim_val))
        if size > 50:
            out.append(
                Finding(
                    name,
                    "error",
                    "MATRIX_UNBOUNDED",
                    f"job {job_name!r} matrix expands to {size} combinations "
                    "(cap is 50)",
                )
            )
    return out


def _validate_workflow(
    workflow: pathlib.Path, pins: dict[str, set[str]]
) -> list[Finding]:
    name = workflow.name
    try:
        text = workflow.read_text()
    except OSError as exc:
        return [Finding(name, "error", "READ_FAILED", str(exc))]
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [Finding(name, "error", "YAML_PARSE", str(exc).splitlines()[0])]
    if not isinstance(data, dict):
        return [
            Finding(
                name,
                "error",
                "YAML_SHAPE",
                "top-level is not a mapping",
            )
        ]
    findings: list[Finding] = []
    findings += _validate_uses(workflow, data, pins)
    findings += _validate_run_refs(workflow, data)
    findings += _validate_needs(workflow, data)
    findings += _validate_matrix(workflow, data)
    return findings


def check(
    workflows_dir: pathlib.Path = WORKFLOWS_DIR,
    pins_path: pathlib.Path = PINS_FILE,
    only: list[pathlib.Path] | None = None,
) -> tuple[int, list[Finding]]:
    """Returns (exit_code, findings)."""
    pins = _load_pins(pins_path)
    if not pins:
        return (
            2,
            [
                Finding(
                    "<pins>",
                    "error",
                    "PINS_MISSING",
                    f"action pin file is empty or missing at {pins_path}",
                )
            ],
        )
    workflows = sorted(only) if only else sorted(workflows_dir.glob("*.yml"))
    all_findings: list[Finding] = []
    for wf in workflows:
        all_findings.extend(_validate_workflow(wf, pins))
    errors = [f for f in all_findings if f.severity == "error"]
    return (1 if errors else 0, all_findings)


def _print_report(findings: list[Finding]) -> None:
    by_workflow: dict[str, list[Finding]] = {}
    for f in findings:
        by_workflow.setdefault(f.workflow, []).append(f)
    if not findings:
        print("CI workflow integrity: OK (no findings).")
        return
    for wf in sorted(by_workflow):
        print(f"\n=== {wf} ===")
        for f in by_workflow[wf]:
            print(f.render())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--workflow",
        action="append",
        default=None,
        help="Only check the given workflow file (repeatable).",
    )
    p.add_argument(
        "--workflows-dir",
        default=str(WORKFLOWS_DIR),
        help="Directory holding workflow YAML files.",
    )
    p.add_argument(
        "--pins-file",
        default=str(PINS_FILE),
        help="Path to action_pins.yml.",
    )
    p.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "Print the report but always exit 0. Used by the PR-comment "
            "step so a comment is posted even when findings exist."
        ),
    )
    p.add_argument(
        "--severity-gate",
        choices=["any", "error", "yaml-only"],
        default="error",
        help=(
            "What severity should turn into a non-zero exit. "
            "'yaml-only' fails only on YAML parse errors (used in PR "
            "advisory mode); 'error' is the default; 'any' includes "
            "warnings."
        ),
    )
    args = p.parse_args(argv)
    only = [pathlib.Path(w) for w in args.workflow] if args.workflow else None
    rc, findings = check(
        workflows_dir=pathlib.Path(args.workflows_dir),
        pins_path=pathlib.Path(args.pins_file),
        only=only,
    )
    _print_report(findings)
    if args.report_only:
        return 0
    if args.severity_gate == "yaml-only":
        bad = [
            f
            for f in findings
            if f.code in {"YAML_PARSE", "YAML_SHAPE", "READ_FAILED", "PINS_MISSING"}
        ]
        return 1 if bad else 0
    if args.severity_gate == "any":
        return 1 if findings else 0
    return rc


if __name__ == "__main__":
    sys.exit(main())
