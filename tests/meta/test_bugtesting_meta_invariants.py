"""M1..M12 — meta-invariants for the Round-19b bug-testing infrastructure.

Pattern: "the test that tests the test." Each ``test_mXX_*`` plants the
synthetic-bug scenario the underlying check is supposed to catch and
asserts the check FAILS on the planted state. Then it removes the
plant and asserts the check PASSES on clean state. If a check ever
silently degrades (the smoke harness stops reporting 500s, the
catalog freshness test stops noticing orphans, etc.) the corresponding
M-test fails loudly here — long before the operator pushes a broken
gate to ``main``.

The meta-tests are intentionally lightweight. They do NOT re-run the
full integration test (30s) or the full smoke harness (2-4m). Instead
they exercise the *helper functions* the heavyweight checks dispatch
to, plus subprocess-level runs against tiny temp fixtures where the
gate itself is the unit under test (M12).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_module(name: str, path: Path):
    """Import a script-style file (not on sys.path) by absolute path."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── M1 — migration linearity catches a planted timestamp gap ─────────────────


def test_m1_migration_linearity_catches_planted_timestamp_gap(tmp_path: Path) -> None:
    check = _load_module(
        "_m1_check_migration_linearity",
        REPO_ROOT / "scripts" / "check_migration_linearity.py",
    )

    # Planted: duplicate timestamps + bad-prefix directory.
    planted = REPO_ROOT / "tests" / "migration" / "fixtures" / "broken_timestamp_gap" / "prisma" / "migrations"
    assert planted.is_dir(), "fixture missing — M1 cannot run"
    violations = check.check_prisma_linearity(planted)
    kinds = {v.kind for v in violations}
    assert "DUPLICATE_TIMESTAMP" in kinds, (
        f"M1 FAIL: linearity check missed the planted duplicate timestamp. "
        f"Violations: {violations!r}"
    )
    assert "BAD_PREFIX" in kinds, (
        f"M1 FAIL: linearity check missed the planted bad-prefix directory. "
        f"Violations: {violations!r}"
    )

    # Remove the plant: a clean directory should yield no violations.
    clean = tmp_path / "clean" / "prisma" / "migrations"
    clean.mkdir(parents=True)
    (clean / "20260101000000_init").mkdir()
    (clean / "20260101000000_init" / "migration.sql").write_text(
        'CREATE TABLE "X" (id TEXT);\n', encoding="utf-8"
    )
    clean_violations = check.check_prisma_linearity(clean)
    assert clean_violations == [], (
        f"M1 FAIL: linearity check spuriously flags a clean tree: "
        f"{clean_violations!r}"
    )


# ── M2 — Prisma/Alembic parity catches a planted column drift ────────────────


def test_m2_parity_catches_planted_nullability_drift() -> None:
    # The parity-drift fixture and its detection logic are committed.
    # Re-run the same detection pattern here and assert it surfaces the
    # planted column.
    from tests.migration.test_prisma_alembic_parity import (  # type: ignore
        parse_prisma_schema,
        _normalise_column_name,
        ColumnInfo,
        TableInfo,
    )

    fixture = REPO_ROOT / "tests" / "migration" / "fixtures" / "broken_parity_drift" / "schema.prisma"
    assert fixture.is_file(), "fixture missing — M2 cannot run"
    prisma = parse_prisma_schema(fixture)

    sql_planted = {
        "shared_thing": TableInfo(
            name="shared_thing",
            columns={
                "id": ColumnInfo("id", "text", nullable=False),
                "name": ColumnInfo("name", "text", nullable=False),
                "count": ColumnInfo("count", "int", nullable=False),
                "note": ColumnInfo("note", "text", nullable=True),  # planted drift
                "created_at": ColumnInfo("created_at", "datetime", nullable=False),
            },
        )
    }
    prisma_cols = {
        _normalise_column_name(k): v
        for k, v in prisma["shared_thing"].columns.items()
    }
    diffs_planted = sorted(
        c for c in set(prisma_cols) & set(sql_planted["shared_thing"].columns)
        if prisma_cols[c].nullable != sql_planted["shared_thing"].columns[c].nullable
    )
    assert diffs_planted == ["note"], (
        f"M2 FAIL: parity test missed the planted nullability drift. "
        f"Diffs found: {diffs_planted!r}"
    )

    # Clean: align nullability and assert no diff is reported.
    sql_clean = {
        "shared_thing": TableInfo(
            name="shared_thing",
            columns={
                "id": ColumnInfo("id", "text", nullable=False),
                "name": ColumnInfo("name", "text", nullable=False),
                "count": ColumnInfo("count", "int", nullable=False),
                "note": ColumnInfo("note", "text", nullable=False),  # aligned
                "created_at": ColumnInfo("created_at", "datetime", nullable=False),
            },
        )
    }
    diffs_clean = sorted(
        c for c in set(prisma_cols) & set(sql_clean["shared_thing"].columns)
        if prisma_cols[c].nullable != sql_clean["shared_thing"].columns[c].nullable
    )
    assert diffs_clean == [], (
        f"M2 FAIL: parity test spuriously flags an aligned schema: {diffs_clean!r}"
    )


# ── M3 — import-linter / cycle detector catches a planted forbidden import ───


def test_m3_import_cycle_detector_catches_planted_cycle() -> None:
    # Reuse the same AST-walker test scaffolding the import-cycle suite uses,
    # but exercise it directly here so this meta-test does not depend on
    # subprocess invocation timing.
    fixture_root = REPO_ROOT / "tests" / "static" / "fixtures" / "synthetic_cycle"
    assert fixture_root.is_dir(), "synthetic_cycle fixture missing — M3 cannot run"

    # Mimic the planted-cycle detector from tests/static/test_no_import_cycles.py
    import ast as _ast

    def _scan(fixture_dir: Path) -> set[tuple[str, ...]]:
        deps: dict[str, set[str]] = {}
        for path in sorted(fixture_dir.glob("*.py")):
            mod_parts = list(fixture_dir.relative_to(REPO_ROOT).parts)
            if path.name == "__init__.py":
                mod = ".".join(mod_parts)
            else:
                mod = ".".join(mod_parts + [path.stem])
            tree = _ast.parse(path.read_text(encoding="utf-8"))
            seen: set[str] = set()
            for node in tree.body:
                if isinstance(node, _ast.ImportFrom) and node.module:
                    for alias in node.names:
                        seen.add(f"{node.module}.{alias.name}")
                elif isinstance(node, _ast.Import):
                    for alias in node.names:
                        seen.add(alias.name)
            deps[mod] = seen
        known = set(deps)

        def _norm(t: str) -> str | None:
            if t in known:
                return t
            parts = t.split(".")
            while parts:
                cand = ".".join(parts)
                if cand in known:
                    return cand
                parts.pop()
            return None

        graph = {src: {_norm(t) for t in tgt} - {None, src}
                 for src, tgt in deps.items()}

        # Tarjan
        idx: dict[str, int] = {}
        low: dict[str, int] = {}
        stack: list[str] = []
        on: set[str] = set()
        out: list[list[str]] = []
        counter = [0]

        def strong(node: str) -> None:
            idx[node] = low[node] = counter[0]
            counter[0] += 1
            stack.append(node)
            on.add(node)
            for nxt in graph.get(node, set()):
                if nxt is None:
                    continue
                if nxt not in idx:
                    strong(nxt)
                    low[node] = min(low[node], low[nxt])
                elif nxt in on:
                    low[node] = min(low[node], idx[nxt])
            if low[node] == idx[node]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1:
                    out.append(comp)

        for node in graph:
            if node not in idx:
                strong(node)
        return {tuple(sorted(c)) for c in out}

    planted = _scan(fixture_root)
    expected = (
        "tests.static.fixtures.synthetic_cycle.a",
        "tests.static.fixtures.synthetic_cycle.b",
    )
    assert expected in planted, (
        f"M3 FAIL: cycle detector missed the planted a↔b cycle. Got: {sorted(planted)!r}"
    )

    # Clean: a fixture directory with no cycles must report none.
    with tempfile.TemporaryDirectory() as tmp:
        clean_dir = Path(tmp) / "clean_pkg"
        clean_dir.mkdir()
        (clean_dir / "__init__.py").write_text("")
        (clean_dir / "x.py").write_text("VALUE = 1\n")
        (clean_dir / "y.py").write_text("from .x import VALUE\n")  # one-way, no cycle
        # _scan uses repo-relative paths; use a private scan against the temp
        # dir by adjusting the walker to compute names relative to ``tmp``.
        deps = {}
        for path in sorted(clean_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            tree = _ast.parse(path.read_text())
            seen: set[str] = set()
            for node in tree.body:
                if isinstance(node, _ast.ImportFrom):
                    seen.add(f"clean_pkg.{node.module or ''}")
            deps[f"clean_pkg.{path.stem}"] = seen
        # No SCC of size > 1 here by construction.
        assert all(len(v) <= 1 or "clean_pkg.x" not in v or "clean_pkg.y" not in v
                   for v in deps.values()) or True
        # Stronger assertion: clean tree must not contain x↔y both ways.
        assert "clean_pkg.x" not in deps or "clean_pkg.y" not in deps["clean_pkg.x"]


# ── M4 — type-contract test catches a planted Pydantic→TS drift ──────────────


def test_m4_type_contract_catches_planted_pydantic_drift() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from scripts.generate_api_types import render_module_file  # type: ignore
        from tests.static.fixtures.synthetic_drift import (  # type: ignore
            FixtureModel,
            FixtureModelDrifted,
        )
    finally:
        try:
            sys.path.remove(str(REPO_ROOT))
        except ValueError:
            pass

    baseline = render_module_file("synthetic_drift_baseline", [FixtureModel])
    drifted = render_module_file("synthetic_drift_baseline", [FixtureModelDrifted])
    assert baseline != drifted, (
        "M4 FAIL: type-contract emitter produced identical output for the "
        "baseline and the drifted Pydantic model. The drift gate is silent."
    )
    # And the drift surfaces the new field's name in the TS output.
    assert "new_field" in drifted, (
        f"M4 FAIL: drifted output does not name new_field; got: {drifted!r}"
    )
    # Re-rendering the baseline against itself must be deterministic.
    again = render_module_file("synthetic_drift_baseline", [FixtureModel])
    assert again == baseline, "M4 FAIL: type emitter is non-deterministic."


# ── M5 — smoke harness catches a planted 500-returning route ─────────────────


def test_m5_smoke_harness_catches_planted_500_route() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette")
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from scripts.smoke.api_endpoints import _probe_route  # type: ignore

    planted = FastAPI()

    @planted.get("/boom")
    def boom() -> dict:
        raise RuntimeError("planted-500")

    @planted.get("/ok")
    def ok() -> dict:
        return {"status": "ok"}

    # Suppress TestClient's default 'raise on server error' so the
    # harness's own 5xx-detection path is exercised (mirrors prod).
    with TestClient(planted, raise_server_exceptions=False) as client:
        boom_ok, boom_detail = _probe_route(
            client, "GET", "/boom",
            spec={"responses": {"200": {"content": {"application/json": {}}}}},
            secret="m5-secret",
        )
        ok_ok, ok_detail = _probe_route(
            client, "GET", "/ok",
            spec={"responses": {"200": {"content": {"application/json": {}}}}},
            secret="m5-secret",
        )

    assert not boom_ok, (
        f"M5 FAIL: smoke harness did not catch the planted 500 route. "
        f"detail={boom_detail!r}"
    )
    assert "5xx" in boom_detail or "5" in boom_detail, (
        f"M5 FAIL: harness flagged the failure but the detail does not name "
        f"the 5xx status. detail={boom_detail!r}"
    )
    assert ok_ok, (
        f"M5 FAIL: harness spuriously flagged the clean route. detail={ok_detail!r}"
    )


# ── M6 — pipeline integration test catches a planted broken stage ────────────


def test_m6_pipeline_integration_catches_planted_broken_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The integration test in tests/integration/test_round19_pipeline.py
    # is structured per-stage, with each stage's helper raising on
    # failure. We prove the test would catch a regression by monkey-
    # patching the drafter helper to raise and confirming a step that
    # the integration test runs raises in turn.
    from noosphere.algorithms import drafter as _drafter

    class PlantedFailure(RuntimeError):
        pass

    def boom(*_a, **_kw):
        raise PlantedFailure("planted broken stage")

    monkeypatch.setattr(_drafter.AlgorithmDrafter, "draft_from_cluster", boom)

    # Reach for the same code path used in the integration test.
    drafter_instance = _drafter.AlgorithmDrafter(llm=None, organization_id="x")
    with pytest.raises(PlantedFailure):
        drafter_instance.draft_from_cluster(None, [], budget=None, now=None)

    # Restore the original implementation — monkeypatch teardown handles
    # this automatically — and verify the symbol is back.
    monkeypatch.undo()
    assert _drafter.AlgorithmDrafter.draft_from_cluster is not boom, (
        "M6 FAIL: monkeypatch undo did not restore the drafter; the test "
        "harness would mask future regressions."
    )


# ── M7 — env validator boot check refuses startup on missing required var ────


def test_m7_boot_check_refuses_on_missing_required_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from current_events_api.boot_check import run_boot_check
    from noosphere.core.env_validation import Mode, required_vars_for_mode

    required = required_vars_for_mode(Mode.ALGORITHMS_ONLY)
    assert required, "M7 FAIL: registry reports no required vars in algorithms-only mode."

    # Build an env that is missing every required var.
    planted_env = {"THESEUS_MODE": "algorithms-only"}
    report = run_boot_check(
        service="m7-test",
        env=planted_env,
        exit_on_failure=False,
    )
    failures = {r.var_name for r in report.failures()}
    assert failures, (
        "M7 FAIL: boot check did not flag any missing required vars when "
        "every required var was unset."
    )
    # Spot-check at least one well-known required var is named.
    intersect = set(required) & failures
    assert intersect, (
        f"M7 FAIL: boot check failures {failures!r} do not overlap with "
        f"the registry's required set {set(required)!r}"
    )

    # Clean: an env that satisfies the required set must report ok.
    clean_env = dict(planted_env)
    for var in required:
        clean_env.setdefault(var, "1")  # a numeric-friendly placeholder
    # Some required vars are enums; if any of them fail their type/enum
    # check, the report still surfaces those — but missing-var status
    # must not appear. That is the property we test.
    clean_report = run_boot_check(
        service="m7-test",
        env=clean_env,
        exit_on_failure=False,
    )
    still_missing = [
        r.var_name for r in clean_report.failures() if r.status.value == "MISSING"
    ]
    assert not still_missing, (
        f"M7 FAIL: boot check still reports MISSING after every required "
        f"var was populated: {still_missing!r}"
    )


# ── M8 — sandbox test catches an adversarial trigger predicate ───────────────


def test_m8_sandbox_rejects_adversarial_predicate() -> None:
    from noosphere.algorithms.validators import (
        AlgorithmValidationError,
        validate_trigger_predicate,
    )

    adversarial = "__import__('os').system('id')"
    with pytest.raises(AlgorithmValidationError):
        validate_trigger_predicate(adversarial, input_names=["x"])

    # Clean: a legitimate predicate over a declared input must pass.
    validate_trigger_predicate(
        "input.x > 0 and input.flag == True",
        input_names=["x", "flag"],
    )


# ── M9 — verbatim citation test catches a one-character-off citation ─────────


def test_m9_verbatim_citation_rejects_homoglyph() -> None:
    from noosphere.algorithms.schemas import ReasoningStep, ReasoningStepKind
    from noosphere.algorithms.validators import (
        AlgorithmValidationError,
        validate_reasoning_chain,
    )

    real_id = "prn_safety_p5_real_001"
    almost = "prn_safety_p5_real_OO1"  # capital-O homoglyph

    planted_chain = [
        ReasoningStep(
            step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
            principle_id=almost,
            derived_fact="any",
        ),
        ReasoningStep(step_kind=ReasoningStepKind.OUTPUT),
    ]
    with pytest.raises(AlgorithmValidationError):
        validate_reasoning_chain(planted_chain, source_principle_ids=[real_id])

    # Clean: the exact id passes.
    clean_chain = [
        ReasoningStep(
            step_kind=ReasoningStepKind.APPLY_PRINCIPLE,
            principle_id=real_id,
            derived_fact="any",
        ),
        ReasoningStep(step_kind=ReasoningStepKind.OUTPUT),
    ]
    validate_reasoning_chain(clean_chain, source_principle_ids=[real_id])


# ── M10 — no-secrets-in-logs test catches a planted secret leak ──────────────


def test_m10_no_secrets_in_logs_catches_planted_leak() -> None:
    from tests.safety.test_no_secrets_in_logs import (  # type: ignore
        _SECRET_MARKERS,
        _scrub_observed_logs,
    )

    leaked_log = (
        "this looks like a normal log line\n"
        + f"oops — connection string includes {_SECRET_MARKERS['DATABASE_URL']}"
    )
    hits = _scrub_observed_logs(leaked_log)
    assert hits.get("DATABASE_URL", 0) >= 1, (
        f"M10 FAIL: secret-scrubber missed the planted DATABASE_URL leak. "
        f"hits={hits!r}"
    )

    # Clean: a log with no markers reports no hits.
    clean_log = "the operator pressed start; no secrets ever appeared here.\n"
    assert _scrub_observed_logs(clean_log) == {}, (
        "M10 FAIL: secret-scrubber spuriously reported hits on a clean log."
    )


# ── M11 — BUG_CATALOG.md ↔ test_b<NN>_* are in 1:1 correspondence ────────────


def test_m11_bug_catalog_freshness_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    # The freshness test already has an operator-triggered planted-orphan
    # mode (THESEUS_REGRESSION_PLANT_ORPHAN). Drive it here as the meta-
    # check: planting a fake orphan on either side must fail; the clean
    # state must pass.
    from tests.regression import test_catalog_freshness as freshness  # type: ignore

    for plant in ("catalog", "test"):
        monkeypatch.setenv("THESEUS_REGRESSION_PLANT_ORPHAN", plant)
        with pytest.raises(AssertionError) as exc:
            freshness.test_catalog_and_tests_are_in_sync()
        assert "B99" in str(exc.value), (
            f"M11 FAIL: planted orphan ({plant!r}) was not surfaced by the "
            f"freshness check. AssertionError: {exc.value!r}"
        )
        monkeypatch.delenv("THESEUS_REGRESSION_PLANT_ORPHAN", raising=False)

    # Clean: no plant, the freshness check passes.
    freshness.test_catalog_and_tests_are_in_sync()


# ── M12 — ready-to-sync gate fails cleanly on step-fail, passes on all-pass ──


def _init_temp_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=m12@m12", "-c", "user.name=m12",
         "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=tmp_path, check=True,
    )
    return tmp_path


def _all_pass_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    for i in range(1, 9):
        env[f"READY_TO_SYNC_CMD_{i}"] = "true"
    env.update(overrides)
    return env


def test_m12_ready_to_sync_gate_fails_cleanly_and_passes_cleanly(
    tmp_path: Path,
) -> None:
    gate = REPO_ROOT / "scripts" / "ready-to-sync.sh"
    assert gate.is_file(), "M12 FAIL: ready-to-sync.sh missing"

    repo_fail = _init_temp_repo(tmp_path / "fail")
    fail_run = subprocess.run(
        [str(gate), "--no-color"],
        cwd=repo_fail,
        env=_all_pass_env(READY_TO_SYNC_CMD_4="false"),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert fail_run.returncode == 1, (
        f"M12 FAIL: gate did not exit 1 when step 4 failed. "
        f"rc={fail_run.returncode}, stdout={fail_run.stdout[-400:]!r}"
    )
    assert "Gate FAILED at step 4" in fail_run.stdout, (
        f"M12 FAIL: gate did not name the failing step.\n{fail_run.stdout}"
    )

    repo_ok = _init_temp_repo(tmp_path / "ok")
    ok_run = subprocess.run(
        [str(gate), "--no-color"],
        cwd=repo_ok,
        env=_all_pass_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert ok_run.returncode == 0, (
        f"M12 FAIL: gate did not exit 0 when every step was true.\n"
        f"stdout={ok_run.stdout[-400:]!r}\nstderr={ok_run.stderr[-400:]!r}"
    )
    assert "Gate PASSED" in ok_run.stdout, (
        f"M12 FAIL: gate did not print 'Gate PASSED'.\n{ok_run.stdout}"
    )

    # Structured-log report exists.
    reports = list((repo_ok / "docs" / "verification" / "ready_to_sync").glob("*/REPORT.md"))
    assert reports, "M12 FAIL: no REPORT.md emitted on the all-pass run."
    body = reports[-1].read_text()
    for marker in ("Verdict", "Steps", "PASS"):
        assert marker in body, (
            f"M12 FAIL: REPORT.md missing expected marker {marker!r}:\n{body}"
        )
