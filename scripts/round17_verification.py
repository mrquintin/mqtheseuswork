#!/usr/bin/env python3
"""round17_verification.py

Re-runs the round-17 verification pass. Captures:

  A) noosphere / theseus-codex / dialectic test suites
  B) every scripts/check_*.py invariant
  C) coding_prompts/_audit_implementation.py
  D) the public-surface smoke probes (read-only — looks at source files for
     hero phrases; the live HTTP smoke is run separately via scripts/round17_smoke.sh)
  E) cross-prompt coupling (does the artifact a later prompt depends on exist?)

It writes a fresh report to docs/runs/round17_verification_<timestamp>.md.
The original run lives at docs/runs/round17_verification.md.

This script never edits production code. It is read-only.
"""
from __future__ import annotations

import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TC = REPO / "theseus-codex"
NOOSPHERE = REPO / "noosphere"
DIALECTIC = REPO / "dialectic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: Path, *, env_extra: dict | None = None,
        timeout: int = 600) -> tuple[int, str]:
    """Run `cmd`, return (exit_code, combined_output). Never raises."""
    import os
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, text=True,
        )
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired as exc:
        return 124, (exc.stdout or "") + f"\n[timed out after {timeout}s]"
    except FileNotFoundError as exc:
        return 127, f"[not found] {exc}"


def tail(text: str, n: int = 30) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


# ---------------------------------------------------------------------------
# A) test suites
# ---------------------------------------------------------------------------

def section_test_suites() -> str:
    out = ["## A. Test suites", ""]

    rc, log = run(
        ["python", "-m", "pytest", "-x", "-q"],
        cwd=NOOSPHERE,
    )
    out.append(f"### noosphere (`pytest -x -q`)  exit={rc}")
    out.append("```")
    out.append(tail(log, 25))
    out.append("```")
    out.append("")

    rc, log = run(
        ["npm", "test", "--", "--run"],
        cwd=TC, timeout=900,
    )
    out.append(f"### theseus-codex (`npm test -- --run`)  exit={rc}")
    out.append("```")
    out.append(tail(log, 30))
    out.append("```")
    out.append("")

    rc, log = run(
        ["python", "-m", "pytest", "-x", "-q"],
        cwd=DIALECTIC,
    )
    out.append(f"### dialectic (`pytest -x -q`)  exit={rc}")
    out.append("```")
    out.append(tail(log, 20))
    out.append("```")
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# B) check_*.py invariants
# ---------------------------------------------------------------------------

def section_invariants() -> str:
    out = ["## B. CI invariant gates (`scripts/check_*.py`)", ""]
    checks = sorted((REPO / "scripts").glob("check_*.py"))
    env_extra = {"PYTHONPATH": str(NOOSPHERE)}
    for script in checks:
        # check_packaging_selfcontainment.py needs an arg; round3 invariants
        # is itself an aggregator that calls the others.
        if script.name == "check_packaging_selfcontainment.py":
            out.append(f"- **{script.name}**: SKIP (requires `package_dir` arg)")
            continue
        rc, log = run(["python3", str(script)], cwd=REPO, env_extra=env_extra)
        last = log.strip().splitlines()
        last_line = last[-1] if last else ""
        marker = "ok" if rc == 0 else f"FAIL exit={rc}"
        out.append(f"- **{script.name}** — {marker}  `{last_line[:140]}`")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# C) prompt audit
# ---------------------------------------------------------------------------

def section_audit() -> str:
    out = ["## C. Prompt audit (`coding_prompts/_audit_implementation.py`)", ""]
    rc, log = run(
        ["python3", "coding_prompts/_audit_implementation.py"],
        cwd=REPO,
    )
    # Extract just the ACTIVE block — that's the round-17 verdict.
    active_section = []
    in_active = False
    for line in log.splitlines():
        if line.startswith("=== ACTIVE TOP-LEVEL"):
            in_active = True
        elif in_active and line.startswith("=== "):
            break
        if in_active:
            active_section.append(line)
    out.append(f"audit exit={rc}")
    out.append("")
    out.append("```")
    out.append("\n".join(active_section))
    out.append("```")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# D) public-surface smoke (file-level)
# ---------------------------------------------------------------------------

PUBLIC_SURFACES = [
    ("/calibration",            "calibration/page.tsx",            "Calibration scorecard"),
    ("/methodology/criteria",   "methodology/criteria/page.tsx",   "Five-criterion rubric"),
    ("/methodology/replicate",  "methodology/replicate/page.tsx",  "Replicate the firm"),
    ("/methodology/redteam",    "methodology/redteam/page.tsx",    "Red-team tournament"),
    ("/ask",                    "ask/page.tsx",                    "Ask the firm"),
    ("/critiques",              "critiques/page.tsx",              "Critique hall of fame"),
    ("/privacy",                "privacy/page.tsx",                "Privacy & Data Retention"),
    ("/research/seasonal",      "research/seasonal/page.tsx",      "Quarterly research reviews"),
]


def section_public_surfaces() -> str:
    out = ["## D. Public-surface check (file-level)", ""]
    out.append("Confirms the hero phrase is present in each new public route. The")
    out.append("live HTTP smoke (200 + hero) is `scripts/round17_smoke.sh`, run")
    out.append("separately against a dev server.")
    out.append("")
    base = TC / "src" / "app"
    for route, rel, hero in PUBLIC_SURFACES:
        p = base / rel
        if not p.exists():
            out.append(f"- {route} — **MISSING file** at `{p.relative_to(REPO)}`")
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        present = hero in body
        out.append(
            f"- {route} — {'ok' if present else 'MISSING HERO'}  "
            f"`{p.relative_to(REPO)}`  hero=`{hero}`"
        )
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# E) cross-prompt coupling
# ---------------------------------------------------------------------------

# Pair (dependent → dependency). The artifact in the second slot must exist
# for the dependent prompt's work to be coherent. These mirror the explicit
# dependency claims in the prompt headers.
COUPLINGS = [
    # 02 → 01: linkage references MQS scorer
    ("02 → 01", "noosphere/noosphere/evaluation/mqs.py"),
    # 03 → 02: failure-mode catalog reads outcome linkage
    ("03 → 02", "noosphere/noosphere/evaluation/method_outcome_linker.py"),
    # 04 → 02: drift detector reads track-record stream
    ("04 → 02", "noosphere/noosphere/evaluation/method_track_record.py"),
    # 05 → 02: composition graph reads track record
    ("05 → 02", "noosphere/noosphere/evaluation/method_track_record.py"),
    # 06 → 02: domain bounds derived from track record
    ("06 → 02", "noosphere/noosphere/evaluation/method_track_record.py"),
    # 07 → 01..06: public methodology explorer surfaces all of these
    ("07 → 01", "noosphere/noosphere/evaluation/mqs.py"),
    # 14 → 12: calibration-aware confidence reads public scorecard
    ("14 → 12", "noosphere/noosphere/evaluation/public_calibration.py"),
    # 18 → 19: retraction propagation reads credibility
    ("18 → 19", "noosphere/noosphere/literature/source_credibility.py"),
    # 20 → 19: chain validator reads credibility
    ("20 → 19", "noosphere/noosphere/literature/source_credibility.py"),
    # 22 → 21: severity weighting consumes swarm output
    ("22 → 21", "noosphere/noosphere/peer_review/swarm.py"),
    # 23 → 22: tournament aggregates severity-weighted objections
    ("23 → 22", "noosphere/noosphere/peer_review/severity.py"),
    # 24 → geometry primitives
    ("24",     "noosphere/noosphere/peer_review/geometric_blindspot.py"),
    # 32 → 31: speaker models attach to triage dialog
    ("32 → 31", "noosphere/noosphere/literature/response_triage.py"),
    # 33 → 32: argument map renders dialog turns
    ("33 → 32", "noosphere/noosphere/literature/response_triage.py"),
    # 41 currents market link
    ("41",     "theseus-codex/src/app/currents/page.tsx"),
    # 42 → 01: methodology diff uses MQS
    ("42 → 01", "noosphere/noosphere/evaluation/mqs.py"),
    # 47 → 12: seasonal review pulls calibration data
    ("47 → 12", "noosphere/noosphere/evaluation/public_calibration.py"),
    # 49 → 46: security/privacy hardening rides on retention
    ("49 → 46", "noosphere/noosphere/decay/retention_policies.py"),
]


def section_coupling() -> str:
    out = ["## E. Cross-prompt coupling", ""]
    out.append("For each dependent prompt, confirm the dependency artifact is on disk.")
    out.append("")
    for prompt_num, dep in COUPLINGS:
        ok = (REPO / dep).exists()
        out.append(f"- **{prompt_num}** ← `{dep}` — {'ok' if ok else 'MISSING'}")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPO / "docs" / "runs" / f"round17_verification_{timestamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    chunks = [
        f"# Round-17 verification — {timestamp}",
        "",
        "Re-run of `scripts/round17_verification.py`. The first authoritative run",
        "is at `docs/runs/round17_verification.md`.",
        "",
        section_test_suites(),
        section_invariants(),
        section_audit(),
        section_public_surfaces(),
        section_coupling(),
    ]
    out_path.write_text("\n".join(chunks), encoding="utf-8")
    print(f"wrote {out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
