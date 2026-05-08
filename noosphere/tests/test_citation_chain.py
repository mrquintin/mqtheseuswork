"""
Tests for the citation-chain validator.

The NLI judge is mocked in every test — we keep CI hermetic and fast.
``FakeJudge`` returns a scripted probability triple per (premise,
hypothesis) pair so a test can assert that windowing, label derivation,
and triage escalation behave deterministically.

What we cover:

* Excerpt extraction — leading window when there is no span; centered
  window when a span is given; the persisted ``excerpt_used`` is
  exactly what the judge saw.
* Label derivation from NLI probabilities and the "beats its rival"
  rule.
* The mentions-clamp: a ``mentions`` cite cannot be promoted to
  ``entails`` even when NLI is confident.
* Publication gate vs. triage escalation: ``ambiguous`` is a finding
  but not a failure; only load-bearing cites escalate to triage.
* Founder override — once stamped, the verdict no longer blocks or
  triages.
* Recompute trigger — re-validating against an updated source text
  produces a new verdict row when the verdict flips.
* Ledger dedupe — re-running the validator with identical inputs and
  identical model is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import pytest

from noosphere.literature.citation_chain import (
    CitationCandidate,
    CitationRelation,
    CitationVerdict,
    DEFAULT_LOAD_BEARING_THRESHOLD,
    InMemoryCitationVerdictLedger,
    NLIJudgment,
    VerdictLabel,
    apply_override,
    blocks_publication,
    extract_excerpt,
    judge_citation,
    needs_triage,
    publication_blockers,
    revalidate_for_source,
    revalidate_on_standing_change,
    triage_payloads,
    validate_citations,
)


# ── fakes ──────────────────────────────────────────────────────────────


@dataclass
class FakeJudge:
    """Deterministic judge backed by a (premise, hypothesis) → probs map.

    Falls back to a configurable default triple when no exact key
    matches. The default itself is "ambiguous" so tests that don't
    register a hit can still exercise the ambiguous branch without
    extra setup.
    """

    scripted: dict[tuple[str, str], NLIJudgment] = field(default_factory=dict)
    default: NLIJudgment = NLIJudgment(
        entailment=0.34, neutral=0.33, contradiction=0.33, model_version="fake-nli-v1"
    )
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, premise: str, hypothesis: str) -> NLIJudgment:
        self.calls.append((premise, hypothesis))
        return self.scripted.get((premise, hypothesis), self.default)


def _candidate(
    *,
    citation_id: str = "cite-1",
    citation_kind: str = "opinion",
    source_id: str = "doi:10.0/test",
    stated_claim: str = "the firm's claim",
    source_text: str = "source text " * 10,
    relation: CitationRelation = CitationRelation.SUPPORTS,
    cascade_weight: float = 0.0,
    span_start: int | None = None,
    span_end: int | None = None,
) -> CitationCandidate:
    return CitationCandidate(
        citation_kind=citation_kind,
        citation_id=citation_id,
        source_id=source_id,
        stated_claim=stated_claim,
        source_text=source_text,
        relation=relation,
        cascade_weight=cascade_weight,
        span_start=span_start,
        span_end=span_end,
    )


# ── excerpt extraction ─────────────────────────────────────────────────


class TestExtractExcerpt:
    def test_leading_window_when_no_span(self) -> None:
        text = " ".join(f"w{i}" for i in range(500))
        out = extract_excerpt(text, window_words=10)
        assert out.split() == ["w0", "w1", "w2", "w3", "w4", "w5", "w6", "w7", "w8", "w9"]

    def test_centered_window_around_span(self) -> None:
        words = [f"w{i}" for i in range(200)]
        text = " ".join(words)
        # word w50 starts at offset sum(len(w_i) + 1 for i < 50)
        offset = sum(len(w) + 1 for w in words[:50])
        end = offset + len(words[50])
        out = extract_excerpt(text, span_start=offset, span_end=end, window_words=11)
        # cited word + ~5 words before + ~5 words after
        tokens = out.split()
        assert "w50" in tokens
        assert tokens[0].startswith("w") and int(tokens[0][1:]) < 50
        assert tokens[-1].startswith("w") and int(tokens[-1][1:]) > 50

    def test_empty_text_returns_empty(self) -> None:
        assert extract_excerpt("") == ""
        assert extract_excerpt("   \n   ") == ""

    def test_excerpt_persisted_verbatim(self) -> None:
        # The constraint: a verdict written using a 200-word excerpt
        # must record exactly that excerpt. The judge's premise must
        # equal the verdict's excerpt_used.
        judge = FakeJudge()
        cand = _candidate(source_text=" ".join(f"w{i}" for i in range(400)))
        verdict = judge_citation(cand, judge, window_words=200)
        assert verdict.excerpt_used == judge.calls[-1][0]
        # And the recorded length matches the budget we asked for.
        assert len(verdict.excerpt_used.split()) == 200


# ── label derivation ───────────────────────────────────────────────────


class TestLabelDerivation:
    def test_high_entailment_yields_entails(self) -> None:
        judge = FakeJudge()
        excerpt_text = "supportive " * 20  # 20 words
        cand = _candidate(source_text=excerpt_text, stated_claim="claim X")
        # The judge keys off (excerpt, claim). Compute the expected
        # excerpt the same way the validator will.
        expected_excerpt = extract_excerpt(excerpt_text, window_words=150)
        judge.scripted[(expected_excerpt, "claim X")] = NLIJudgment(
            entailment=0.9, neutral=0.05, contradiction=0.05, model_version="m"
        )
        v = judge_citation(cand, judge, window_words=150)
        assert v.relation_holds is VerdictLabel.ENTAILS
        assert v.confidence == pytest.approx(0.9)
        assert v.model_version == "m"

    def test_high_contradiction_yields_contradicts(self) -> None:
        judge = FakeJudge()
        cand = _candidate(source_text="raw text", stated_claim="claim Y")
        expected = extract_excerpt("raw text")
        judge.scripted[(expected, "claim Y")] = NLIJudgment(
            entailment=0.1, neutral=0.1, contradiction=0.8, model_version="m"
        )
        v = judge_citation(cand, judge)
        assert v.relation_holds is VerdictLabel.CONTRADICTS

    def test_below_threshold_yields_ambiguous(self) -> None:
        judge = FakeJudge()
        cand = _candidate(source_text="raw text", stated_claim="claim Z")
        expected = extract_excerpt("raw text")
        judge.scripted[(expected, "claim Z")] = NLIJudgment(
            entailment=0.4, neutral=0.4, contradiction=0.2, model_version="m"
        )
        v = judge_citation(cand, judge)
        assert v.relation_holds is VerdictLabel.AMBIGUOUS

    def test_neutral_strong_yields_neutral(self) -> None:
        judge = FakeJudge()
        cand = _candidate(source_text="raw text", stated_claim="claim N")
        expected = extract_excerpt("raw text")
        judge.scripted[(expected, "claim N")] = NLIJudgment(
            entailment=0.1, neutral=0.85, contradiction=0.05, model_version="m"
        )
        v = judge_citation(cand, judge)
        assert v.relation_holds is VerdictLabel.NEUTRAL


# ── mentions clamp ─────────────────────────────────────────────────────


class TestMentionsClamp:
    def test_mentions_entails_clamped_to_ambiguous(self) -> None:
        judge = FakeJudge()
        cand = _candidate(
            source_text="raw text",
            stated_claim="claim M",
            relation=CitationRelation.MENTIONS,
        )
        expected = extract_excerpt("raw text")
        judge.scripted[(expected, "claim M")] = NLIJudgment(
            entailment=0.9, neutral=0.05, contradiction=0.05, model_version="m"
        )
        v = judge_citation(cand, judge)
        # mentions can never be promoted to entails — clamps to ambiguous.
        assert v.relation_holds is VerdictLabel.AMBIGUOUS

    def test_mentions_contradicts_not_clamped(self) -> None:
        # The reverse direction is not clamped — a passing-reference
        # cite that the source actually contradicts is itself a finding.
        judge = FakeJudge()
        cand = _candidate(
            source_text="raw text",
            stated_claim="claim M2",
            relation=CitationRelation.MENTIONS,
        )
        expected = extract_excerpt("raw text")
        judge.scripted[(expected, "claim M2")] = NLIJudgment(
            entailment=0.05, neutral=0.05, contradiction=0.9, model_version="m"
        )
        v = judge_citation(cand, judge)
        assert v.relation_holds is VerdictLabel.CONTRADICTS


# ── publication gate ───────────────────────────────────────────────────


def _verdict(
    *,
    relation: CitationRelation,
    label: VerdictLabel,
    cascade_weight: float = 0.0,
    overridden_by: str | None = None,
    override_reason: str | None = None,
) -> CitationVerdict:
    return CitationVerdict(
        citation_kind="opinion",
        citation_id="c1",
        source_id="doi:10.0/x",
        relation=relation,
        relation_holds=label,
        confidence=0.8,
        excerpt_used="x",
        stated_claim="y",
        cascade_weight=cascade_weight,
        model_version="m",
        computed_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        overridden_by=overridden_by,
        override_reason=override_reason,
    )


class TestPublicationGate:
    def test_supports_contradicts_blocks(self) -> None:
        v = _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.CONTRADICTS)
        assert blocks_publication(v) is True

    def test_supports_neutral_blocks(self) -> None:
        v = _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.NEUTRAL)
        assert blocks_publication(v) is True

    def test_supports_ambiguous_does_not_block(self) -> None:
        # Ambiguous is a finding, not a failure.
        v = _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.AMBIGUOUS)
        assert blocks_publication(v) is False

    def test_supports_entails_does_not_block(self) -> None:
        v = _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.ENTAILS)
        assert blocks_publication(v) is False

    def test_non_supports_relations_never_block(self) -> None:
        for rel in (
            CitationRelation.CONTRADICTS,
            CitationRelation.QUALIFIES,
            CitationRelation.MENTIONS,
        ):
            v = _verdict(relation=rel, label=VerdictLabel.CONTRADICTS)
            assert blocks_publication(v) is False

    def test_override_clears_block(self) -> None:
        v = _verdict(
            relation=CitationRelation.SUPPORTS,
            label=VerdictLabel.CONTRADICTS,
            overridden_by="founder-1",
            override_reason="paraphrase looks fine on closer read",
        )
        assert blocks_publication(v) is False

    def test_publication_blockers_filters(self) -> None:
        verdicts = [
            _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.ENTAILS),
            _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.CONTRADICTS),
            _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.NEUTRAL),
        ]
        assert len(publication_blockers(verdicts)) == 2


# ── triage escalation ──────────────────────────────────────────────────


class TestTriageEscalation:
    def test_blocking_verdict_triages(self) -> None:
        v = _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.CONTRADICTS)
        assert needs_triage(v) is True

    def test_ambiguous_below_threshold_does_not_triage(self) -> None:
        v = _verdict(
            relation=CitationRelation.SUPPORTS,
            label=VerdictLabel.AMBIGUOUS,
            cascade_weight=DEFAULT_LOAD_BEARING_THRESHOLD - 0.01,
        )
        assert needs_triage(v) is False

    def test_ambiguous_at_threshold_triages(self) -> None:
        v = _verdict(
            relation=CitationRelation.SUPPORTS,
            label=VerdictLabel.AMBIGUOUS,
            cascade_weight=DEFAULT_LOAD_BEARING_THRESHOLD,
        )
        assert needs_triage(v) is True

    def test_override_suppresses_triage(self) -> None:
        v = _verdict(
            relation=CitationRelation.SUPPORTS,
            label=VerdictLabel.AMBIGUOUS,
            cascade_weight=0.9,
            overridden_by="founder-1",
            override_reason="manual review confirmed support",
        )
        assert needs_triage(v) is False

    def test_payloads_carry_excerpt_and_claim(self) -> None:
        v = _verdict(
            relation=CitationRelation.SUPPORTS,
            label=VerdictLabel.CONTRADICTS,
        )
        payloads = triage_payloads([v])
        assert len(payloads) == 1
        p = payloads[0]
        assert p.excerpt == "x"
        assert p.stated_claim == "y"
        assert p.label is VerdictLabel.CONTRADICTS
        assert "contradicts" in p.reason


# ── overrides ──────────────────────────────────────────────────────────


class TestOverride:
    def test_apply_override_stamps_metadata(self) -> None:
        v = _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.CONTRADICTS)
        out = apply_override(v, overridden_by="founder-1", override_reason="ok")
        assert out.overridden_by == "founder-1"
        assert out.override_reason == "ok"
        assert blocks_publication(out) is False

    def test_empty_reason_rejected(self) -> None:
        v = _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.CONTRADICTS)
        with pytest.raises(ValueError):
            apply_override(v, overridden_by="x", override_reason="   ")

    def test_empty_overrider_rejected(self) -> None:
        v = _verdict(relation=CitationRelation.SUPPORTS, label=VerdictLabel.CONTRADICTS)
        with pytest.raises(ValueError):
            apply_override(v, overridden_by="", override_reason="ok")


# ── ledger / recompute ─────────────────────────────────────────────────


class TestValidateAndRecompute:
    def test_validate_persists_one_row_per_candidate(self) -> None:
        judge = FakeJudge()
        ledger = InMemoryCitationVerdictLedger()
        candidates = [
            _candidate(citation_id="c1", source_text="alpha"),
            _candidate(citation_id="c2", source_text="beta"),
        ]
        out = validate_citations(candidates, judge, ledger)
        assert len(out) == 2
        assert len(ledger.all()) == 2
        assert {v.citation_id for v in ledger.all()} == {"c1", "c2"}

    def test_dedup_on_identical_rerun(self) -> None:
        judge = FakeJudge()
        ledger = InMemoryCitationVerdictLedger()
        cand = _candidate(citation_id="c1", source_text="alpha")
        validate_citations([cand], judge, ledger)
        validate_citations([cand], judge, ledger)
        # Second run dedupes — same excerpt, same model, same label.
        assert len(ledger.all()) == 1

    def test_recompute_for_source_only_touches_matching_candidates(self) -> None:
        judge = FakeJudge()
        ledger = InMemoryCitationVerdictLedger()
        a = _candidate(
            citation_id="c1", source_id="doi:10.0/a", source_text="alpha"
        )
        b = _candidate(
            citation_id="c2", source_id="doi:10.0/b", source_text="beta"
        )
        out = revalidate_for_source("doi:10.0/a", [a, b], judge, ledger)
        assert len(out) == 1
        assert out[0].source_id == "doi:10.0/a"

    def test_recompute_after_text_update_produces_new_row_when_label_flips(
        self,
    ) -> None:
        judge = FakeJudge()
        ledger = InMemoryCitationVerdictLedger()

        # Initial source text — judge says contradicts.
        cand_v1 = _candidate(
            citation_id="c1",
            source_id="doi:10.0/x",
            source_text="initial text",
            stated_claim="claim",
        )
        excerpt_v1 = extract_excerpt(cand_v1.source_text)
        judge.scripted[(excerpt_v1, "claim")] = NLIJudgment(
            entailment=0.1, neutral=0.1, contradiction=0.8, model_version="m"
        )
        validate_citations([cand_v1], judge, ledger)
        assert (
            ledger.latest_for("opinion", "c1").relation_holds
            is VerdictLabel.CONTRADICTS
        )

        # Source-text update — same citation row, new body. The judge
        # says entails on the new excerpt. Recompute path should write
        # a new verdict.
        cand_v2 = _candidate(
            citation_id="c1",
            source_id="doi:10.0/x",
            source_text="updated text after correction",
            stated_claim="claim",
        )
        excerpt_v2 = extract_excerpt(cand_v2.source_text)
        judge.scripted[(excerpt_v2, "claim")] = NLIJudgment(
            entailment=0.9, neutral=0.05, contradiction=0.05, model_version="m"
        )
        revalidate_for_source("doi:10.0/x", [cand_v2], judge, ledger)
        latest = ledger.latest_for("opinion", "c1")
        assert latest.relation_holds is VerdictLabel.ENTAILS
        assert latest.excerpt_used == excerpt_v2
        # Two rows now: the old contradicts and the new entails.
        history = [v for v in ledger.all() if v.citation_id == "c1"]
        assert len(history) == 2

    def test_recompute_on_standing_change_uses_lookup(self) -> None:
        judge = FakeJudge()
        ledger = InMemoryCitationVerdictLedger()
        candidates_by_source = {
            "doi:10.0/a": [
                _candidate(citation_id="c1", source_id="doi:10.0/a", source_text="a"),
                _candidate(citation_id="c2", source_id="doi:10.0/a", source_text="a"),
            ],
            "doi:10.0/b": [
                _candidate(citation_id="c3", source_id="doi:10.0/b", source_text="b"),
            ],
        }

        def lookup(sid: str) -> Iterable[CitationCandidate]:
            return candidates_by_source.get(sid, [])

        # A retraction affects only doi:10.0/a — recompute hits its
        # two cites and leaves doi:10.0/b alone.
        out = revalidate_on_standing_change(
            ["doi:10.0/a"], lookup, judge, ledger
        )
        assert {v.citation_id for v in out} == {"c1", "c2"}
        assert ledger.latest_for("opinion", "c3") is None

    def test_for_source_returns_one_row_per_citation(self) -> None:
        judge = FakeJudge()
        ledger = InMemoryCitationVerdictLedger()
        cand = _candidate(citation_id="c1", source_id="doi:10.0/x")
        validate_citations([cand], judge, ledger)
        # Force a second row via a label flip.
        judge.scripted[(extract_excerpt(cand.source_text), cand.stated_claim)] = (
            NLIJudgment(entailment=0.9, neutral=0.05, contradiction=0.05, model_version="m")
        )
        validate_citations([cand], judge, ledger)
        rows = ledger.for_source("doi:10.0/x")
        # Latest-only view: one row per (kind, id).
        assert len(rows) == 1
        assert rows[0].relation_holds is VerdictLabel.ENTAILS
