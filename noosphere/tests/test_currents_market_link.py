"""Tests for Currents <-> Forecast market linkage.

Covers:
- NLI matcher entails / does-not-entail / contradiction veto;
- low-liquidity flag;
- edge calculation for AGREES and DISAGREES;
- public-side restraint contract: edge data never appears in the
  ``PublicOpinion`` shape served to public consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from noosphere.currents.market_linker import (
    DEFAULT_LIQUIDITY_FLOOR_USD,
    NLIScore,
    link_opinion_to_markets,
)
from noosphere.forecasts.edge_calc import (
    compute_edge,
    edge_report_to_wire,
    firm_yes_probability,
)
from noosphere.forecasts.paper_bet_engine import PaperBetConfig
from noosphere.models import (
    EventOpinion,
    ForecastMarket,
    ForecastMarketStatus,
    ForecastSource,
    OpinionStance,
)


@dataclass
class FakeScorer:
    """Lookup-table scorer keyed by (premise_excerpt, hypothesis_excerpt)."""

    table: dict[tuple[str, str], NLIScore]
    default: NLIScore = NLIScore(entailment=0.05, contradiction=0.05)

    def __call__(self, premise: str, hypothesis: str) -> NLIScore:
        for (p, h), score in self.table.items():
            if p in premise and h in hypothesis:
                return score
        return self.default


def _opinion(
    *,
    stance: OpinionStance = OpinionStance.AGREES,
    confidence: float = 0.85,
    headline: str = "China will not invade Taiwan in 2026",
    body: str = "The firm assigns low probability to a 2026 invasion.",
) -> EventOpinion:
    return EventOpinion(
        organization_id="org-1",
        event_id="evt-1",
        stance=stance,
        confidence=confidence,
        headline=headline,
        body_markdown=body,
        uncertainty_notes=[],
        topic_hint="geopolitics",
        model_name="claude-haiku-test",
    )


def _market(
    *,
    title: str,
    yes_price: float = 0.6,
    volume: float = 25_000.0,
    status: ForecastMarketStatus = ForecastMarketStatus.OPEN,
    raw_payload: dict | None = None,
    source: ForecastSource = ForecastSource.POLYMARKET,
    market_id: str | None = None,
    external_id: str = "ext-1",
    resolution_criteria: str | None = "Resolves YES if China invades Taiwan in 2026.",
) -> ForecastMarket:
    return ForecastMarket(
        id=market_id or f"mkt-{external_id}",
        organization_id="org-1",
        source=source,
        external_id=external_id,
        title=title,
        resolution_criteria=resolution_criteria,
        current_yes_price=Decimal(str(yes_price)),
        current_no_price=Decimal(str(1.0 - yes_price)),
        volume=Decimal(str(volume)),
        status=status,
        raw_payload=raw_payload or {},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Matcher
# ─────────────────────────────────────────────────────────────────────────────


def test_matcher_returns_only_nli_entailing_markets() -> None:
    opinion = _opinion()
    matching = _market(
        title="Will China invade Taiwan by end of 2026?",
        yes_price=0.18,
        external_id="poly-taiwan",
    )
    superficial = _market(
        title="Will China overtake the US in chip exports in 2026?",
        yes_price=0.42,
        external_id="poly-chips",
        resolution_criteria="Resolves YES if China is the top chip exporter.",
    )

    scorer = FakeScorer(
        table={
            ("China will not invade Taiwan", "China invade Taiwan"): NLIScore(
                entailment=0.86, contradiction=0.04
            ),
            ("China invade Taiwan", "China will not invade Taiwan"): NLIScore(
                entailment=0.78, contradiction=0.05
            ),
            ("China will not invade Taiwan", "chip exports"): NLIScore(
                entailment=0.10, contradiction=0.04
            ),
            ("chip exports", "China will not invade Taiwan"): NLIScore(
                entailment=0.08, contradiction=0.04
            ),
        }
    )

    matches = link_opinion_to_markets(opinion, [matching, superficial], scorer=scorer)

    assert [m.market_id for m in matches] == ["mkt-poly-taiwan"]
    only = matches[0]
    assert only.market_yes_price == pytest.approx(0.18)
    assert only.entailment_forward >= 0.7
    assert only.low_liquidity is False


def test_matcher_rejects_when_contradiction_dominates() -> None:
    opinion = _opinion()
    market = _market(
        title="Will China invade Taiwan by end of 2026?",
        external_id="poly-contradicts",
    )
    scorer = FakeScorer(
        table={
            ("China will not invade Taiwan", "China invade Taiwan"): NLIScore(
                entailment=0.72, contradiction=0.65
            ),
            ("China invade Taiwan", "China will not invade Taiwan"): NLIScore(
                entailment=0.30, contradiction=0.65
            ),
        }
    )
    assert link_opinion_to_markets(opinion, [market], scorer=scorer) == []


def test_matcher_skips_complicates_and_abstained() -> None:
    market = _market(
        title="Will China invade Taiwan by end of 2026?",
        external_id="poly-skip",
    )
    scorer = FakeScorer(
        table={("", ""): NLIScore(entailment=0.99, contradiction=0.0)}
    )
    for stance in (OpinionStance.COMPLICATES, OpinionStance.ABSTAINED):
        opinion = _opinion(stance=stance)
        assert link_opinion_to_markets(opinion, [market], scorer=scorer) == []


def test_matcher_flags_low_liquidity_markets() -> None:
    opinion = _opinion()
    thin_market = _market(
        title="Will China invade Taiwan by end of 2026?",
        external_id="poly-thin",
        volume=DEFAULT_LIQUIDITY_FLOOR_USD / 10,
    )
    scorer = FakeScorer(
        table={
            ("China will not invade Taiwan", "China invade Taiwan"): NLIScore(
                entailment=0.86, contradiction=0.04
            ),
            ("China invade Taiwan", "China will not invade Taiwan"): NLIScore(
                entailment=0.78, contradiction=0.05
            ),
        }
    )
    matches = link_opinion_to_markets(opinion, [thin_market], scorer=scorer)
    assert len(matches) == 1
    assert matches[0].low_liquidity is True


# ─────────────────────────────────────────────────────────────────────────────
# Edge calculator
# ─────────────────────────────────────────────────────────────────────────────


def test_firm_probability_maps_stance_to_yes_prob() -> None:
    assert firm_yes_probability(_opinion(stance=OpinionStance.AGREES, confidence=0.9)) == pytest.approx(0.9)
    assert firm_yes_probability(_opinion(stance=OpinionStance.DISAGREES, confidence=0.9)) == pytest.approx(0.1)
    assert firm_yes_probability(_opinion(stance=OpinionStance.COMPLICATES)) is None
    assert firm_yes_probability(_opinion(stance=OpinionStance.ABSTAINED)) is None


def test_edge_surfaces_when_gap_exceeds_threshold() -> None:
    opinion = _opinion(stance=OpinionStance.AGREES, confidence=0.85)
    market = _market(
        title="Will the firm's claim resolve YES?",
        yes_price=0.45,
        external_id="poly-edge",
    )
    scorer = FakeScorer(
        table={
            ("China will not invade Taiwan", "firm's claim resolve YES"): NLIScore(
                entailment=0.83, contradiction=0.05
            ),
            ("firm's claim resolve YES", "China will not invade Taiwan"): NLIScore(
                entailment=0.81, contradiction=0.05
            ),
        }
    )
    [match] = link_opinion_to_markets(opinion, [market], scorer=scorer)

    config = PaperBetConfig(edge_threshold=0.1, kelly_fraction=0.25, max_stake_usd=50.0, initial_balance_usd=10_000.0)
    report = compute_edge(opinion, match, config=config, paper_balance_usd=10_000.0)

    assert report is not None
    assert report.firm_yes_probability == pytest.approx(0.85)
    assert report.market_yes_price == pytest.approx(0.45)
    assert report.edge_pts == pytest.approx(40.0)
    assert report.side == "YES"
    assert report.surface is True
    assert report.suggested_stake_usd is not None and report.suggested_stake_usd > 0


def test_edge_below_threshold_is_logged_not_surfaced() -> None:
    opinion = _opinion(stance=OpinionStance.AGREES, confidence=0.55)
    market = _market(
        title="Will the firm's claim resolve YES?",
        yes_price=0.52,
        external_id="poly-noedge",
    )
    scorer = FakeScorer(
        table={
            ("China will not invade Taiwan", "firm's claim resolve YES"): NLIScore(
                entailment=0.83, contradiction=0.05
            ),
            ("firm's claim resolve YES", "China will not invade Taiwan"): NLIScore(
                entailment=0.81, contradiction=0.05
            ),
        }
    )
    [match] = link_opinion_to_markets(opinion, [market], scorer=scorer)
    config = PaperBetConfig(edge_threshold=0.1)
    report = compute_edge(opinion, match, config=config)
    assert report is not None
    assert report.surface is False


def test_edge_low_liquidity_suppresses_position_size() -> None:
    opinion = _opinion(stance=OpinionStance.AGREES, confidence=0.85)
    thin = _market(
        title="Will the firm's claim resolve YES?",
        yes_price=0.45,
        external_id="poly-thin-edge",
        volume=10.0,
    )
    scorer = FakeScorer(
        table={
            ("China will not invade Taiwan", "firm's claim resolve YES"): NLIScore(
                entailment=0.83, contradiction=0.05
            ),
            ("firm's claim resolve YES", "China will not invade Taiwan"): NLIScore(
                entailment=0.81, contradiction=0.05
            ),
        }
    )
    [match] = link_opinion_to_markets(opinion, [thin], scorer=scorer)
    assert match.low_liquidity is True
    report = compute_edge(opinion, match, paper_balance_usd=10_000.0)
    assert report is not None
    assert report.surface is True
    assert report.low_liquidity is True
    assert report.suggested_stake_usd is None


def test_disagrees_flips_side_and_size() -> None:
    opinion = _opinion(stance=OpinionStance.DISAGREES, confidence=0.8)
    market = _market(
        title="Will the firm's claim resolve YES?",
        yes_price=0.6,
        external_id="poly-disagrees",
    )
    scorer = FakeScorer(
        table={
            ("China will not invade Taiwan", "firm's claim resolve YES"): NLIScore(
                entailment=0.83, contradiction=0.05
            ),
            ("firm's claim resolve YES", "China will not invade Taiwan"): NLIScore(
                entailment=0.81, contradiction=0.05
            ),
        }
    )
    [match] = link_opinion_to_markets(opinion, [market], scorer=scorer)
    report = compute_edge(opinion, match, paper_balance_usd=10_000.0)
    assert report is not None
    assert report.firm_yes_probability == pytest.approx(0.2)
    assert report.side == "NO"
    assert report.edge_pts == pytest.approx(-40.0)
    assert report.surface is True


# ─────────────────────────────────────────────────────────────────────────────
# Public-side restraint contract
# ─────────────────────────────────────────────────────────────────────────────


def test_event_opinion_row_does_not_carry_edge_fields() -> None:
    """Edge linkage must never be persisted on the EventOpinion row.

    Edge data is firm-internal signal computed on demand for the founder
    portal. Persisting it on the row would make it trivial to leak into the
    public Currents serializer (which currently mirrors row fields one-to-one).
    """
    forbidden = {
        "edge_pts",
        "edge",
        "marketYesPrice",
        "firmYesProbability",
        "suggestedStakeUsd",
        "marketId",
        "marketUrl",
    }
    columns = {column.name for column in EventOpinion.__table__.columns}
    leaked = forbidden & columns
    assert not leaked, (
        "EventOpinion table must not carry edge linkage columns: " + ", ".join(sorted(leaked))
    )


def test_public_currents_types_do_not_declare_edge_fields() -> None:
    """The TypeScript ``PublicOpinion`` shape served to ``/currents`` must not
    declare edge-linkage fields. Pinned by parsing the canonical type file."""
    from pathlib import Path

    types_path = (
        Path(__file__).resolve().parents[2]
        / "theseus-codex"
        / "src"
        / "lib"
        / "currentsTypes.ts"
    )
    contents = types_path.read_text(encoding="utf-8")
    public_block_start = contents.index("export interface PublicOpinion ")
    public_block_end = contents.index("}", public_block_start)
    public_block = contents[public_block_start:public_block_end]
    for forbidden in ("edge_pts", "market_yes_price", "firm_yes_probability", "suggested_stake_usd"):
        assert forbidden not in public_block, (
            f"Public Currents type must not declare {forbidden!r}; "
            "edge linkage is founder-internal."
        )


def test_edge_wire_payload_is_founder_internal_only() -> None:
    """Defensive: the wire dict produced for the founder UI carries the
    sensitive fields explicitly. If a future contributor wants to render this
    on the public side they will hit ``test_public_opinion_payload_does_not_
    carry_edge_fields`` first.
    """
    opinion = _opinion()
    match = _market(
        title="Will the firm's claim resolve YES?",
        yes_price=0.45,
        external_id="poly-wire",
    )
    scorer = FakeScorer(
        table={
            ("China will not invade Taiwan", "firm's claim resolve YES"): NLIScore(
                entailment=0.83, contradiction=0.05
            ),
            ("firm's claim resolve YES", "China will not invade Taiwan"): NLIScore(
                entailment=0.81, contradiction=0.05
            ),
        }
    )
    [matched] = link_opinion_to_markets(opinion, [match], scorer=scorer)
    report = compute_edge(opinion, matched, paper_balance_usd=10_000.0)
    assert report is not None
    wire = edge_report_to_wire(report)
    assert {"firm_yes_probability", "market_yes_price", "edge_pts"} <= wire.keys()
