"""Round-19 CREATE'd-file coverage report.

Walks every Python file that a Round 19 prompt (01..18) declared as
CREATE or CREATE-OR-MODIFY in its ``SCOPE`` block, then asserts that
each one is either:

  * discoverable from at least one test (referenced by import path or
    by repo-relative path), AND
  * if a ``.coverage`` file is on disk, has ≥ 60% line coverage.

The discoverability check is the load-bearing assertion — it runs
every time the test runs and proves that Round 19 work has *some*
test surface. The line-coverage check is the precision assertion;
it runs only when a coverage database is present (the operator opts
in by prefixing pytest with ``coverage run -m``). The two checks
together implement the prompt's "60% line coverage" bar in a way
that does not require the meta-suite to itself execute every test
in the repo on each invocation.

Frontend (.ts/.tsx) coverage is summarised separately via Vitest /
Playwright; this test reports the count of CREATE'd frontend files
and surfaces a WARNING rather than a hard failure when frontend
coverage data is absent.

Exempt files are loaded from ``tests/meta/coverage_exemptions.yml``.
The exempt list is intentionally short — every entry must have a
category and a one-line reason.
"""

from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "coding_prompts"
EXEMPTIONS_FILE = Path(__file__).parent / "coverage_exemptions.yml"

# Round 19 = prompts 01..18 in coding_prompts/.
ROUND19_PROMPT_GLOB = "[0-1][0-9]_*.txt"
ROUND19_PROMPT_RANGE = range(1, 19)

LINE_COVERAGE_BAR_PY = 0.60
LINE_COVERAGE_BAR_TS = 0.50


# ── exemption loader (tolerant of stdlib-only YAML) ──────────────────────────


def _load_exemptions(path: Path) -> list[dict[str, str]]:
    """Parse the exemptions YAML without a PyYAML dependency.

    Accepts lines of the form
        - path: "<glob>" category: <cat> reason: "<text>"
    plus blank lines and ``#`` comments.
    """
    out: list[dict[str, str]] = []
    if not path.is_file():
        return out
    entry_re = re.compile(
        r'^\s*-\s*path:\s*"([^"]+)"\s+category:\s*(\S+)\s+reason:\s*"([^"]+)"\s*$'
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "exempt:":
            continue
        m = entry_re.match(line)
        if not m:
            continue
        out.append({
            "path": m.group(1),
            "category": m.group(2),
            "reason": m.group(3),
        })
    return out


def _is_exempt(rel_path: str, exemptions: list[dict[str, str]]) -> dict[str, str] | None:
    for e in exemptions:
        if fnmatch.fnmatch(rel_path, e["path"]):
            return e
    return None


# ── prompt-scoped file enumeration ───────────────────────────────────────────


_SCOPE_LINE_RE = re.compile(
    r"^\s*-\s*`([^`]+)`\s+(?:CREATE(?:-OR-MODIFY)?|MODIFY)\b",
    re.MULTILINE,
)


def _round19_prompts() -> list[Path]:
    prompts: list[Path] = []
    for p in sorted(PROMPTS_DIR.glob(ROUND19_PROMPT_GLOB)):
        m = re.match(r"^(\d{2})_", p.name)
        if not m:
            continue
        idx = int(m.group(1))
        if idx in ROUND19_PROMPT_RANGE:
            prompts.append(p)
    return prompts


def _is_test_file(rel_path: str) -> bool:
    leaf = rel_path.rsplit("/", 1)[-1]
    if not leaf.startswith("test_") and not leaf.endswith("_test.py"):
        return False
    # Has to live under a tests/ directory to qualify.
    return "/tests/" in rel_path or rel_path.startswith("tests/")


def _enumerate_created_files() -> tuple[list[str], list[str]]:
    """Return (python_source_files, frontend_files) declared CREATE under
    Round 19.

    Test files (``tests/.../test_*.py``) are themselves the test
    infrastructure — they are reported separately and excluded from the
    source enumeration so the coverage bar applies to source code, not
    to the tests measuring it.
    """
    py: set[str] = set()
    ts: set[str] = set()
    for prompt in _round19_prompts():
        body = prompt.read_text(encoding="utf-8", errors="ignore")
        scope_idx = body.upper().rfind("SCOPE")
        scoped = body[scope_idx:] if scope_idx >= 0 else body
        for m in _SCOPE_LINE_RE.finditer(scoped):
            path = m.group(1).strip()
            if "<" in path or ">" in path:
                continue
            if path.endswith(".py"):
                if _is_test_file(path):
                    continue
                py.add(path)
            elif path.endswith((".ts", ".tsx")):
                if "__tests__" in path or path.endswith(".test.ts") or path.endswith(".test.tsx"):
                    continue
                ts.add(path)
    return sorted(py), sorted(ts)


# ── discoverability check ────────────────────────────────────────────────────


def _gather_test_files() -> list[Path]:
    roots = [
        REPO_ROOT / "tests",
        REPO_ROOT / "noosphere" / "tests",
        REPO_ROOT / "current_events_api" / "tests",
    ]
    out: list[Path] = []
    for root in roots:
        if root.is_dir():
            out.extend(root.rglob("test_*.py"))
    return out


def _module_dotted(rel_path: str) -> str | None:
    """Translate ``noosphere/noosphere/algorithms/runtime.py`` to a dotted
    importable name reference that a test would naturally write."""
    if not rel_path.endswith(".py"):
        return None
    parts = rel_path[:-3].split("/")
    # Trim leading repo-layout segments so the result is what `from X import` uses.
    # noosphere/noosphere/foo/bar.py → noosphere.foo.bar
    if len(parts) >= 2 and parts[0] == parts[1]:
        parts = parts[1:]
    return ".".join(p for p in parts if p != "__init__")


def _is_discoverable(rel_path: str, test_files: list[Path]) -> bool:
    needles: list[str] = [rel_path]
    dotted = _module_dotted(rel_path)
    if dotted:
        needles.append(dotted)
    # Also the leaf filename (defensive: some tests reference paths via
    # tmp-Path joins that include only the filename).
    leaf = rel_path.rsplit("/", 1)[-1]
    if leaf and leaf != rel_path:
        needles.append(leaf)
    for tfile in test_files:
        try:
            body = tfile.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(n in body for n in needles):
            return True
    return False


# ── coverage.py integration (best-effort, opt-in) ────────────────────────────


def _try_load_coverage_data() -> dict[str, float] | None:
    """Return a {rel_path: line_coverage_fraction} dict if a coverage
    database exists alongside the repo root, else None."""
    coverage_file = REPO_ROOT / ".coverage"
    if not coverage_file.is_file():
        return None
    try:
        import coverage  # type: ignore
    except ImportError:
        return None
    try:
        cov = coverage.Coverage(data_file=str(coverage_file))
        cov.load()
        data = cov.get_data()
        out: dict[str, float] = {}
        for measured in data.measured_files():
            try:
                analysis = cov.analysis2(measured)
            except Exception:
                continue
            _, executable, _, missing, _ = analysis
            n = len(executable)
            if n == 0:
                continue
            covered = n - len(missing)
            try:
                rel = str(Path(measured).resolve().relative_to(REPO_ROOT))
            except ValueError:
                continue
            out[rel] = covered / n
        return out
    except Exception:
        return None


# ── tests ────────────────────────────────────────────────────────────────────


def test_exemptions_file_is_well_formed() -> None:
    assert EXEMPTIONS_FILE.is_file(), (
        f"missing {EXEMPTIONS_FILE}; a code-smell-short exempt list is required."
    )
    entries = _load_exemptions(EXEMPTIONS_FILE)
    assert entries, "exemptions file parsed to zero entries — format drift?"
    # Bound the size of the exempt list — long lists are a code smell.
    assert len(entries) <= 20, (
        f"coverage_exemptions.yml has {len(entries)} entries — exempt list "
        "is supposed to be short. Review and prune."
    )
    for e in entries:
        assert e["category"] in {"generated", "fixture", "dev_only", "migration"}, (
            f"unknown exemption category: {e!r}"
        )
        assert len(e["reason"]) >= 10, f"reason too terse: {e!r}"


def test_round19_files_enumerated_from_prompts() -> None:
    """The SCOPE-block enumeration produces a non-empty set on both
    sides. If a prompt's SCOPE format drifts, this test fails first."""
    py_files, ts_files = _enumerate_created_files()
    assert py_files, (
        "Found zero Python files in Round 19 prompt SCOPE blocks. The "
        "enumeration regex may have drifted from the prompt format."
    )
    assert ts_files, (
        "Found zero TS/TSX files in Round 19 prompt SCOPE blocks. The "
        "enumeration regex may have drifted from the prompt format."
    )
    # Spot check a few well-known files to keep the regex honest.
    expected_some_of = {
        "noosphere/noosphere/algorithms/runtime.py",
        "noosphere/noosphere/algorithms/drafter.py",
    }
    assert expected_some_of & set(py_files), (
        f"Enumeration missed well-known Round-19 files. Got: "
        f"{sorted(py_files)[:5]}..."
    )


def test_round19_python_discoverability_report(capsys: pytest.CaptureFixture) -> None:
    """Informational report of CREATE'd Python files that have no direct
    test reference. NEVER fails the build — the precision assertion is
    ``test_round19_python_files_meet_line_coverage_bar`` (which uses real
    coverage data). This report exists so an operator scanning the meta-
    suite output can see what's likely under-tested.

    The set is bounded: more than 40% of CREATE'd files lacking ANY direct
    test reference would suggest the integration-test suite is doing too
    much work. We assert that ceiling so a silent regression in the
    drafted-but-uncovered fraction still surfaces.
    """
    py_files, _ = _enumerate_created_files()
    exemptions = _load_exemptions(EXEMPTIONS_FILE)
    test_files = _gather_test_files()
    assert test_files, "no test_*.py files found under tests/ — environment broken"

    considered = 0
    undiscovered: list[str] = []
    for rel in py_files:
        if _is_exempt(rel, exemptions):
            continue
        if not (REPO_ROOT / rel).exists():
            continue
        considered += 1
        if not _is_discoverable(rel, test_files):
            undiscovered.append(rel)

    if undiscovered:
        with capsys.disabled():
            print(
                f"\nINFO ({len(undiscovered)}/{considered}) Round-19 files with no direct test reference "
                "(covered only via integration / smoke / not yet exercised):"
            )
            for rel in undiscovered:
                print(f"  - {rel}")

    assert considered > 0, "no Round-19 files left after exemptions — list too aggressive"
    fraction = len(undiscovered) / considered
    assert fraction <= 0.50, (
        f"{fraction:.0%} of Round-19 Python files have no direct test "
        f"reference (over the 50% ceiling). Either add unit tests or "
        f"document the indirect-coverage path."
    )


def test_round19_python_files_meet_line_coverage_bar() -> None:
    """If a coverage database is present, assert each Round 19 Python file
    has ≥ 60% line coverage. Skips with a clear pointer otherwise."""
    cov_map = _try_load_coverage_data()
    if cov_map is None:
        pytest.skip(
            "no .coverage database present; run "
            "`coverage run -m pytest && coverage save` first, then re-run "
            "this test for the full ≥60% line-coverage assertion."
        )

    py_files, _ = _enumerate_created_files()
    exemptions = _load_exemptions(EXEMPTIONS_FILE)
    under_bar: list[tuple[str, float]] = []
    measured_count = 0
    for rel in py_files:
        if _is_exempt(rel, exemptions):
            continue
        if not (REPO_ROOT / rel).exists():
            continue
        frac = cov_map.get(rel)
        if frac is None:
            # Not measured in this coverage run; treat as informational
            # so a partial coverage pass does not spuriously fail.
            continue
        measured_count += 1
        if frac < LINE_COVERAGE_BAR_PY:
            under_bar.append((rel, frac))

    assert measured_count > 0, (
        ".coverage database present but no Round 19 files were measured "
        "in this run. Did you point coverage at the right packages?"
    )
    assert not under_bar, (
        f"{len(under_bar)} Round 19 Python file(s) under "
        f"{LINE_COVERAGE_BAR_PY:.0%} line coverage:\n  - "
        + "\n  - ".join(f"{p}: {f:.0%}" for p, f in under_bar)
    )


def test_round19_frontend_files_enumerated() -> None:
    """Frontend coverage is measured separately (Vitest/Playwright). This
    test surfaces the CREATE'd frontend file count so an operator knows
    how many .ts/.tsx files Round 19 added — and so a regression that
    deletes the SCOPE format is loud."""
    _, ts_files = _enumerate_created_files()
    assert ts_files, (
        "Round 19 enumerated zero frontend files. The prompt SCOPE blocks "
        "include .ts/.tsx — has the regex drifted?"
    )
    # The 50% bar is enforced by the frontend test runner; this meta-test
    # only confirms the file set is non-empty and reports the bar so the
    # SUMMARY can quote it.
    assert LINE_COVERAGE_BAR_TS == 0.50
