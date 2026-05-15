"""End-to-end integration tests for the firm's first seasonal review.

The unit tests in ``test_seasonal_review.py`` cover quarter arithmetic
and the per-section assembler. This module tests the three invariants
the founder-facing workflow depends on:

* The assembler is deterministic for a fixed window. Two runs over the
  same seeded store produce the same structured object (everything
  except ``generated_at``, which is the wall clock).
* The narrative pass cannot introduce a number that does not already
  appear in the structured object's ledger — drift is a build
  failure, not a silent fabrication.
* The publication signing path round-trips on the seasonal-review
  canonical input: sign over the structured bytes, verify ok against
  the live input, mutate the live input, verify fails.

The signing helper used here mirrors the script
(``scripts/run_seasonal_review.sh``) byte-for-byte — both build a
``PublicationCanonicalInput`` from the structured review using the
canonical-JSON of the structured dict as the conclusion-text slot.
Keeping both code paths converging on the same canonical input is what
makes signature verification meaningful: the script signs what tests
verify.
"""
from __future__ import annotations

import copy
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from noosphere.docgen.seasonal_review import (
    NARRATIVE_SECTION_KEYS,
    NumberDriftError,
    SeasonalReview,
    assemble_seasonal_review,
    quarter_window,
    render_seasonal_review,
    set_review_state,
    write_narrative,
)
from noosphere.ledger.canonicalize import (
    PublicationCanonicalInput,
    canonical_json,
)
from noosphere.ledger.publication_signing import (
    PublicationKeyring,
    sign_publication,
    verify_signature,
)
from noosphere.models import (
    DriftEvent,
    ForecastOutcome,
    ForecastResolution,
    Method,
    MethodImplRef,
    MethodType,
    PublishedConclusion,
    ReviewItem,
)
from noosphere.store import Store


ORG_ID = "org_seasonal_integration"
Q_YEAR = 2026
Q_NUM = 2
WINDOW = quarter_window(Q_YEAR, Q_NUM)
# A single anchor in the middle of the quarter window. Pinned so the
# seeded values are byte-identical across runs.
INSIDE = datetime(2026, 5, 14, 12, 0, 0)
GENERATED_AT = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


# ── Deterministic seeding ──────────────────────────────────────────


def _seed_methods(store: Store) -> None:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for method_id, name, status in [
        ("m_active_one", "Six-layer coherence", "active"),
        ("m_active_two", "Adversarial probing", "active"),
        ("m_dep", "Legacy domain heuristic", "deprecated"),
        ("m_retire", "Naive priors", "retired"),
    ]:
        store.insert_method(
            Method(
                method_id=method_id,
                name=name,
                version="1.0",
                method_type=MethodType.JUDGMENT,
                input_schema={},
                output_schema={},
                description="",
                rationale="",
                preconditions=[],
                postconditions=[],
                dependencies=[],
                implementation=MethodImplRef(
                    module="x.y", fn_name="run", git_sha="0" * 40
                ),
                owner="firm",
                status=status,
                nondeterministic=False,
                created_at=base,
            )
        )


def _seed_drift(store: Store) -> None:
    store.put_drift_event(
        DriftEvent(
            id="drift_in_window",
            target_id="m_active_one",
            observed_at=date(WINDOW.start.year, WINDOW.start.month, 15),
            drift_score=0.42,
            notes="cross-domain transfer regression",
        )
    )
    store.put_drift_event(
        DriftEvent(
            id="drift_out_window",
            target_id="m_active_two",
            observed_at=date(WINDOW.start.year - 1, 1, 5),
            drift_score=0.33,
            notes="prior-quarter event ignored",
        )
    )


def _seed_forecasts(store: Store) -> None:
    with store.session() as session:
        for i, brier, log_loss in [
            (0, 0.12, 0.30),
            (1, 0.20, 0.45),
        ]:
            session.add(
                ForecastResolution(
                    id=f"resolution_{i}",
                    prediction_id=f"pred_{i}",
                    market_outcome=ForecastOutcome.YES,
                    brier_score=brier,
                    log_loss=log_loss,
                    resolved_at=INSIDE,
                    justification="",
                )
            )
        session.commit()


def _seed_articles(store: Store) -> None:
    with store.session() as session:
        payload = {
            "conclusionText": "First quarter article",
            "article": {
                "headline": "First quarter article",
                "bodyMarkdown": "",
            },
        }
        session.add(
            PublishedConclusion(
                id="pub_in_window",
                organization_id=ORG_ID,
                source_conclusion_id="src_article",
                slug="article-in-window",
                version=1,
                kind="ARTICLE",
                discounted_confidence=0.7,
                stated_confidence=0.7,
                calibration_discount_reason="",
                payload_json=json.dumps(payload, sort_keys=True),
                doi="",
                zenodo_record_id="",
                published_at=INSIDE,
            )
        )
        session.commit()


def _seed_self_critique(store: Store) -> None:
    store.put_review_item(
        ReviewItem(
            id="review_in_window",
            claim_a_id="article-in-window",
            claim_b_id="report_1",
            reason=(
                "Self-critique on 'First quarter article' — verdict: "
                "weakened; recommended: addend. Source claim aged poorly."
            ),
            status="open",
            created_at=INSIDE.replace(tzinfo=timezone.utc),
        )
    )


def _seed_principles_drafts(tmp_path: Path) -> Path:
    drafts = [
        {
            "text": "Cross-domain coherence beats single-domain depth.",
            "domains": ["a", "b", "c"],
            "cited_conclusion_ids": ["c1", "c2"],
            "cluster_conclusion_ids": ["c1", "c2", "c3", "c4"],
            "conviction_score": 0.74,
            "domain_breadth": 3,
            "cluster_centroid_similarity": 0.81,
            "status": "draft",
            "drafted_at": INSIDE.replace(tzinfo=timezone.utc).isoformat(),
        },
    ]
    out = tmp_path / "drafts.json"
    out.write_text(json.dumps(drafts, sort_keys=True), encoding="utf-8")
    return out


def _seeded_store(tmp_path: Path) -> tuple[Store, Path]:
    store = Store.from_database_url("sqlite:///:memory:")
    _seed_methods(store)
    _seed_drift(store)
    _seed_forecasts(store)
    _seed_articles(store)
    _seed_self_critique(store)
    return store, _seed_principles_drafts(tmp_path)


def _stable_dict(review: SeasonalReview) -> dict:
    """``to_dict()`` minus the wall-clock ``generated_at`` field.

    Determinism applies to the derived content of the quarter, not to
    the moment the assembler was invoked.
    """
    payload = copy.deepcopy(review.to_dict())
    payload.pop("generated_at", None)
    return payload


# ── A. Determinism for a fixed window ──────────────────────────────


def test_assembler_output_is_deterministic_for_fixed_window(
    tmp_path: Path,
) -> None:
    store, drafts = _seeded_store(tmp_path)

    first = assemble_seasonal_review(
        store,
        year=Q_YEAR,
        quarter=Q_NUM,
        principles_drafts_path=drafts,
        now=GENERATED_AT,
    )
    second = assemble_seasonal_review(
        store,
        year=Q_YEAR,
        quarter=Q_NUM,
        principles_drafts_path=drafts,
        now=GENERATED_AT,
    )

    assert _stable_dict(first) == _stable_dict(second)
    # Canonical JSON of the structured slice must round-trip byte-equal.
    assert canonical_json(_stable_dict(first)) == canonical_json(
        _stable_dict(second)
    )


# ── B. Narrative pass refuses invented numbers ─────────────────────


class _ScriptedLLM:
    """LLM stub that returns prose pre-keyed by section."""

    def __init__(self, sections: dict[str, str]) -> None:
        self.sections = dict(sections)
        self.calls: list[str] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        for key in NARRATIVE_SECTION_KEYS:
            if f"Section: {key}" in user:
                self.calls.append(key)
                return self.sections.get(key, "")
        raise AssertionError("no known section key in user prompt")


def test_prose_pass_cannot_introduce_numbers(tmp_path: Path) -> None:
    store, drafts = _seeded_store(tmp_path)
    review = assemble_seasonal_review(
        store,
        year=Q_YEAR,
        quarter=Q_NUM,
        principles_drafts_path=drafts,
        now=GENERATED_AT,
    )

    # 0.97 is not anywhere in the structured object's number ledger.
    cheating = {key: "All clear." for key in NARRATIVE_SECTION_KEYS}
    cheating["calibration"] = (
        "Across 2 resolved forecasts the firm achieved a mean Brier of 0.97."
    )

    with pytest.raises(NumberDriftError) as exc:
        write_narrative(review, _ScriptedLLM(cheating))
    assert "calibration" in str(exc.value)
    assert "0.97" in str(exc.value)


# ── C. Signing round-trip ─────────────────────────────────────────


def seasonal_canonical_input(review: SeasonalReview) -> PublicationCanonicalInput:
    """Build the publication-signing canonical input for a seasonal review.

    The seasonal review is signed over the byte content of its
    structured-object: that is exactly what the narrative pass is
    constrained to. The signed bytes therefore certify the firm's
    quarter (counts, scores, IDs, dates) — not a particular prose
    rendering of it.

    The same builder lives in the driver script; tests and driver must
    agree on canonical input down to the byte or the signature would
    not round-trip.
    """
    structured = canonical_json(review.to_dict()).decode("utf-8")
    return PublicationCanonicalInput(
        slug=review.window.slug,
        version=1,
        conclusion_text=structured,
        methodology_profile_ids=[],
        citations=[],
        discounted_confidence=1.0,
        stated_confidence=1.0,
        mqs=None,
        published_at=review.generated_at,
    )


def test_signature_round_trip_on_seasonal_review(tmp_path: Path) -> None:
    store, drafts = _seeded_store(tmp_path)
    review = assemble_seasonal_review(
        store,
        year=Q_YEAR,
        quarter=Q_NUM,
        principles_drafts_path=drafts,
        now=GENERATED_AT,
    )
    canonical = seasonal_canonical_input(review)

    with tempfile.TemporaryDirectory() as tmp:
        keyring = PublicationKeyring(Path(tmp) / "publication-keys")
        keyring.ensure()
        sig = sign_publication(canonical, keyring)

        # Unmutated input verifies.
        result = verify_signature(sig, keyring, live_input=canonical)
        assert result.ok, result.reason

        # Mutated input — slug changed — must fail.
        mutated = PublicationCanonicalInput(
            slug=canonical.slug + "_v2",
            version=canonical.version,
            conclusion_text=canonical.conclusion_text,
            methodology_profile_ids=list(canonical.methodology_profile_ids),
            citations=list(canonical.citations),
            discounted_confidence=canonical.discounted_confidence,
            stated_confidence=canonical.stated_confidence,
            mqs=canonical.mqs,
            published_at=canonical.published_at,
        )
        mutated_result = verify_signature(sig, keyring, live_input=mutated)
        assert not mutated_result.ok

        # Mutating the structured payload (e.g. dropping a calibration
        # number) must also fail — the signed bytes certify the
        # structured numbers.
        structured = json.loads(canonical.conclusion_text)
        structured["calibration"]["mean_brier"] = 0.99
        tampered = PublicationCanonicalInput(
            slug=canonical.slug,
            version=canonical.version,
            conclusion_text=canonical_json(structured).decode("utf-8"),
            methodology_profile_ids=list(canonical.methodology_profile_ids),
            citations=list(canonical.citations),
            discounted_confidence=canonical.discounted_confidence,
            stated_confidence=canonical.stated_confidence,
            mqs=canonical.mqs,
            published_at=canonical.published_at,
        )
        tampered_result = verify_signature(sig, keyring, live_input=tampered)
        assert not tampered_result.ok


# ── D. End-to-end: render, queue, sign on founder approval ────────


def test_founder_approval_flow_writes_signature(tmp_path: Path) -> None:
    """Render the review, leave it pending, flip to approved, sign.

    The agent never flips ``review_state`` to ``published`` on its own
    — that is a founder action. The test models the founder action by
    calling ``set_review_state`` directly. After the flip the signing
    path round-trips on the canonical bytes the sidecar carries.
    """
    store, drafts = _seeded_store(tmp_path)
    review = assemble_seasonal_review(
        store,
        year=Q_YEAR,
        quarter=Q_NUM,
        principles_drafts_path=drafts,
        now=GENERATED_AT,
    )

    out_root = tmp_path / "seasonal"
    artifact = render_seasonal_review(review, out_root=out_root, build_pdf=False)
    assert artifact.tex_path.exists()
    assert artifact.json_path.exists()

    sidecar = json.loads(artifact.json_path.read_text(encoding="utf-8"))
    assert sidecar["review_state"] == "pending"

    # Founder approves.
    updated = set_review_state(
        out_root=out_root,
        slug=review.window.slug,
        review_state="approved",
        reviewer="founder",
    )
    assert updated["review_state"] == "approved"

    # Sign over the canonical input.
    canonical = seasonal_canonical_input(review)
    with tempfile.TemporaryDirectory() as tmp:
        keyring = PublicationKeyring(Path(tmp) / "publication-keys")
        keyring.ensure()
        sig = sign_publication(canonical, keyring)
        (out_root / review.window.slug / "signature.json").write_text(
            json.dumps(sig.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        verify_ok = verify_signature(sig, keyring, live_input=canonical)
        assert verify_ok.ok

    # Founder publishes.
    published = set_review_state(
        out_root=out_root,
        slug=review.window.slug,
        review_state="published",
        reviewer="founder",
    )
    assert published["review_state"] == "published"
    # The structured numbers above the signature are unchanged.
    final_sidecar = json.loads(artifact.json_path.read_text(encoding="utf-8"))
    assert final_sidecar["structured"] == sidecar["structured"]
