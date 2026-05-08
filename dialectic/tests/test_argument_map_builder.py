"""Tests for the live argument-map builder.

These run headlessly — no Qt, no LLM, no network — by relying on the
heuristic fallbacks (or injecting deterministic stubs).
"""

from __future__ import annotations

import time
import threading
from pathlib import Path

import pytest

from dialectic.argument_map_builder import (
    ArgumentMapBuilder,
    BuilderConfig,
    BuilderEvent,
    Utterance,
    cosine,
    heuristic_embed,
    heuristic_extract_claims,
    heuristic_nli,
    RELATION_ASKS_ABOUT,
    RELATION_CONTRADICTS,
    RELATION_REFINES,
    RELATION_SUPPORTS,
)
from dialectic.exports.argument_map_export import (
    export_json,
    export_markdown,
    export_svg,
    write_session_exports,
)


# ── helpers ────────────────────────────────────────────────────────────


def _stable_embed(text: str) -> list[float]:
    """Deterministic, paraphrase-tolerant embedder for tests.

    Bag-of-words over content tokens. Two utterances that share most
    content words will score above the dedup threshold.
    """

    return heuristic_embed(text, dim=64)


def _make_builder(**overrides) -> ArgumentMapBuilder:
    base = dict(
        dedup_similarity=0.80,
        nli_supports_threshold=0.45,
        nli_contradicts_threshold=0.45,
        nli_refines_overlap=0.30,
        drift_window=4,
        drift_threshold=0.50,
        unresolved_K_turns=2,
        queue_maxsize=16,
        pulse_seconds=0.01,
    )
    base.update(overrides)
    cfg = BuilderConfig(**base)
    return ArgumentMapBuilder(
        config=cfg,
        extractor=heuristic_extract_claims,
        embedder=_stable_embed,
        nli=heuristic_nli,
    )


# ── identity / dedup ──────────────────────────────────────────────────


def test_repeated_claim_hits_same_node():
    builder = _make_builder()
    builder.process_now(
        Utterance(text="Caffeine improves short-term memory.", speaker="A")
    )
    builder.process_now(
        Utterance(text="Caffeine improves short-term memory.", speaker="B")
    )
    nodes = builder.nodes()
    assert len(nodes) == 1
    assert nodes[0].seen_count == 2


def test_paraphrase_dedupes_via_embedding():
    builder = _make_builder(dedup_similarity=0.70)
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    builder.process_now(Utterance(text="Coffee improves focus a lot.", speaker="B"))
    nodes = builder.nodes()
    # Same-content paraphrase should hit the existing node, not split.
    assert len(nodes) == 1, [n.text for n in nodes]


def test_distinct_claims_make_distinct_nodes():
    builder = _make_builder()
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    builder.process_now(
        Utterance(text="Photosynthesis releases oxygen.", speaker="A")
    )
    assert len(builder.nodes()) == 2


# ── relations ──────────────────────────────────────────────────────────


def test_question_links_via_asks_about():
    builder = _make_builder()
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    builder.process_now(Utterance(text="Does coffee improve focus?", speaker="B"))
    edges = builder.edges()
    asks = [e for e in edges if e.relation == RELATION_ASKS_ABOUT]
    assert asks, "expected an asks_about edge from question to prior claim"


def test_contradiction_relation():
    builder = _make_builder()
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    builder.process_now(
        Utterance(text="Coffee does not improve focus.", speaker="B")
    )
    rels = {e.relation for e in builder.edges()}
    assert RELATION_CONTRADICTS in rels


def test_supports_when_overlap_no_negation():
    """Two non-negated, overlapping claims should connect via supports
    or refines — both signal alignment, not contradiction."""

    # Use a higher dedup threshold so close paraphrases stay separate.
    builder = _make_builder(dedup_similarity=0.95)
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    builder.process_now(
        Utterance(
            text="Coffee improves focus by elevating dopamine signalling.",
            speaker="A",
        )
    )
    rels = {e.relation for e in builder.edges()}
    assert rels & {RELATION_SUPPORTS, RELATION_REFINES}


# ── unresolved questions ───────────────────────────────────────────────


def test_question_goes_amber_after_K_turns_then_red():
    builder = _make_builder()
    builder.process_now(Utterance(text="Why does coffee help?", speaker="A"))
    # K=2 → after 2 turns of unrelated content the question goes amber.
    builder.process_now(Utterance(text="Sodium is an element.", speaker="B"))
    builder.process_now(Utterance(text="Iron rusts in air.", speaker="B"))
    qs = [n for n in builder.nodes() if n.is_question]
    assert qs and qs[0].state == "amber"
    # Two more unrelated turns → 2K total → red.
    builder.process_now(Utterance(text="Plants use chlorophyll.", speaker="B"))
    builder.process_now(Utterance(text="Birds have feathers.", speaker="B"))
    qs = [n for n in builder.nodes() if n.is_question]
    assert qs[0].state == "red"


def test_answered_question_does_not_go_amber():
    builder = _make_builder()
    builder.process_now(Utterance(text="Does coffee improve focus?", speaker="A"))
    # An answering claim with strong overlap → supports edge, marks answered.
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="B"))
    qs = [n for n in builder.nodes() if n.is_question]
    assert qs and qs[0].state == "answered"


# ── drift indicator ────────────────────────────────────────────────────


def test_drift_flags_topic_shift():
    builder = _make_builder(drift_threshold=0.30, drift_window=3)
    on_topic = [
        "Coffee improves focus.",
        "Caffeine boosts attention.",
        "Espresso has more caffeine.",
        "Coffee beans are roasted.",
    ]
    for t in on_topic:
        builder.process_now(Utterance(text=t, speaker="A"))
    # Now jump topics:
    builder.process_now(
        Utterance(text="Mitochondria produce ATP in cells.", speaker="A")
    )
    drift = builder.drift_readings()
    assert any(d.flagged for d in drift), [d.drift for d in drift]


# ── threading / back-pressure ──────────────────────────────────────────


def test_builder_thread_does_not_lose_utterances_under_normal_load():
    builder = _make_builder(queue_maxsize=64)
    builder.start()
    try:
        for i in range(10):
            ok = builder.submit(
                Utterance(text=f"Claim number {i} about reasoning.", speaker="A")
            )
            assert ok
        # Wait for the worker to drain.
        deadline = time.time() + 3.0
        while time.time() < deadline and len(builder.utterances()) < 10:
            time.sleep(0.05)
    finally:
        builder.stop()
    assert len(builder.utterances()) == 10


def test_backpressure_drops_oldest_when_queue_full():
    """Submit must never block — the live transcribe loop is the priority."""

    builder = _make_builder(queue_maxsize=2)
    # Don't start the worker; the queue stays full on purpose.
    accepted = []
    for i in range(6):
        accepted.append(
            builder.submit(Utterance(text=f"Claim {i}", speaker="A"))
        )
    # Every submit succeeds even though the queue overflows — the
    # builder drops the oldest pending item rather than rejecting new
    # input.
    assert all(accepted)


# ── exports ───────────────────────────────────────────────────────────


def test_markdown_export_has_frontmatter_and_claims():
    builder = _make_builder()
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    builder.process_now(Utterance(text="Why does coffee improve focus?", speaker="B"))
    md = export_markdown(builder, session_id="sess-1", title="Coffee debate")
    assert md.startswith("---")
    assert "kind: argument_map" in md
    assert "Coffee improves focus." in md
    assert "## Claims" in md


def test_json_export_round_trips():
    builder = _make_builder()
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    j = export_json(builder, session_id="sess-1")
    assert j["kind"] == "argument_map"
    assert j["session_id"] == "sess-1"
    assert any(n["text"] == "Coffee improves focus." for n in j["nodes"])


def test_svg_export_is_well_formed():
    builder = _make_builder()
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    builder.process_now(Utterance(text="Coffee does not improve focus.", speaker="B"))
    svg = export_svg(builder)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "<line" in svg
    assert "<circle" in svg


def test_write_session_exports_creates_all_files(tmp_path: Path):
    builder = _make_builder()
    builder.process_now(Utterance(text="Coffee improves focus.", speaker="A"))
    paths = write_session_exports(
        builder, tmp_path, session_id="sess", title="t"
    )
    for kind in ("json", "svg", "markdown", "transcript"):
        assert paths[kind].exists(), kind
    text = paths["markdown"].read_text(encoding="utf-8")
    assert "kind: argument_map" in text


# ── tiny utility coverage ──────────────────────────────────────────────


def test_cosine_basic():
    a = [1.0, 0.0]
    b = [1.0, 0.0]
    assert cosine(a, b) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_config_defaults_round_trip():
    cfg = BuilderConfig()
    assert cfg.dedup_similarity > 0
    assert cfg.unresolved_K_turns >= 1
