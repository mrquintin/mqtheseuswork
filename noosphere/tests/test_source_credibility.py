"""
Tests for the source-credibility ledger.

Coverage:
    * priors are well-formed and the firm's own outputs start neutral
    * weighted Beta updates move the posterior in the expected
      direction at the expected rate, and never escape [0, 1]
    * cascade weight modulation respects the "no manufacturing strong
      evidence from many weak sources" property
    * the in-memory ledger is idempotent on repeat applications
    * the display threshold prevents confident rendering from a thin
      track record
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noosphere.cascade.graph import CascadeGraph
from noosphere.literature.source_credibility import (
    BetaPosterior,
    CredibilityEventKind,
    CredibilityOutcome,
    CredibilityUpdate,
    InMemoryCredibilityLedger,
    aggregate_supports_confidence,
    apply_updates,
    current_credibility,
    display_payload,
    modulated_supports_confidence,
)
from noosphere.literature.source_priors import (
    MIN_UPDATES_FOR_CONFIDENT_DISPLAY,
    SourcePrior,
    SourceType,
    all_priors,
    is_firm_source,
    prior_for,
)


# ── prior table ─────────────────────────────────────────────────────────


class TestSourcePriors:
    def test_every_type_has_a_prior(self) -> None:
        priors = all_priors()
        for st in SourceType:
            assert st in priors, f"missing prior for {st}"

    def test_priors_have_valid_beta_parameters(self) -> None:
        for prior in all_priors().values():
            assert 0.0 < prior.prior_credibility < 1.0
            assert prior.prior_strength > 0.0
            assert prior.alpha > 0.0
            assert prior.beta > 0.0

    def test_firm_outputs_start_neutral(self) -> None:
        # Constraint from the prompt: the firm's own outputs do not
        # carry a self-flattering head start — they earn credibility
        # through the same loop as everyone else.
        for st in (SourceType.FIRM_PODCAST, SourceType.FIRM_CONCLUSION):
            p = prior_for(st)
            assert p.prior_credibility == pytest.approx(0.5), (
                f"{st} prior is not neutral: {p.prior_credibility}"
            )
            assert is_firm_source(st)

    def test_peer_review_above_preprint_above_blog(self) -> None:
        # Sanity check on the relative ordering — if these flip the
        # priors are probably mis-edited.
        peer = prior_for(SourceType.PEER_REVIEWED_PAPER).prior_credibility
        preprint = prior_for(SourceType.PREPRINT).prior_credibility
        blog = prior_for(SourceType.BLOG_SELF_PUB).prior_credibility
        tabloid = prior_for(SourceType.NEWS_TABLOID).prior_credibility
        assert peer > preprint > blog
        assert peer > tabloid

    def test_unknown_falls_through(self) -> None:
        assert prior_for("not-a-real-type").source_type == SourceType.UNKNOWN
        assert prior_for(None).source_type == SourceType.UNKNOWN

    def test_constructor_validates(self) -> None:
        with pytest.raises(ValueError):
            SourcePrior(
                source_type=SourceType.UNKNOWN,
                prior_credibility=1.5,
                prior_strength=1.0,
                rationale="bad",
            )
        with pytest.raises(ValueError):
            SourcePrior(
                source_type=SourceType.UNKNOWN,
                prior_credibility=0.5,
                prior_strength=0.0,
                rationale="bad",
            )


# ── update helpers ──────────────────────────────────────────────────────


def _u(
    *,
    sid: str = "doi:10.1/x",
    outcome: CredibilityOutcome = CredibilityOutcome.CONFIRMATION,
    weight: float = 1.0,
    kind: CredibilityEventKind = CredibilityEventKind.FORECAST_RESOLUTION,
    cid: str = "concl-1",
    when: datetime | None = None,
) -> CredibilityUpdate:
    return CredibilityUpdate(
        source_id=sid,
        outcome=outcome,
        weight=weight,
        kind=kind,
        conclusion_id=cid,
        observed_at=when or datetime.now(timezone.utc),
    )


# ── posterior maths ─────────────────────────────────────────────────────


class TestApplyUpdates:
    def test_no_updates_returns_prior(self) -> None:
        post = apply_updates(
            source_id="src",
            source_type=SourceType.PEER_REVIEWED_PAPER,
            updates=[],
        )
        prior = prior_for(SourceType.PEER_REVIEWED_PAPER)
        assert post.alpha == pytest.approx(prior.alpha)
        assert post.beta == pytest.approx(prior.beta)
        assert post.mean == pytest.approx(prior.prior_credibility)
        assert post.n_updates == 0

    def test_confirmations_push_credibility_up(self) -> None:
        prior = prior_for(SourceType.PREPRINT)
        post = apply_updates(
            source_id="s",
            source_type=SourceType.PREPRINT,
            updates=[_u(sid="s") for _ in range(8)],
        )
        assert post.mean > prior.prior_credibility
        assert post.n_confirmations == 8
        assert post.n_failures == 0
        assert post.n_updates == 8

    def test_failures_push_credibility_down(self) -> None:
        prior = prior_for(SourceType.X_POST)
        post = apply_updates(
            source_id="s",
            source_type=SourceType.X_POST,
            updates=[
                _u(sid="s", outcome=CredibilityOutcome.FAILURE, cid=f"c{i}")
                for i in range(5)
            ],
        )
        assert post.mean < prior.prior_credibility
        assert post.n_failures == 5
        assert post.n_confirmations == 0

    def test_weights_change_rate_of_movement(self) -> None:
        # Higher weight should move the posterior further per event.
        light = apply_updates(
            source_id="s",
            source_type=SourceType.X_POST,
            updates=[_u(sid="s", weight=0.1, cid=f"c{i}") for i in range(5)],
        )
        heavy = apply_updates(
            source_id="s",
            source_type=SourceType.X_POST,
            updates=[_u(sid="s", weight=1.0, cid=f"c{i}") for i in range(5)],
        )
        prior_mean = prior_for(SourceType.X_POST).prior_credibility
        # Both move up (confirmations), heavy moves further.
        assert prior_mean < light.mean < heavy.mean

    def test_posterior_stays_in_unit_interval_under_extremes(self) -> None:
        # Hammer many large-weight failures: mean must stay >= 0.
        post = apply_updates(
            source_id="s",
            source_type=SourceType.PEER_REVIEWED_PAPER,
            updates=[
                _u(sid="s", outcome=CredibilityOutcome.FAILURE, cid=f"c{i}")
                for i in range(1000)
            ],
        )
        assert 0.0 <= post.mean <= 1.0
        # And the inverse direction.
        post2 = apply_updates(
            source_id="s",
            source_type=SourceType.X_POST,
            updates=[_u(sid="s", cid=f"c{i}") for i in range(1000)],
        )
        assert 0.0 <= post2.mean <= 1.0
        # With this many confirmations the mean should be very high
        # but never exceed 1.
        assert post2.mean > 0.9
        assert post2.mean < 1.0

    def test_invalid_weight_rejected(self) -> None:
        with pytest.raises(ValueError):
            CredibilityUpdate(
                source_id="s",
                outcome=CredibilityOutcome.CONFIRMATION,
                weight=0.0,
                kind=CredibilityEventKind.FORECAST_RESOLUTION,
                conclusion_id="c",
                observed_at=datetime.now(timezone.utc),
            )
        with pytest.raises(ValueError):
            CredibilityUpdate(
                source_id="s",
                outcome=CredibilityOutcome.CONFIRMATION,
                weight=1.5,
                kind=CredibilityEventKind.FORECAST_RESOLUTION,
                conclusion_id="c",
                observed_at=datetime.now(timezone.utc),
            )

    def test_last_updated_at_tracks_max(self) -> None:
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t1 = t0 + timedelta(days=10)
        t2 = t0 + timedelta(days=5)
        post = apply_updates(
            source_id="s",
            source_type=SourceType.PEER_REVIEWED_PAPER,
            updates=[
                _u(sid="s", cid="a", when=t0),
                _u(sid="s", cid="b", when=t1),
                _u(sid="s", cid="c", when=t2),
            ],
        )
        assert post.last_updated_at == t1


# ── ledger idempotence + view ───────────────────────────────────────────


class TestLedger:
    def test_idempotent_on_same_resolution(self) -> None:
        led = InMemoryCredibilityLedger()
        u = _u(sid="s", cid="c1")
        assert led.append(u) is True
        assert led.append(u) is False  # exact dup
        assert len(led.history("s")) == 1

    def test_distinct_conclusions_both_recorded(self) -> None:
        led = InMemoryCredibilityLedger()
        led.append(_u(sid="s", cid="c1"))
        led.append(_u(sid="s", cid="c2"))
        assert len(led.history("s")) == 2

    def test_current_credibility_folds_log(self) -> None:
        led = InMemoryCredibilityLedger()
        for i in range(3):
            led.append(_u(sid="s", cid=f"c{i}"))
        for i in range(2):
            led.append(
                _u(sid="s", outcome=CredibilityOutcome.FAILURE, cid=f"f{i}")
            )
        post = current_credibility(
            source_id="s",
            source_type=SourceType.PEER_REVIEWED_PAPER,
            ledger=led,
        )
        assert post.n_confirmations == 3
        assert post.n_failures == 2
        assert post.n_updates == 5


# ── display thresholds ──────────────────────────────────────────────────


class TestDisplay:
    def test_thin_track_record_is_not_confident(self) -> None:
        post = apply_updates(
            source_id="s",
            source_type=SourceType.X_POST,
            updates=[_u(sid="s", cid="c1")],
        )
        assert post.is_confident_for_display is False
        payload = display_payload(post)
        assert payload["confident"] is False
        assert payload["min_updates_for_confidence"] == MIN_UPDATES_FOR_CONFIDENT_DISPLAY

    def test_threshold_flip(self) -> None:
        updates = [
            _u(sid="s", cid=f"c{i}")
            for i in range(MIN_UPDATES_FOR_CONFIDENT_DISPLAY)
        ]
        post = apply_updates(
            source_id="s",
            source_type=SourceType.X_POST,
            updates=updates,
        )
        assert post.is_confident_for_display is True

    def test_score_100_in_range(self) -> None:
        post = apply_updates(
            source_id="s",
            source_type=SourceType.X_POST,
            updates=[],
        )
        assert 0.0 <= post.score_100 <= 100.0


# ── cascade modulation ─────────────────────────────────────────────────


def _post(mean: float, *, n: int = 20) -> BetaPosterior:
    """Construct a BetaPosterior with a target mean for tests."""

    alpha = mean * n
    beta = (1.0 - mean) * n
    return BetaPosterior(
        source_id="s",
        source_type=SourceType.UNKNOWN,
        alpha=alpha,
        beta=beta,
        n_updates=n,
        n_confirmations=int(round(alpha)),
        n_failures=int(round(beta)),
        last_updated_at=None,
    )


class TestCascadeModulation:
    def test_single_edge_scaled_by_credibility(self) -> None:
        post = _post(0.3)
        assert modulated_supports_confidence(0.9, post) == pytest.approx(0.27)

    def test_unknown_source_falls_back_to_neutral(self) -> None:
        # Without a ledger entry we treat the source as neutral 0.5,
        # which is more conservative than full credit.
        assert modulated_supports_confidence(0.8, None) == pytest.approx(0.4)

    def test_modulation_clamped_to_unit_interval(self) -> None:
        assert modulated_supports_confidence(-1.0, _post(0.5)) == 0.0
        assert modulated_supports_confidence(2.0, _post(0.99)) <= 1.0

    def test_aggregator_handles_empty(self) -> None:
        assert aggregate_supports_confidence([]) == 0.0

    def test_many_low_credibility_supports_cannot_manufacture_strong(self) -> None:
        # Constraint from the prompt: a claim supported only by
        # low-credibility sources cannot escape low confidence
        # regardless of how many such sources exist.
        weak = _post(0.2)
        contributions = [(0.9, weak)] * 50
        agg = aggregate_supports_confidence(contributions)
        assert agg <= weak.mean + 1e-9, (
            "Aggregating 50 low-credibility supports should not exceed "
            f"the cap of max-credibility ({weak.mean:.3f}); got {agg:.3f}"
        )

    def test_aggregator_caps_at_strongest_source(self) -> None:
        weak = _post(0.2)
        mid = _post(0.5)
        contributions = [(0.9, weak), (0.9, mid), (0.9, weak)]
        agg = aggregate_supports_confidence(contributions)
        assert agg <= mid.mean + 1e-9

    def test_aggregator_mixed_strong_source_can_lift_aggregate(self) -> None:
        # Add a high-credibility source — the cap rises so the aggregate
        # is allowed to climb above the weak-only ceiling.
        weak = _post(0.2)
        strong = _post(0.9)
        weak_only = aggregate_supports_confidence([(0.9, weak)] * 5)
        with_strong = aggregate_supports_confidence(
            [(0.9, weak)] * 5 + [(0.9, strong)]
        )
        assert with_strong > weak_only

    def test_aggregator_in_unit_interval(self) -> None:
        # Fuzz-ish: lots of contributions of varying credibility — never
        # outside [0, 1].
        contribs = [(0.9, _post(c)) for c in (0.1, 0.3, 0.5, 0.7, 0.9)] * 4
        agg = aggregate_supports_confidence(contribs)
        assert 0.0 <= agg <= 1.0

    def test_cascade_graph_exposes_helpers(self) -> None:
        # The helpers must be reachable through the CascadeGraph
        # surface (callers wire revisions / forecast resolution
        # through the graph, not directly through the literature
        # module).
        post = _post(0.4)
        assert CascadeGraph.modulate_supports_edge(0.8, post) == pytest.approx(0.32)
        assert CascadeGraph.aggregate_supports([(0.8, post)]) > 0.0
