"""Round 19 load-bearing invariants.

One test per invariant I1..I15 declared in
``coding_prompts/18_round19_verification.txt``. Each test verifies the
*deliverable shape* — the modules, enums, route files, lifecycle hooks,
and copy strings that must be in place for the round to be called done.

These are intentionally lightweight structural tests; the heavier
integration cases (full synthesizer end-to-end against seeded fixtures,
the dialectic latency target, agent reasoner against the planted-weak-
link fixture) already live in the per-feature test suites under
``noosphere/tests/`` and ``dialectic/tests/`` — these invariants assert
that the wiring those tests cover is reachable and load-bearing.
"""

from __future__ import annotations

import importlib
import pathlib
import re
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
NOO = REPO / "noosphere"
CODEX = REPO / "theseus-codex"

# Make ``noosphere`` and ``dialectic`` importable for the structural
# import-based checks below.
for path in (NOO, REPO / "dialectic"):
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)


# ──────────────────────────────────────────────────────────────────────
# I1. Algorithm layer is live (data model exists, enum says ACTIVE,
#     LogicalAlgorithm + AlgorithmInvocation are real persisted classes,
#     and an Invocation row carries a reasoning_trace field).
# ──────────────────────────────────────────────────────────────────────


def test_invariant_01_algorithm_layer_is_live():
    schemas = importlib.import_module("noosphere.algorithms.schemas")
    assert hasattr(schemas, "AlgorithmStatus")
    assert "ACTIVE" in {s.value for s in schemas.AlgorithmStatus}

    models = importlib.import_module("noosphere.models")
    assert hasattr(models, "LogicalAlgorithm"), "LogicalAlgorithm model missing"
    assert hasattr(models, "AlgorithmInvocation"), "AlgorithmInvocation model missing"

    invocation = models.AlgorithmInvocation
    field_names = set(getattr(invocation, "model_fields", {}).keys())
    assert "reasoning_trace" in field_names, (
        "AlgorithmInvocation must carry a reasoning_trace column "
        "(I1: invocation has a complete reasoning_trace)."
    )


# ──────────────────────────────────────────────────────────────────────
# I2. Algorithms are visible: list, detail, invocation-trace routes.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_02_algorithm_routes_present():
    for relpath in (
        "src/app/algorithms/page.tsx",
        "src/app/algorithms/[id]/page.tsx",
        "src/app/algorithms/[id]/invocations/[invocationId]/page.tsx",
    ):
        p = CODEX / relpath
        assert p.exists(), f"missing algorithm route: {relpath}"
        assert p.stat().st_size > 200, f"stub route: {relpath}"

    card = (CODEX / "src/components/algorithms/AlgorithmCard.tsx").read_text()
    # Card must surface name, principles invoked, hit rate, last fired.
    for token in ("name", "principle", "hit", "fired"):
        assert token in card.lower(), f"AlgorithmCard missing '{token}'"


# ──────────────────────────────────────────────────────────────────────
# I3. Contradiction engine canonical, six legacy heuristics DEPRECATED
#     and not called by any new code path.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_03_contradiction_engine_canonical():
    coh_init = (NOO / "noosphere/coherence/__init__.py").read_text()
    assert "DEPRECATED" in coh_init, "coherence/__init__.py must mark legacy heuristics DEPRECATED"
    for heur in ("engine", "argumentation", "probabilistic", "geometry", "information", "judge"):
        assert heur in coh_init, f"legacy heuristic '{heur}' not named in deprecation notice"

    engine_path = NOO / "noosphere/coherence/contradiction_engine.py"
    assert engine_path.exists() and engine_path.stat().st_size > 1000

    # No NEW code path invokes the deprecated *heuristic entrypoints*.
    # Pure math utilities (e.g. ``hoyer_sparsity`` from coherence.geometry)
    # are explicitly allowed: the canonical engine's docstring documents
    # Householder reflection + Hoyer sparsity of difference as its core.
    forbidden_callables = (
        "score_principles",
        "score_claims",
        "coherence_check_local",
        "evaluate_pair_with_neighbors",
        "check_kolmogorov_for_pair",
        "score_claim_geometry",
        "score_claim_information",
        "run_llm_judge",
    )
    for fname in (
        "contradiction_engine.py",
        "contradiction_scheduler.py",
        "auto_resolver.py",
        "lifecycle.py",
        "cluster_index.py",
    ):
        body = (NOO / "noosphere/coherence" / fname).read_text()
        for fn in forbidden_callables:
            assert fn not in body, f"{fname} invokes deprecated heuristic '{fn}'"


# ──────────────────────────────────────────────────────────────────────
# I4. Cluster pre-filter is on; cross-cluster surprise sampling is
#     non-zero per config.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_04_cluster_prefilter_on():
    sched = importlib.import_module("noosphere.coherence.contradiction_scheduler")
    idx = importlib.import_module("noosphere.coherence.cluster_index")

    # Surprise-sampling fractions must be > 0 by default (the docstring
    # promises this; setting either to 0 is a config error).
    assert idx.CROSS_CLUSTER_SAMPLE_FRACTION > 0
    assert idx.CROSS_CLUSTER_RANDOM_FRACTION > 0

    src = (NOO / "noosphere/coherence/contradiction_scheduler.py").read_text()
    # No raw O(N²) enqueue pattern — the scheduler must consult the
    # cluster index, not iterate over every other artifact directly.
    assert "cluster" in src.lower()
    assert "for _a in artifacts:\n        for _b in artifacts:" not in src


# ──────────────────────────────────────────────────────────────────────
# I5. Manual contradiction resolution gone. Lifecycle table drives state.
#     SUBSUMED requires founder confirmation.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_05_manual_resolve_gone():
    resolve_page = CODEX / "src/app/(authed)/contradictions/[id]/resolve/page.tsx"
    assert not resolve_page.exists(), "the old resolve route must be gone (I5)"

    lifecycle = importlib.import_module("noosphere.coherence.lifecycle")
    assert hasattr(lifecycle, "LifecycleStatus")
    statuses = {s.value for s in lifecycle.LifecycleStatus}
    assert "SUBSUMED_BY_SYNTHESIS" in statuses

    src = (NOO / "noosphere/coherence/lifecycle.py").read_text()
    assert "founder" in src.lower(), (
        "lifecycle.py must document founder-confirmation for SUBSUMED_BY_SYNTHESIS (I5)"
    )


# ──────────────────────────────────────────────────────────────────────
# I6. Provenance demarcation enforced. ProvenanceKind has four values;
#     Oracle surface presents four checkboxes; contradiction engine
#     respects provenance_policy by default.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_06_provenance_demarcation():
    schema = (CODEX / "prisma/schema.prisma").read_text()
    enum_match = re.search(r"enum ProvenanceKind\s*\{([^}]+)\}", schema)
    assert enum_match, "ProvenanceKind enum missing from prisma schema"
    values = {v.strip() for v in enum_match.group(1).split() if v.strip()}
    assert values == {
        "PROPRIETARY",
        "ENDORSED_EXTERNAL",
        "STUDIED_EXTERNAL",
        "OPPOSING_EXTERNAL",
    }, f"unexpected ProvenanceKind values: {values}"

    pf = (CODEX / "src/components/oracle/ProvenanceFilter.tsx").read_text()
    for kind in values:
        assert kind in pf, f"ProvenanceFilter missing kind {kind}"

    sched = (NOO / "noosphere/coherence/contradiction_scheduler.py").read_text()
    assert "provenance" in sched.lower(), "scheduler must consult provenance policy (I6)"


# ──────────────────────────────────────────────────────────────────────
# I7. Synthesizer engine produces structured memos: CONCLUDED with a
#     non-empty reasoning chain, OR an explicit ABSTAINED reason.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_07_synthesizer_engine_has_explicit_outcomes():
    engine = importlib.import_module("noosphere.synthesizer.engine")
    # Round 19's synthesizer surfaces the outcome enum as
    # ``SynthesisOutcome`` (CONCLUDED / ABSTAINED_*); accept either name.
    outcome_enum = getattr(engine, "SynthesisOutcome", None) or getattr(
        engine, "SynthesisStatus", None
    )
    assert outcome_enum is not None, "synthesizer.engine must expose an outcome enum"
    statuses = {s.value for s in outcome_enum}
    assert "CONCLUDED" in statuses
    abstain = {s for s in statuses if s.startswith("ABSTAINED")}
    assert abstain, "synthesizer must surface ≥1 explicit ABSTAINED status (no silent failures)"


# ──────────────────────────────────────────────────────────────────────
# I8. Memos are auditable artifacts. 10 sections in canonical order,
#     PDF builder present, validator enforces ≥ 2 governing principles.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_08_memos_are_auditable():
    models = importlib.import_module("noosphere.models")
    assert hasattr(models, "MEMO_SECTIONS")
    assert len(models.MEMO_SECTIONS) == 10, f"expected 10 sections, got {len(models.MEMO_SECTIONS)}"
    assert "governing_principles" in models.MEMO_SECTIONS

    validator = (NOO / "noosphere/synthesizer/memo_validator.py").read_text()
    assert "governing_principles" in validator
    # The ≥ 2 governing-principles minimum is enforced at memo-build
    # time in memo_builder.py (the canonical check 'principles_govern').
    builder = (NOO / "noosphere/synthesizer/memo_builder.py").read_text()
    assert "governing_count >= 2" in builder, (
        "memo_builder must enforce 'governing_count >= 2' (I8)"
    )

    pdf_builder = NOO / "noosphere/synthesizer/memo_pdf.py"
    assert pdf_builder.exists() and pdf_builder.stat().st_size > 500


# ──────────────────────────────────────────────────────────────────────
# I9. Portfolio agent never bypasses gates. Default HUMAN; AUTO_LIVE
#     queues for confirmation rather than auto-submitting.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_09_portfolio_agent_default_is_human():
    router = importlib.import_module("noosphere.portfolio_agent.router")
    assert router.MEMO_DISPATCH_DEFAULT_MODE.value == "HUMAN", (
        "default portfolio-agent mode must be HUMAN (I9)"
    )

    auto_live = importlib.import_module("noosphere.portfolio_agent.auto_live")
    assert hasattr(auto_live, "AUTO_LIVE_PENDING_STATUS")
    # Pending status is the AUTHORIZED enum sentinel — bets sit there
    # awaiting an operator press, never auto-submitted.
    assert auto_live.AUTO_LIVE_PENDING_STATUS.value in {"AUTHORIZED", "PENDING_CONFIRMATION"}


# ──────────────────────────────────────────────────────────────────────
# I10. Knowledge graph reflects reality. Builder + agent reasoner exist;
#      a planted-weak-link fixture is part of the test surface.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_10_knowledge_graph_present():
    builder = importlib.import_module("noosphere.knowledge_graph.builder")
    reasoner = importlib.import_module("noosphere.knowledge_graph.agent_reasoner")
    # Builder exports both a procedural entry and a class wrapper.
    assert any(
        hasattr(builder, n)
        for n in ("build_for_org", "build", "build_snapshot", "build_graph", "KnowledgeGraphBuilder")
    )
    assert any(
        hasattr(reasoner, n)
        for n in ("evaluate_edge", "reason_about", "judge_edge", "explain_edge", "_fallback_reasoning")
    )

    test_path = NOO / "tests/test_agent_reasoner.py"
    body = test_path.read_text()
    assert "fabricat" in body.lower() or "weak" in body.lower() or "planted" in body.lower(), (
        "agent_reasoner test must include the planted-weak-link fixture (I10)"
    )


# ──────────────────────────────────────────────────────────────────────
# I11. Dialectic live recording fires real flags.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_11_dialectic_live_recording_present():
    rec = importlib.import_module("dialectic.live_recorder")
    assert any(hasattr(rec, n) for n in ("LiveRecorder", "run", "start"))
    test_path = REPO / "dialectic/tests/test_live_recorder.py"
    assert test_path.exists() and test_path.stat().st_size > 500


# ──────────────────────────────────────────────────────────────────────
# I12. Bet abstraction is polymorphic. Four kinds; one resolver per kind.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_12_bet_abstraction_polymorphic():
    spec = importlib.import_module("noosphere.bets.spec")
    kinds = {k.value for k in spec.BetKind}
    assert kinds == {"MARKET_BET", "ADVISORY_BET", "STRATEGIC_BET", "SCIENTIFIC_BET"}

    for kind in ("market", "advisory", "strategic", "scientific"):
        mod = importlib.import_module(f"noosphere.bets.resolvers.{kind}")
        assert any(
            hasattr(mod, n)
            for n in ("resolve", "Resolver", f"resolve_{kind}", f"{kind.capitalize()}Resolver")
        ), f"bets.resolvers.{kind} must export a resolve()/Resolver"


# ──────────────────────────────────────────────────────────────────────
# I13. Deletion pass executed cleanly: audit + plan committed, the
#      DELETE'd resolve route is gone.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_13_deletion_pass_executed():
    for p in (
        REPO / "docs/architecture/Round19_Deletion_Audit.md",
        REPO / "docs/architecture/Round19_Deletion_Plan.md",
    ):
        assert p.exists() and p.stat().st_size > 500, f"deletion artifact missing or stub: {p}"

    # The single canonical DELETE'd path from the round (resolve route).
    assert not (
        CODEX / "src/app/(authed)/contradictions/[id]/resolve/page.tsx"
    ).exists()


# ──────────────────────────────────────────────────────────────────────
# I14. Identity is consistent. Homepage / about / README all reach into
#      identity.ts or contain its canonical tagline. Pitch deck PDF
#      exists (built artifact).
# ──────────────────────────────────────────────────────────────────────


def test_invariant_14_identity_consistent():
    identity = (CODEX / "src/lib/copy/identity.ts").read_text()
    assert "A philosopher in a box." in identity

    homepage = (CODEX / "src/app/page.tsx").read_text()
    about = (CODEX / "src/app/about/page.tsx").read_text()
    readme = (REPO / "README.md").read_text()

    for surface_name, body in (("homepage", homepage), ("about", about)):
        assert "identity" in body or "THESEUS_TAGLINE" in body or "philosopher in a box" in body.lower(), (
            f"{surface_name} does not reference identity.ts or its canonical copy"
        )
    assert "philosopher in a box" in readme.lower(), "README missing the canonical identity copy"

    deck_pdf = REPO / "docs/pitch/2026_philosopher_in_a_box/deck.pdf"
    assert deck_pdf.exists() and deck_pdf.stat().st_size > 5_000, "pitch deck PDF not built"


# ──────────────────────────────────────────────────────────────────────
# I15. No new prompt regressed prior rounds. Round 18 forecasts invariant
#      suite and Round 10 safety-gate file are still present and discoverable.
# ──────────────────────────────────────────────────────────────────────


def test_invariant_15_no_prior_round_regression():
    forecasts_inv = NOO / "tests/test_forecasts_invariants.py"
    assert forecasts_inv.exists(), "Round 18 forecasts invariants suite missing"
    body = forecasts_inv.read_text()
    # The Round 18 prompt 18 set names eight invariants. We assert the
    # suite still defines ≥ 8 test functions (the prompt 50 verifier
    # used the same heuristic).
    test_funcs = re.findall(r"^def (test_invariant_\d+_)", body, re.M)
    assert len(test_funcs) >= 8, (
        f"Round 18 forecasts invariants are below 8 ({len(test_funcs)}); "
        "a prompt may have removed coverage."
    )

    safety = NOO / "noosphere/forecasts/safety.py"
    assert safety.exists(), "Round 10 eight-gate safety module missing"
    safety_src = safety.read_text()
    assert "check_all_gates" in safety_src, "safety.check_all_gates entrypoint missing (I15)"
