"""Tests: retiring an object flags every conclusion that cited it for re-examination."""

from __future__ import annotations

import uuid

import pytest

from noosphere.models import (
    Actor,
    Claim,
    Conclusion,
    ConfidenceTier,
    Freshness,
    RevalidationResult,
    Speaker,
)
from noosphere.store import Store


def _uid() -> str:
    return str(uuid.uuid4())


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


class TestRetirementCascade:
    def test_retiring_claim_flags_citing_conclusions(self):
        from noosphere.decay.retirement import retire

        store = _store()
        claim_id = _uid()
        claim = Claim(
            id=claim_id,
            text="testable claim",
            speaker=Speaker(name="Alice"),
            episode_id="ep1",
            episode_date="2025-01-01",
            freshness=Freshness.FRESH,
        )
        store.put_claim(claim)

        conc_id = _uid()
        conclusion = Conclusion(
            id=conc_id,
            text="derived conclusion",
            claims_used=[claim_id],
            freshness=Freshness.FRESH,
            confidence_tier=ConfidenceTier.MODERATE,
        )
        store.put_conclusion(conclusion)

        unrelated_id = _uid()
        unrelated = Conclusion(
            id=unrelated_id,
            text="unrelated conclusion",
            claims_used=[_uid()],
            freshness=Freshness.FRESH,
            confidence_tier=ConfidenceTier.MODERATE,
        )
        store.put_conclusion(unrelated)

        actor = Actor(kind="agent", id="decay-scheduler", display_name="Decay")
        result = retire(store, claim_id, reason="refuted by new evidence", actor=actor)

        assert result.outcome == "refuted"
        assert result.new_tier == "retired"

        retired_claim = store.get_claim(claim_id)
        assert retired_claim is not None
        assert retired_claim.freshness == Freshness.RETIRED

        flagged = store.get_conclusion(conc_id)
        assert flagged is not None
        assert flagged.freshness == Freshness.STALE

        untouched = store.get_conclusion(unrelated_id)
        assert untouched is not None
        assert untouched.freshness == Freshness.FRESH

    def test_retiring_claim_inserts_reexamine_revalidation(self):
        from noosphere.decay.retirement import retire

        store = _store()
        claim_id = _uid()
        claim = Claim(
            id=claim_id,
            text="claim",
            speaker=Speaker(name="Bob"),
            episode_id="ep1",
            episode_date="2025-01-01",
        )
        store.put_claim(claim)

        conc_id = _uid()
        conclusion = Conclusion(
            id=conc_id,
            text="conclusion citing claim",
            claims_used=[claim_id],
            confidence_tier=ConfidenceTier.MODERATE,
        )
        store.put_conclusion(conclusion)

        actor = Actor(kind="agent", id="decay", display_name="Decay")
        retire(store, claim_id, reason="test", actor=actor)

        revals = store.list_revalidations(conc_id)
        assert len(revals) >= 1
        reexamine = [r for r in revals if "cascade:retired" in r.ledger_entry_id]
        assert len(reexamine) == 1
        assert reexamine[0].new_tier == "needs_reexamination"

    def test_retiring_conclusion_does_not_cascade_to_other_conclusions(self):
        from noosphere.decay.retirement import retire

        store = _store()
        conc_id = _uid()
        conclusion = Conclusion(
            id=conc_id,
            text="a conclusion",
            claims_used=[],
            confidence_tier=ConfidenceTier.MODERATE,
        )
        store.put_conclusion(conclusion)

        other_id = _uid()
        other = Conclusion(
            id=other_id,
            text="other conclusion not citing the first",
            claims_used=[_uid()],
            confidence_tier=ConfidenceTier.MODERATE,
        )
        store.put_conclusion(other)

        actor = Actor(kind="agent", id="decay", display_name="Decay")
        retire(store, conc_id, reason="test", actor=actor)

        other_after = store.get_conclusion(other_id)
        assert other_after is not None
        assert other_after.freshness == Freshness.FRESH

    def test_already_retired_conclusions_not_re_flagged(self):
        from noosphere.decay.retirement import retire

        store = _store()
        claim_id = _uid()
        claim = Claim(
            id=claim_id,
            text="claim",
            speaker=Speaker(name="C"),
            episode_id="ep1",
            episode_date="2025-01-01",
        )
        store.put_claim(claim)

        conc_id = _uid()
        conclusion = Conclusion(
            id=conc_id,
            text="already retired conclusion",
            claims_used=[claim_id],
            freshness=Freshness.RETIRED,
            confidence_tier=ConfidenceTier.MODERATE,
        )
        store.put_conclusion(conclusion)

        actor = Actor(kind="agent", id="decay", display_name="Decay")
        retire(store, claim_id, reason="test", actor=actor)

        revals = store.list_revalidations(conc_id)
        reexamine = [r for r in revals if "cascade:retired" in r.ledger_entry_id]
        assert len(reexamine) == 0
