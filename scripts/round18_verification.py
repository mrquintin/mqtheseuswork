#!/usr/bin/env python3
"""round18_verification.py

Re-runs the round-18 verification pass and writes a fresh report under
``docs/runs/round18_verification_<timestamp>/``.

Sections produced (mirroring round 17, plus the round-18 specific items):

  A) noosphere / theseus-codex / dialectic test suites + replication harness
     ``make smoke`` (the round-18 prompt asks for ``make light`` only "if the
     light path exists" — it does not, so we use ``make smoke``).
  B) every ``scripts/check_*.py`` invariant gate
  C) ``coding_prompts/_audit_implementation.py`` — per-prompt verdicts
  D) empirical artifact spot-check for prompts 13–20 (existence + non-empty
     + numbers vs template placeholders)
  E) cross-prompt coupling — every artifact a Round-17 archived prompt
     declared in its SCOPE block must still resolve on disk OR be covered
     by a compatibility shim that re-exports the original module path.

It never edits production code. It is read-only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TC = REPO / "theseus-codex"
NOOSPHERE = REPO / "noosphere"
DIALECTIC = REPO / "dialectic"
REPLICATION = REPO / "replication"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: Path, *, env_extra: dict | None = None,
        timeout: int = 600) -> tuple[int, str]:
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
    return "\n".join(text.splitlines()[-n:])


# ---------------------------------------------------------------------------
# A) test suites + replication harness
# ---------------------------------------------------------------------------

def section_test_suites(out_dir: Path) -> str:
    """Run the four suites and write a long-form log to test_output.md.

    Returns a markdown summary table for the REPORT."""
    log_path = out_dir / "test_output.md"
    summary_rows: list[tuple[str, str, int, str]] = []
    full_log_chunks: list[str] = ["# Round-18 verification — test suite output", ""]

    # Use `python3` because the system PATH on darwin doesn't always have a
    # `python` symlink; round-17 verification has a known exit=127 footnote
    # for the same reason. Falls back to `python` if `python3` is missing.
    py = "python3"
    targets = [
        ("noosphere", [py, "-m", "pytest", "-x", "-q"], NOOSPHERE, 600),
        ("theseus-codex", ["npm", "test", "--", "--run"], TC, 1200),
        ("dialectic", [py, "-m", "pytest", "-x", "-q"], DIALECTIC, 600),
    ]
    for name, cmd, cwd, timeout in targets:
        if not cwd.exists():
            summary_rows.append((name, " ".join(cmd), 1, "missing dir"))
            full_log_chunks.append(f"## {name} — directory missing ({cwd})\n")
            continue
        rc, log = run(cmd, cwd=cwd, timeout=timeout)
        verdict = "ok" if rc == 0 else f"FAIL exit={rc}"
        summary_rows.append((name, " ".join(cmd), rc, verdict))
        full_log_chunks.append(f"## {name} (`{' '.join(cmd)}`) — exit {rc}\n")
        full_log_chunks.append("```")
        full_log_chunks.append(log)
        full_log_chunks.append("```\n")

    # Replication harness — prompt asks for `make light` if it exists.
    # In the current Makefile only `smoke` exists; record both facts.
    rc = 0
    log = ""
    repl_status = "skipped — neither `light` nor `smoke` target found"
    if REPLICATION.exists():
        targets_avail = run(["make", "-C", str(REPLICATION), "-pn"], REPO, timeout=30)[1]
        if re.search(r"^light:", targets_avail, re.MULTILINE):
            rc, log = run(["make", "-C", str(REPLICATION), "light"], REPO, timeout=900)
            repl_status = f"`make -C replication light` — exit {rc}"
        elif re.search(r"^smoke:", targets_avail, re.MULTILINE):
            rc, log = run(["make", "-C", str(REPLICATION), "smoke"], REPO, timeout=900)
            repl_status = (
                f"`make -C replication light` (not present) → fell back to "
                f"`make smoke` — exit {rc}"
            )
    summary_rows.append(("replication", repl_status, rc, "ok" if rc == 0 else f"FAIL exit={rc}"))
    full_log_chunks.append(f"## replication — {repl_status}\n")
    full_log_chunks.append("```")
    full_log_chunks.append(log or "(no output)")
    full_log_chunks.append("```\n")

    log_path.write_text("\n".join(full_log_chunks), encoding="utf-8")

    # Build the REPORT summary section.
    out = ["## A. Test suites", ""]
    out.append("| Suite | Command | Exit | Verdict |")
    out.append("|---|---|---:|---|")
    for name, cmd, rc, verdict in summary_rows:
        out.append(f"| **{name}** | `{cmd}` | {rc} | {verdict} |")
    out.append("")
    out.append(f"Full output captured at `{log_path.relative_to(REPO)}`.")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# B) check_*.py invariants
# ---------------------------------------------------------------------------

ROUND18_NEW_CHECKS = {
    "check_schema_audit_consistency.py",
    "check_migration_linearity.py",
    "check_architecture_consistency.py",
    "check_rationale_structure.py",
    "check_mqs_doc_consistency.py",
    "check_no_inline_env_reads.py",
    "check_no_hardcoded_colors.py",
    "check_no_tracking_pixels.py",
    "check_no_secrets_in_code.py",
    "check_signing_key_not_in_web.py",
}


def section_invariants() -> str:
    out = ["## B. CI invariant gates (`scripts/check_*.py`)", ""]
    checks = sorted((REPO / "scripts").glob("check_*.py"))
    env_extra = {"PYTHONPATH": str(NOOSPHERE)}
    out.append("| Script | Round-18 new? | Result | Last line |")
    out.append("|---|:---:|---|---|")
    for script in checks:
        if script.name == "check_packaging_selfcontainment.py":
            out.append(f"| `{script.name}` |  | SKIP | requires `package_dir` arg |")
            continue
        rc, log = run(["python3", str(script)], cwd=REPO, env_extra=env_extra)
        last = log.strip().splitlines()
        last_line = (last[-1] if last else "").replace("|", r"\|")
        marker = "ok" if rc == 0 else f"FAIL exit={rc}"
        new_marker = "★" if script.name in ROUND18_NEW_CHECKS else ""
        out.append(f"| `{script.name}` | {new_marker} | {marker} | `{last_line[:140]}` |")
    out.append("")
    out.append("★ = explicitly listed as a round-18 invariant in the prompt.")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# C) prompt audit
# ---------------------------------------------------------------------------

def section_audit() -> str:
    out = ["## C. Prompt audit (`coding_prompts/_audit_implementation.py`)", ""]
    rc, log = run(
        ["python3", "coding_prompts/_audit_implementation.py"],
        cwd=REPO, timeout=120,
    )
    # Capture the ACTIVE block plus the action-plan summary.
    lines = log.splitlines()
    active_block: list[str] = []
    in_active = False
    for line in lines:
        if line.startswith("=== ACTIVE TOP-LEVEL"):
            in_active = True
        elif in_active and line.startswith("=== ") and not line.startswith("=== ACTIVE"):
            break
        if in_active:
            active_block.append(line)

    plan_block: list[str] = []
    in_plan = False
    for line in lines:
        if line.startswith("=== Action plan"):
            in_plan = True
        if in_plan:
            plan_block.append(line)

    out.append(f"audit exit={rc}")
    out.append("")
    out.append("### Active prompts (the round-18 batch)")
    out.append("")
    out.append("```")
    out.append("\n".join(active_block) or "(no ACTIVE section in audit output)")
    out.append("```")
    out.append("")
    out.append("### Action-plan summary")
    out.append("")
    out.append("```")
    out.append("\n".join(plan_block) or "(no Action plan section)")
    out.append("```")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# D) empirical artifact spot-check
# ---------------------------------------------------------------------------

# For each empirical execution prompt, list the canonical artifacts the
# prompt's SCOPE block declared. Glob-resolved (`<run-stamp>` etc.) — we
# accept any timestamp as long as a real file shows up.
EMPIRICAL_SPECS: list[tuple[str, str, list[str]]] = [
    ("13", "QH benchmark v1 first run", [
        "benchmarks/quintin_hypothesis/v1/results/*/results.json",
        "benchmarks/quintin_hypothesis/v1/results/*/envelope.json",
        "benchmarks/quintin_hypothesis/v1/results/*/analysis.md",
        "docs/research/QH_Benchmark_v1_Results.tex",
        "docs/research/QH_Benchmark_v1_Results.pdf",
        "noosphere/scripts/run_qh_full.sh",
        "noosphere/tests/test_qh_full_run_integration.py",
        "theseus-codex/src/app/methodology/benchmark/qh/page.tsx",
    ]),
    ("14", "Cross-model geometry study", [
        "benchmarks/quintin_hypothesis/v1/results/cross_model/*/results.parquet",
        "benchmarks/quintin_hypothesis/v1/results/cross_model/*/envelope.json",
        "benchmarks/quintin_hypothesis/v1/results/cross_model/*/analysis.md",
        "docs/research/Cross_Model_Geometry_Study.tex",
        "docs/research/Cross_Model_Geometry_Study.pdf",
        "docs/research/internal/Cross_Model_Findings_Memo.md",
        "theseus-codex/src/app/methodology/benchmark/qh/cross-model/page.tsx",
        "noosphere/scripts/run_cross_model_full.sh",
    ]),
    ("15", "Householder ablation", [
        "benchmarks/quintin_hypothesis/v1/results/ablations/*/results.json",
        "benchmarks/quintin_hypothesis/v1/results/ablations/*/envelope.json",
        "docs/research/Householder_Ablation.tex",
        "docs/research/Householder_Ablation.pdf",
        "docs/research/internal/Ablation_Decisions.md",
        "theseus-codex/src/app/methodology/contradiction_geometry/page.tsx",
    ]),
    ("16", "Red-team tournament v1", [
        "benchmarks/redteam/v1/results/*/results.json",
        "benchmarks/redteam/v1/results/*/envelope.json",
        "benchmarks/redteam/v1/results/*/leaderboard.csv",
        "docs/research/internal/Redteam_Tournament_*.md",
        "theseus-codex/src/app/methodology/redteam/page.tsx",
        "noosphere/scripts/run_redteam_tournament_v1.sh",
    ]),
    ("17", "Principle distillation pass", [
        "noosphere/scripts/run_principle_distillation.sh",
        "docs/research/internal/Principle_Distillation_*.md",
        "theseus-codex/src/app/(authed)/principles/queue/page.tsx",
        "noosphere/noosphere/distillation/principle_distillation.py",
        "noosphere/tests/test_principle_distillation_integration.py",
    ]),
    ("18", "Forecast resolution backfill", [
        "docs/runs/resolution_backfill_*_dryrun.md",
        "docs/runs/resolution_backfill_*.md",
        "noosphere/scripts/run_resolution_backfill.sh",
        "noosphere/tests/test_resolution_backfill_integration.py",
    ]),
    ("19", "Self-critique pass", [
        "noosphere/scripts/run_self_critique_pass.sh",
        "docs/runs/self_critique_*.md",
        "docs/runs/self_critique_*",  # the addenda directory
        "noosphere/tests/test_self_critique_integration.py",
    ]),
    ("20", "First auto paper", [
        "noosphere/scripts/run_first_auto_paper.sh",
        "docs/research/auto/*/paper.tex",
        "docs/research/auto/*/paper.pdf",
        "docs/research/internal/Auto_Paper_Candidates_*.md",
        "noosphere/tests/test_auto_paper_integration.py",
    ]),
]

# Patterns that suggest a file is still a template (not real numbers).
# `N/A` was previously here but it shows up legitimately in research analyses
# as "this baseline doesn't measure that metric" — too noisy to be a signal.
PLACEHOLDER_PATTERNS = [
    re.compile(r"\bTBD\b"),
    re.compile(r"<run-stamp>"),
    re.compile(r"<stamp>"),
    re.compile(r"<slug-\d+>"),
    re.compile(r"\bXX\.X+%?"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bPLACEHOLDER\b", re.IGNORECASE),
]
NUMBER_RE = re.compile(r"\d")


def _has_numbers(text: str) -> bool:
    return bool(NUMBER_RE.search(text))


def _has_placeholders(text: str) -> list[str]:
    hits = []
    for pat in PLACEHOLDER_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def _resolve(pattern: str) -> list[Path]:
    if any(ch in pattern for ch in "*?["):
        matches = sorted(REPO.glob(pattern))
        return matches
    p = REPO / pattern
    return [p] if p.exists() else []


def section_empirical_spotcheck(out_dir: Path) -> str:
    detail_path = out_dir / "empirical_spotcheck.md"
    chunks = ["# Round-18 empirical artifact spot-check", "",
              "Per-prompt resolution of declared SCOPE artifacts. ",
              "For each artifact: file present? non-empty? numeric content?",
              "placeholders flagged?", ""]
    summary_rows: list[tuple[str, str, str]] = []

    for prompt_id, label, patterns in EMPIRICAL_SPECS:
        chunks.append(f"## Prompt {prompt_id} — {label}")
        chunks.append("")
        all_present = True
        any_placeholder = False
        any_empty = False
        artifact_count = 0
        for pat in patterns:
            matches = _resolve(pat)
            if not matches:
                all_present = False
                chunks.append(f"- `{pat}` — **MISSING** (no glob matches)")
                continue
            for path in matches:
                artifact_count += 1
                rel = path.relative_to(REPO)
                if path.is_dir():
                    files = [f for f in path.rglob("*") if f.is_file()]
                    if not files:
                        any_empty = True
                        chunks.append(f"- `{rel}/` — **EMPTY directory**")
                    else:
                        chunks.append(
                            f"- `{rel}/` — directory with {len(files)} file(s)"
                        )
                    continue
                size = path.stat().st_size
                if size == 0:
                    any_empty = True
                    chunks.append(f"- `{rel}` — **EMPTY** (0 bytes)")
                    continue
                # Read text where reasonable; binary (PDF, parquet) just gets size.
                if path.suffix in {".pdf", ".parquet", ".png", ".jpg", ".jpeg"}:
                    chunks.append(f"- `{rel}` — {size:,} bytes (binary)")
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except Exception as exc:
                    chunks.append(f"- `{rel}` — read error: {exc}")
                    continue
                # Placeholder detection only matters for *output* artifacts —
                # generated documents, results files. A page.tsx or a shell
                # script that *consumes* a run-stamp directory legitimately
                # contains the literal string `<run-stamp>` in its source.
                is_output_artifact = (
                    path.suffix in {".md", ".tex", ".json", ".csv"}
                    and not str(path.relative_to(REPO)).startswith(("noosphere/scripts/", "scripts/"))
                    and not path.name.endswith(("page.tsx", "page.tsx"))
                )
                placeholders = _has_placeholders(text) if is_output_artifact else []
                has_nums = _has_numbers(text)
                flags = []
                if is_output_artifact and not has_nums:
                    flags.append("no digits")
                if placeholders:
                    any_placeholder = True
                    flags.append("placeholders=" + ",".join(placeholders))
                flag_str = "  ⚠ " + " | ".join(flags) if flags else ""
                chunks.append(f"- `{rel}` — {size:,} bytes{flag_str}")

        if not all_present:
            verdict = "INCOMPLETE"
        elif any_empty:
            verdict = "EMPTY ARTIFACT"
        elif any_placeholder:
            verdict = "PLACEHOLDERS"
        else:
            verdict = "REAL"
        chunks.append("")
        chunks.append(f"**Prompt {prompt_id} verdict: {verdict}** "
                      f"({artifact_count} artifact(s) resolved)")
        chunks.append("")
        summary_rows.append((prompt_id, label, verdict))

    detail_path.write_text("\n".join(chunks), encoding="utf-8")

    # Top-level summary in REPORT.
    out = ["## D. Empirical artifact spot-check (prompts 13–20)", ""]
    out.append("| Prompt | Topic | Verdict |")
    out.append("|---:|---|---|")
    for prompt_id, label, verdict in summary_rows:
        out.append(f"| {prompt_id} | {label} | **{verdict}** |")
    out.append("")
    out.append("Verdicts:")
    out.append("- **REAL**: every artifact present, non-empty, no placeholder strings.")
    out.append("- **PLACEHOLDERS**: artifacts present but contain `<run-stamp>`, `TBD`, `XX.X%`, etc.")
    out.append("- **EMPTY ARTIFACT**: at least one declared artifact is 0 bytes.")
    out.append("- **INCOMPLETE**: at least one declared artifact glob has no match on disk.")
    out.append("")
    out.append(f"Per-artifact detail: `{detail_path.relative_to(REPO)}`.")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# E) cross-prompt coupling — Round-17 SCOPE exports must still resolve
# ---------------------------------------------------------------------------

ROUND17_ARCHIVE = REPO / "coding_prompts" / "archive_round17_methodology_implementation"

SCOPE_LINE_RE = re.compile(
    r"""^\s*-\s+`([^`]+)`\s+(?:CREATE|MODIFY)\b""",
    re.MULTILINE,
)


def _r17_scope_paths() -> dict[str, list[str]]:
    paths: dict[str, list[str]] = {}
    if not ROUND17_ARCHIVE.exists():
        return paths
    for prompt in sorted(ROUND17_ARCHIVE.glob("*.txt")):
        text = prompt.read_text(encoding="utf-8", errors="replace")
        scope = SCOPE_LINE_RE.findall(text)
        # Only files (not "MODIFY (only on bug)" etc — the regex already
        # skips those because they don't match CREATE|MODIFY directly).
        cleaned = [s.strip() for s in scope if not s.startswith("http")]
        if cleaned:
            paths[prompt.name] = cleaned
    return paths


def section_coupling(out_dir: Path) -> str:
    detail_path = out_dir / "coupling_analysis.md"
    chunks = [
        "# Round-18 cross-prompt coupling analysis",
        "",
        "Round-18 stabilization prompts (01–12) altered abstractions used by",
        "Round-17 code. This section walks every Round-17 archived prompt's",
        "SCOPE block, checks whether each declared file still resolves, and",
        "(when it does not) looks for a compatibility shim that re-exports",
        "the original module path so existing imports keep working.",
        "",
        "Resolution rules:",
        "- Path on disk: present.",
        "- Glob containing `*` accepted if any match exists.",
        "- For Python module paths, also probe whether the parent directory was",
        "  promoted to a package (e.g. `noosphere/observability.py` → ",
        "  `noosphere/observability/__init__.py`).",
        "",
    ]
    summary_total = 0
    summary_present = 0
    summary_shimmed = 0
    summary_dropped: list[tuple[str, str]] = []

    paths = _r17_scope_paths()
    for prompt, items in paths.items():
        chunks.append(f"## {prompt}")
        for entry in items:
            summary_total += 1
            target = REPO / entry
            present = target.exists()
            shim_note = ""
            if not present and entry.endswith(".py"):
                pkg_path = target.with_suffix("") / "__init__.py"
                if pkg_path.exists():
                    present = True
                    shim_note = (f" — promoted to package: "
                                 f"`{pkg_path.relative_to(REPO)}`")
            if not present and "*" in entry:
                if list(REPO.glob(entry)):
                    present = True
            mark = "ok" if present else "MISSING"
            if present:
                summary_present += 1
                if shim_note:
                    summary_shimmed += 1
            else:
                summary_dropped.append((prompt, entry))
            chunks.append(f"- `{entry}` — {mark}{shim_note}")
        chunks.append("")

    chunks.insert(8, f"_Inspected {summary_total} declared SCOPE entries across "
                     f"{len(paths)} Round-17 prompts._\n")

    detail_path.write_text("\n".join(chunks), encoding="utf-8")

    out = ["## E. Cross-prompt coupling (Round-17 SCOPE exports)", ""]
    out.append(f"- Total declared SCOPE entries scanned: **{summary_total}**")
    out.append(f"- Still resolve on disk: **{summary_present}**")
    out.append(f"- Resolved via package-promotion shim: **{summary_shimmed}**")
    out.append(f"- Dropped without shim: **{len(summary_dropped)}**")
    out.append("")
    if summary_dropped:
        out.append("### Dropped (potentially silent breakage)")
        out.append("")
        for prompt, entry in summary_dropped[:60]:
            out.append(f"- `{entry}`  (declared by `{prompt}`)")
        if len(summary_dropped) > 60:
            out.append(f"- … {len(summary_dropped) - 60} more — see "
                       f"`{detail_path.relative_to(REPO)}`")
        out.append("")
    out.append(f"Per-prompt detail: `{detail_path.relative_to(REPO)}`.")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    timestamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    out_dir = REPO / "docs" / "runs" / f"round18_verification_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        f"# Round-18 verification — {timestamp}",
        "",
        "Generated by `scripts/round18_verification.py` "
        "(invoked from `coding_prompts/50_round18_verification.txt`).",
        "",
        "Re-run command: `python3 scripts/round18_verification.py`.",
        "Public-surface HTTP smoke (separate, requires dev server up):",
        "`PUBLIC_BASE_URL=http://127.0.0.1:3000 ./scripts/round18_smoke.sh`",
        "",
        "This report is the deliverable. It records the state of the round at",
        "the moment of verification — including red signals. It does not move",
        "any prompts to archive (the founder runs `_audit_implementation.py",
        "--apply` separately).",
        "",
        "---",
        "",
        section_test_suites(out_dir),
        section_invariants(),
        section_audit(),
        section_empirical_spotcheck(out_dir),
        section_coupling(out_dir),
        "## F. Gaps and follow-up prompts",
        "",
        "See the human-curated section in `REPORT.md` (next to this file). The",
        "machine-generated sections above feed it.",
        "",
    ]
    auto_path = out_dir / "REPORT_auto.md"
    auto_path.write_text("\n".join(chunks), encoding="utf-8")
    print(f"wrote {auto_path.relative_to(REPO)}")
    print(f"wrote {(out_dir / 'test_output.md').relative_to(REPO)}")
    print(f"wrote {(out_dir / 'empirical_spotcheck.md').relative_to(REPO)}")
    print(f"wrote {(out_dir / 'coupling_analysis.md').relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
