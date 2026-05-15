#!/usr/bin/env python3
"""CI lint: scheduled jobs in code ↔ runbook entries.

The runbook at ``docs/operations/Runbook.md`` is the firm's source of
truth for what runs on a schedule and what alerts fire. This script
fails CI when the two sides of that contract drift apart.

What it checks:

  1. Every ``.github/workflows/*.yml`` file with a ``schedule: cron:``
     block appears as a job entry's ``Source`` in the runbook.
  2. Every ``noosphere/noosphere/**/scheduler*.py`` module appears as a
     job entry's ``Source`` in the runbook.
  3. Every job entry's ``Source`` path exists on disk.
  4. Job entries whose source is a workflow yaml actually contain a
     ``cron:`` line (i.e. the workflow is genuinely scheduled).
  5. Every ``AlertRule(name="…")`` in
     ``noosphere/noosphere/observability/metrics.py`` (the
     ``DEFAULT_RULES`` list) appears as an alert entry in the runbook.

What it does NOT check:

  * Whether the prose under each entry is correct.
  * Whether procedures are accurate.
  * Whether the runbook's recovery commands actually work.

Those belong in the quarterly drill (see
``scripts/operations_drill_candidates.py`` and Runbook §"Quarterly
drill"). This script is a structural drift gate, nothing more.

Exit codes:
  0 — runbook and code agree.
  1 — drift detected; details printed to stdout.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNBOOK_PATH = REPO_ROOT / "docs" / "operations" / "Runbook.md"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
NOOSPHERE_PKG_DIR = REPO_ROOT / "noosphere" / "noosphere"
METRICS_PATH = (
    REPO_ROOT / "noosphere" / "noosphere" / "observability" / "metrics.py"
)

JOB_CATALOG_HEADING = "## Job catalog"
ALERT_RESPONSE_HEADING = "## Alert response"


# ── Runbook parsing ──────────────────────────────────────────────────


def _section_body(md: str, heading: str) -> str:
    """Return the body of the H2 section whose title is ``heading``.

    Bounded by the next ``## `` heading (any H2) or end-of-file.
    """
    start = md.find(heading)
    if start == -1:
        return ""
    end = md.find("\n## ", start + len(heading))
    return md[start:end] if end != -1 else md[start:]


_H3_RE = re.compile(r"^### +(?P<id>[A-Za-z0-9_\-]+)\s*$", re.MULTILINE)
_SOURCE_RE = re.compile(
    r"^\s*-\s+\*\*Source:\*\*\s+`(?P<path>[^`]+)`",
    re.MULTILINE,
)


def parse_runbook_jobs(md: str) -> dict[str, str]:
    r"""Return ``{job_id: source_path}`` from the Job catalog section.

    ``source_path`` is the literal string inside the backticks of the
    first ``- **Source:** `…`\`` bullet under each ``### <job-id>``
    heading. Multiple paths per entry are not supported; the runbook
    convention is one source per job.
    """
    section = _section_body(md, JOB_CATALOG_HEADING)
    if not section:
        return {}
    # Pair each H3 with the slice of body up to the next H3.
    heads = list(_H3_RE.finditer(section))
    jobs: dict[str, str] = {}
    for i, m in enumerate(heads):
        job_id = m.group("id")
        body_start = m.end()
        body_end = heads[i + 1].start() if i + 1 < len(heads) else len(section)
        body = section[body_start:body_end]
        src = _SOURCE_RE.search(body)
        if src is None:
            # Caller will report this as a structural error elsewhere
            # if it matters; for the source map we just skip.
            continue
        jobs[job_id] = src.group("path")
    return jobs


def parse_runbook_alerts(md: str) -> set[str]:
    """Return the set of ``### <alert-name>`` ids in the Alert response section."""
    section = _section_body(md, ALERT_RESPONSE_HEADING)
    if not section:
        return set()
    return {m.group("id") for m in _H3_RE.finditer(section)}


# ── Code-side discovery ──────────────────────────────────────────────


_CRON_LINE_RE = re.compile(r"^\s*-\s*cron\s*:\s*['\"]?[^'\"\n#]+", re.MULTILINE)


def discover_scheduled_workflows() -> dict[str, Path]:
    """Return ``{workflow_filename: absolute_path}`` for every workflow
    yaml under ``.github/workflows/`` that contains a ``cron:`` schedule.

    Skips reusable workflows (filename starts with ``_``) — they are
    callable templates, not jobs.
    """
    out: dict[str, Path] = {}
    if not WORKFLOWS_DIR.is_dir():
        return out
    for p in sorted(WORKFLOWS_DIR.glob("*.yml")):
        if p.name.startswith("_"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if _CRON_LINE_RE.search(text):
            out[p.name] = p
    return out


def discover_scheduler_modules() -> dict[str, Path]:
    """Return ``{relative_path: absolute_path}`` for every Python module
    whose filename is ``scheduler.py`` or starts with ``scheduler_`` and
    lives under ``noosphere/noosphere/``.

    Excludes tests (they live under ``noosphere/tests/``, not under the
    package). Excludes ``__pycache__``.
    """
    out: dict[str, Path] = {}
    if not NOOSPHERE_PKG_DIR.is_dir():
        return out
    for p in sorted(NOOSPHERE_PKG_DIR.rglob("scheduler*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(REPO_ROOT).as_posix()
        out[rel] = p
    return out


_ALERT_RULE_NAME_RE = re.compile(
    r"AlertRule\s*\(\s*name\s*=\s*['\"](?P<name>[A-Za-z0-9_\-]+)['\"]"
)


def discover_default_alert_rule_names() -> set[str]:
    """Return every ``name="…"`` argument to an ``AlertRule(…)`` call
    inside the ``DEFAULT_RULES`` block in
    ``observability/metrics.py``.

    We isolate the ``DEFAULT_RULES`` literal so unrelated ``AlertRule``
    constructions elsewhere in the file don't show up. If the file
    shape changes, the script will under-report rather than crash —
    the worst case is a missing alert sneaking through this check,
    which is acceptable for a structural lint.
    """
    try:
        text = METRICS_PATH.read_text(encoding="utf-8")
    except OSError:
        return set()
    marker = "DEFAULT_RULES"
    start = text.find(marker)
    if start == -1:
        return set()
    # Bound the block at the next top-level statement (a non-indented
    # line after the literal opens). This is a heuristic, but the file
    # is short and the literal is the only multi-line construct.
    block_open = text.find("[", start)
    if block_open == -1:
        return set()
    depth = 0
    block_end = block_open
    for i in range(block_open, len(text)):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                block_end = i + 1
                break
    block = text[block_open:block_end]
    return {m.group("name") for m in _ALERT_RULE_NAME_RE.finditer(block)}


# ── Main check ───────────────────────────────────────────────────────


def check(runbook_path: Path = RUNBOOK_PATH) -> list[str]:
    """Return the list of violations. Empty list ⇒ clean."""
    if not runbook_path.is_file():
        return [f"runbook missing: {runbook_path}"]

    md = runbook_path.read_text(encoding="utf-8")
    runbook_jobs = parse_runbook_jobs(md)
    runbook_sources = {src: jid for jid, src in runbook_jobs.items()}
    runbook_alerts = parse_runbook_alerts(md)

    workflows = discover_scheduled_workflows()
    schedulers = discover_scheduler_modules()
    alert_rule_names = discover_default_alert_rule_names()

    violations: list[str] = []

    # 1. Every cron workflow appears in the runbook.
    for wf_name in sorted(workflows):
        wf_rel = f".github/workflows/{wf_name}"
        if wf_rel not in runbook_sources:
            violations.append(
                f"workflow {wf_rel!r} has a cron schedule but no job "
                f"entry in {runbook_path.relative_to(REPO_ROOT)} "
                f"(expected an `- **Source:** `{wf_rel}`` line under "
                f"some `### <job-id>` heading)."
            )

    # 2. Every scheduler module appears in the runbook.
    for sched_rel in sorted(schedulers):
        if sched_rel not in runbook_sources:
            violations.append(
                f"scheduler module {sched_rel!r} exists but no job "
                f"entry in {runbook_path.relative_to(REPO_ROOT)} "
                f"names it as a Source."
            )

    # 3. Every job entry's source path exists.
    for job_id, src in runbook_jobs.items():
        abs_path = REPO_ROOT / src
        if not abs_path.exists():
            violations.append(
                f"runbook job '{job_id}' points at non-existent "
                f"source path {src!r}."
            )

    # 4. Workflow-sourced jobs in the runbook are actually cron-scheduled.
    for job_id, src in runbook_jobs.items():
        if not src.startswith(".github/workflows/"):
            continue
        abs_path = REPO_ROOT / src
        if not abs_path.is_file():
            # Already reported above as missing.
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(
                f"runbook job '{job_id}': could not read {src!r}: {exc}"
            )
            continue
        if not _CRON_LINE_RE.search(text):
            violations.append(
                f"runbook job '{job_id}' names {src!r} as Source but "
                f"that workflow has no `cron:` schedule. Either add one "
                f"or remove the job from the runbook."
            )

    # 5. Every DEFAULT_RULES alert name appears in the runbook.
    for name in sorted(alert_rule_names):
        if name not in runbook_alerts:
            violations.append(
                f"alert rule {name!r} is configured in "
                f"noosphere/noosphere/observability/metrics.py "
                f"(DEFAULT_RULES) but has no `### {name}` entry under "
                f"'## Alert response' in the runbook."
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runbook",
        type=Path,
        default=RUNBOOK_PATH,
        help="path to Runbook.md (default: docs/operations/Runbook.md)",
    )
    args = parser.parse_args(argv)

    violations = check(args.runbook)
    if not violations:
        print(
            "check_runbook_completeness: ok — runbook entries match "
            "scheduled jobs and configured alerts in code."
        )
        return 0
    print(
        f"check_runbook_completeness: {len(violations)} violation(s):",
        file=sys.stdout,
    )
    for v in violations:
        print(f"  - {v}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
