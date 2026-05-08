"""Tests for the quarterly seasonal review assembler.

Synthetic-quarter coverage:

* The structured object matches the seeded values exactly (no
  estimation).
* Sections with no underlying data are marked
  ``data_available=False`` rather than estimated.
* The narrative pass refuses to invent numbers — it raises
  :class:`NumberDriftError` when it sees a decimal/count not present
  in the structured object.
* The .tex output renders with the structured numbers visible and
  pdflatex compiles when available (skipped otherwise).
* The "what we got wrong" section is emitted whether or not findings
  exist for the quarter.
"""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from noosphere.docgen.seasonal_review import (
    DATA_NOT_AVAILABLE_NOTE,
    NARRATIVE_SECTION_KEYS,
    NumberDriftError,
    SELF_CRITIQUE_EMPTY_NOTE,
    assemble_seasonal_review,
    parse_quarter,
    quarter_window,
    render_seasonal_review,
    write_narrative,
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


ORG_ID = "org_seasonal"
Q_YEAR = 2026
Q_NUM = 2
WINDOW = quarter_window(Q_YEAR, Q_NUM)
INSIDE = WINDOW.start.replace(tzinfo=None) + (WINDOW.end - WINDOW.start) / 2
BEFORE = WINDOW.start.replace(tzinfo=None) - (WINDOW.end - WINDOW.start)
AFTER = WINDOW.end.replace(tzinfo=None) + (WINDOW.end - WINDOW.start)


def _store() -> Store:
    return Store.from_database_url("sqlite:///:memory:")


def _seed_methods(store: Store) -> None:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for method_id, name, status in [
        ("m_active", "Six-layer coherence", "active"),
        ("m_dep", "Legacy domain heuristic", "deprecated"),
        ("m_retire", "Naive priors", "retired"),
    ]:
        m = Method(
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
        store.insert_method(m)


def _seed_drift(store: Store) -> None:
    in_window = DriftEvent(
        target_id="m_active",
        observed_at=date(WINDOW.start.year, WINDOW.start.month, 15),
        drift_score=0.42,
        notes="cross-domain transfer regression",
    )
    out_of_window = DriftEvent(
        target_id="m_active",
        observed_at=date(WINDOW.start.year - 1, 1, 5),
        drift_score=0.33,
        notes="prior-quarter event ignored",
    )
    store.put_drift_event(in_window)
    store.put_drift_event(out_of_window)


def _seed_forecast_resolutions(store: Store) -> None:
    with store.session() as session:
        for i, (resolved_at, brier, log_loss) in enumerate(
            [
                (INSIDE, 0.12, 0.30),
                (INSIDE, 0.20, 0.45),
                (BEFORE, 0.05, 0.10),
                (AFTER, 0.99, 1.50),
            ]
        ):
            session.add(
                ForecastResolution(
                    prediction_id=f"pred_{i}",
                    market_outcome=ForecastOutcome.YES,
                    brier_score=brier,
                    log_loss=log_loss,
                    resolved_at=resolved_at,
                    justification="",
                )
            )
        session.commit()


def _seed_articles(store: Store) -> None:
    payloads = [
        ("article-in-window", "First quarter article", INSIDE),
        ("article-out", "Pre-window article", BEFORE),
        ("article-future", "Post-window article", AFTER),
    ]
    with store.session() as session:
        for slug, title, when in payloads:
            payload = {
                "conclusionText": title,
                "article": {"headline": title, "bodyMarkdown": ""},
            }
            session.add(
                PublishedConclusion(
                    organization_id=ORG_ID,
                    source_conclusion_id=f"src_{slug}",
                    slug=slug,
                    version=1,
                    kind="ARTICLE",
                    discounted_confidence=0.7,
                    stated_confidence=0.7,
                    calibration_discount_reason="",
                    payload_json=json.dumps(payload),
                    doi="",
                    zenodo_record_id="",
                    published_at=when,
                )
            )
        session.commit()


def _seed_self_critique_review_items(store: Store) -> None:
    in_window = ReviewItem(
        claim_a_id="article-in-window",
        claim_b_id="report_1",
        reason=(
            "Self-critique on 'First quarter article' — verdict: weakened; "
            "recommended: addend. Source claim aged poorly."
        ),
        status="open",
        created_at=INSIDE.replace(tzinfo=timezone.utc),
    )
    other = ReviewItem(
        claim_a_id="article-in-window",
        claim_b_id="report_2",
        reason="Routine peer-review escalation, not a self-critique",
        status="open",
        created_at=INSIDE.replace(tzinfo=timezone.utc),
    )
    store.put_review_item(in_window)
    store.put_review_item(other)


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
        {
            "text": "Older draft outside the window.",
            "domains": ["a"],
            "cited_conclusion_ids": [],
            "cluster_conclusion_ids": ["c5"],
            "conviction_score": 0.40,
            "domain_breadth": 1,
            "cluster_centroid_similarity": 0.55,
            "status": "draft",
            "drafted_at": BEFORE.replace(tzinfo=timezone.utc).isoformat(),
        },
    ]
    out = tmp_path / "drafts.json"
    out.write_text(json.dumps(drafts), encoding="utf-8")
    return out


def _seeded_store(tmp_path: Path) -> tuple[Store, Path]:
    store = _store()
    _seed_methods(store)
    _seed_drift(store)
    _seed_forecast_resolutions(store)
    _seed_articles(store)
    _seed_self_critique_review_items(store)
    drafts = _seed_principles_drafts(tmp_path)
    return store, drafts


# ── Quarter-window arithmetic ──────────────────────────────────────


def test_quarter_window_bounds_are_correct() -> None:
    w = quarter_window(2026, 2)
    assert w.start == datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert w.end == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert w.label == "2026 Q2"
    assert w.slug == "2026_Q2_Review"


def test_q4_wraps_into_next_year() -> None:
    w = quarter_window(2026, 4)
    assert w.end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_parse_quarter_accepts_common_forms() -> None:
    assert parse_quarter("2026Q2").quarter == 2
    assert parse_quarter("2026-Q2").quarter == 2
    assert parse_quarter(" 2026 q2 ").quarter == 2


# ── Structured assembly: synthetic quarter with known values ──────


def test_structured_object_matches_seeded_values(tmp_path: Path) -> None:
    store, drafts = _seeded_store(tmp_path)
    review = assemble_seasonal_review(
        store,
        year=Q_YEAR,
        quarter=Q_NUM,
        principles_drafts_path=drafts,
    )

    # Methods
    assert review.methods.status.data_available is True
    active_ids = {m.method_id for m in review.methods.active}
    assert "m_active" in active_ids
    assert {m.method_id for m in review.methods.deprecated} == {"m_dep"}
    assert {m.method_id for m in review.methods.retired} == {"m_retire"}

    # Drift in window only
    assert review.drift.status.data_available is True
    assert len(review.drift.events) == 1
    assert review.drift.events[0].target_id == "m_active"
    assert review.drift.events[0].drift_score == pytest.approx(0.42)

    # Calibration: only the two in-window resolutions count
    assert review.calibration.status.data_available is True
    assert review.calibration.resolved_count == 2
    assert review.calibration.mean_brier == pytest.approx((0.12 + 0.20) / 2)
    assert review.calibration.mean_log_loss == pytest.approx((0.30 + 0.45) / 2)

    # Articles in window only
    assert review.articles.status.data_available is True
    assert len(review.articles.articles) == 1
    assert review.articles.articles[0].slug == "article-in-window"

    # Principles in window only
    assert review.principles.status.data_available is True
    assert len(review.principles.drafted) == 1
    assert review.principles.drafted[0].domain_breadth == 3
    assert review.principles.drafted[0].conviction_score == pytest.approx(0.74)

    # Self-critique: only the prefixed review item, not the unrelated one
    assert review.self_critique.status.data_available is True
    assert len(review.self_critique.findings) == 1
    finding = review.self_critique.findings[0]
    assert finding.article_id == "article-in-window"
    assert finding.reason.startswith("Self-critique on")


def test_missing_metric_section_marks_data_not_available(tmp_path: Path) -> None:
    """A quarter with no resolved forecasts and no edits records the
    gap explicitly rather than estimating.
    """
    store = _store()
    _seed_methods(store)
    review = assemble_seasonal_review(
        store, year=Q_YEAR, quarter=Q_NUM
    )

    assert review.calibration.status.data_available is False
    assert "no resolved forecasts" in review.calibration.status.note

    assert review.articles.status.data_available is False
    assert "no articles published" in review.articles.status.note

    assert review.principles.status.data_available is False
    assert review.principles.status.note == DATA_NOT_AVAILABLE_NOTE

    assert review.open_questions.status.data_available is False
    assert review.open_questions.status.note == DATA_NOT_AVAILABLE_NOTE


def test_self_critique_section_is_emitted_even_when_empty(tmp_path: Path) -> None:
    """Required-section invariant: even with zero findings, the
    self-critique section is present and the empty-state note is
    available for the renderer to use.
    """
    store = _store()
    review = assemble_seasonal_review(
        store, year=Q_YEAR, quarter=Q_NUM
    )
    assert review.self_critique.status.data_available is True
    assert len(review.self_critique.findings) == 0


# ── Narrative pass: number drift is a build failure ───────────────


class _PerSectionScripted:
    """Returns one scripted prose blob per section in declaration order."""

    def __init__(self, sections: dict[str, str]) -> None:
        self.sections = dict(sections)
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        for key in NARRATIVE_SECTION_KEYS:
            marker = f"Section: {key}"
            if marker in user:
                self.calls.append({"section": key, "user": user})
                return self.sections.get(key, "")
        raise AssertionError(
            "user prompt did not mention any known section key"
        )


def test_narrative_writer_passes_when_numbers_align(tmp_path: Path) -> None:
    store, drafts = _seeded_store(tmp_path)
    review = assemble_seasonal_review(
        store, year=Q_YEAR, quarter=Q_NUM, principles_drafts_path=drafts
    )

    # Every quoted decimal/integer below appears in the structured
    # object: 1 method retired, 1 drift event, 2 resolved forecasts,
    # 1 article, 1 principle, etc.
    safe = {
        "overview": (
            "The firm closed the quarter with 1 retired method and "
            "2 resolved forecasts."
        ),
        "methods": "The firm retired 1 method this quarter.",
        "drift": "The firm observed 1 drift event in the quarter.",
        "calibration": "Across 2 resolved forecasts the firm holds.",
        "open_questions": "Open-questions data was not available.",
        "articles": "The firm published 1 article in the window.",
        "principles": (
            "The firm distilled 1 principle, conviction 0.74, "
            "spanning 3 domains."
        ),
        "edited_conclusions": "No conclusions were edited in the window.",
        "self_critique": (
            "1 self-critique finding entered the queue this quarter."
        ),
    }

    client = _PerSectionScripted(safe)
    narrative = write_narrative(review, client)

    assert set(narrative.sections.keys()) == set(NARRATIVE_SECTION_KEYS)
    assert "1 retired method" in narrative.sections["overview"]


def test_narrative_writer_blocks_invented_numbers(tmp_path: Path) -> None:
    store, drafts = _seeded_store(tmp_path)
    review = assemble_seasonal_review(
        store, year=Q_YEAR, quarter=Q_NUM, principles_drafts_path=drafts
    )

    # 0.97 is not in the structured object's number ledger.
    cheating = {key: "All clear." for key in NARRATIVE_SECTION_KEYS}
    cheating["calibration"] = (
        "Across 2 resolved forecasts the firm achieved a mean Brier of 0.97."
    )
    client = _PerSectionScripted(cheating)
    with pytest.raises(NumberDriftError) as exc_info:
        write_narrative(review, client)
    assert "calibration" in str(exc_info.value)


# ── Rendering & PDF ───────────────────────────────────────────────


def test_render_writes_tex_and_json_with_self_critique_present(
    tmp_path: Path,
) -> None:
    store, drafts = _seeded_store(tmp_path)
    review = assemble_seasonal_review(
        store, year=Q_YEAR, quarter=Q_NUM, principles_drafts_path=drafts
    )
    artifact = render_seasonal_review(
        review,
        out_root=tmp_path / "seasonal",
        build_pdf=False,
    )
    assert artifact.tex_path.exists()
    assert artifact.json_path.exists()

    tex = artifact.tex_path.read_text(encoding="utf-8")
    assert "What we got wrong" in tex
    assert "2026 Q2" in tex
    # The self-critique finding row must be in the .tex when there is one.
    assert "article-in-window" in tex

    sidecar = json.loads(artifact.json_path.read_text(encoding="utf-8"))
    assert sidecar["review_state"] == "pending"
    assert sidecar["structured"]["self_critique"]["finding_count"] == 1
    assert sidecar["disclosure"] == "machine-drafted, founder-reviewed"


def test_render_without_self_critique_findings_uses_canonical_empty_note(
    tmp_path: Path,
) -> None:
    """The self-critique section cannot be silenced: an empty-quarter
    review still emits the canonical empty-state line.
    """
    store = _store()
    review = assemble_seasonal_review(
        store, year=Q_YEAR, quarter=Q_NUM
    )
    artifact = render_seasonal_review(
        review,
        out_root=tmp_path / "seasonal",
        build_pdf=False,
    )
    tex = artifact.tex_path.read_text(encoding="utf-8")
    assert SELF_CRITIQUE_EMPTY_NOTE in tex


@pytest.mark.skipif(
    shutil.which("pdflatex") is None,
    reason="pdflatex not on PATH",
)
def test_pdf_compiles_when_pdflatex_is_available(tmp_path: Path) -> None:
    store, drafts = _seeded_store(tmp_path)
    review = assemble_seasonal_review(
        store, year=Q_YEAR, quarter=Q_NUM, principles_drafts_path=drafts
    )
    artifact = render_seasonal_review(
        review, out_root=tmp_path / "seasonal", build_pdf=True
    )
    assert artifact.pdf_path is not None
    assert artifact.pdf_path.exists()
    assert artifact.pdf_path.stat().st_size > 0
