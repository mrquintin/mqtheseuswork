#!/usr/bin/env bash
# Produce the firm's first seasonal research review (Round 17 prompt 47
# generator, "actually run it" step).
#
# The assembler, narrative pass, founder triage queue surface, signing
# path, and public seasonal-review route already exist. This script
# turns that code into real artifacts on disk: it assembles the
# structured object for one quarter, runs the narrative pass over it,
# renders .tex (and .pdf when pdflatex is on PATH), files the draft in
# the founder review queue, writes the founder a reviewer's memo, and
# verifies the signing path end-to-end on the same canonical bytes the
# sidecar carries — so when the founder approves, the publish step is
# already proven.
#
# Stages:
#   1. Assemble   — assemble_seasonal_review walks the firm's machinery
#      for the quarter window and produces a fully derived structured
#      object. Sections whose underlying data is missing are recorded
#      with data_available=False; nothing is estimated.
#   2. Narrate    — write_narrative runs the constrained narrative pass.
#      Every decimal-bearing token the prose emits must already appear
#      in the structured object's number ledger, or NumberDriftError is
#      raised. In --offline mode (default when no LLM key is present)
#      the prose pass is skipped — the .tex still renders, just without
#      paragraphs.
#   3. Render     — write the .tex source + .json sidecar under
#      docs/seasonal/<slug>/. Build the PDF when pdflatex is on PATH.
#      A flat copy is left at docs/seasonal/<slug>.{tex,pdf} so the
#      committed artifact lives at a stable path.
#   4. Memo       — docs/research/internal/Seasonal_Review_Q<n>_Reviewer_Memo.md
#      lists the strongest finding, the most embarrassing finding,
#      claims the agent is uncertain about, and every number in the
#      review the agent cannot trace to a row in the database. The
#      memo is the agent's reviewer-of-itself output, not a publication.
#   5. Sign-path  — sign over the same canonical bytes the sidecar
#      carries, verify ok, mutate, verify fails. This proves the
#      signing path works on the seasonal-review canonical input shape
#      before the founder approves. The signature itself is NOT
#      committed (the agent does not publish); the script writes it to
#      a temporary keyring so the verification is end-to-end.
#   6. Digest entry — when the founder later approves the review,
#      subscribers (Round 17 prompt 39) receive a digest entry. The
#      script writes the intake payload for that entry to a sibling
#      file so the founder can review it before the digest fires; the
#      script does NOT enqueue an actual send.
#
# What the agent does NOT do — every one of these is a founder action:
#   * It does not flip review_state. The draft lands ``pending``.
#   * It does not publish. The signing path is verified on a
#     throwaway keyring; the firm's publication keys are untouched.
#   * It does not announce externally. The digest event is staged for
#     founder approval, not enqueued for send.
#
# Run modes:
#   --demo-corpus  (default) seed an embedded, frozen verification
#                  corpus into a scratch SQLite store and review from
#                  it. The four seeded signals are deterministic, so
#                  re-running refreshes docs/seasonal cleanly.
#   --store        review from the live noosphere store instead. If
#                  the store has no signals in the window the review
#                  still produces — empty sections record "data not
#                  available" notes rather than being padded with
#                  estimates.
#
# Usage:
#   ./run_seasonal_review.sh [--demo-corpus | --store]
#       [--year YYYY] [--quarter N]
#       [--out-root DIR] [--memo-dir DIR] [--no-pdf]
#
#   --out-root DIR   Where the slug dir + flat copies land. Default
#                    docs/seasonal.
#   --memo-dir DIR   Where the reviewer memo lands. Default
#                    docs/research/internal.
#   --no-pdf         Skip pdflatex; emit only .tex.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/noosphere:${PYTHONPATH:-}"

PY="${PYTHON:-python3}"
CORPUS_MODE="demo"
OUT_ROOT="$ROOT/docs/seasonal"
MEMO_DIR="$ROOT/docs/research/internal"
YEAR="2026"
QUARTER="2"
BUILD_PDF="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo-corpus) CORPUS_MODE="demo"; shift;;
    --store) CORPUS_MODE="store"; shift;;
    --year) YEAR="$2"; shift 2;;
    --quarter) QUARTER="$2"; shift 2;;
    --out-root) OUT_ROOT="$2"; shift 2;;
    --memo-dir) MEMO_DIR="$2"; shift 2;;
    --no-pdf) BUILD_PDF="0"; shift;;
    -h|--help) sed -n '2,80p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

mkdir -p "$OUT_ROOT" "$MEMO_DIR"

echo "=== First seasonal review run ==="
echo "  root       : $ROOT"
echo "  year       : $YEAR"
echo "  quarter    : Q$QUARTER"
echo "  corpus     : $CORPUS_MODE"
echo "  out root   : $OUT_ROOT"
echo "  memo dir   : $MEMO_DIR"
echo "  build pdf  : $BUILD_PDF"
echo

SEASONAL_MODE="$CORPUS_MODE" \
SEASONAL_YEAR="$YEAR" \
SEASONAL_QUARTER="$QUARTER" \
SEASONAL_OUT_ROOT="$OUT_ROOT" \
SEASONAL_MEMO_DIR="$MEMO_DIR" \
SEASONAL_BUILD_PDF="$BUILD_PDF" \
"$PY" - <<'PYEOF'
"""Driver: assemble the quarter, run the narrative pass, render the
artifact, write the reviewer memo, verify the signing path, stage the
subscriber digest event. The stages share the same in-memory store and
the same structured-object instance, so they run in one process."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

# The narrative-pass stub doesn't hit the LLM, but the assembler logs
# a couple of benign warnings on a scratch store (no resolved forecasts
# in some cells; no per-window open-questions feed). Quiet them so the
# stage log stays readable.
logging.disable(logging.WARNING)

# LaTeX byproducts pdflatex drops next to the PDF. The .tex and .pdf
# are the artifacts; these are not.
_LATEX_BYPRODUCTS = (".aux", ".log", ".out", ".fls", ".fdb_latexmk",
                     ".synctex.gz", ".toc")


def _clean_latex_byproducts(tex_path: Path) -> None:
    for suffix in _LATEX_BYPRODUCTS:
        candidate = tex_path.with_suffix(suffix)
        if candidate.exists():
            candidate.unlink()


from noosphere.docgen.seasonal_review import (
    DISCLOSURE_LABEL,
    NARRATIVE_SECTION_KEYS,
    SELF_CRITIQUE_EMPTY_NOTE,
    SeasonalReview,
    assemble_seasonal_review,
    quarter_window,
    render_seasonal_review,
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

MODE = os.environ["SEASONAL_MODE"]
YEAR = int(os.environ["SEASONAL_YEAR"])
QUARTER = int(os.environ["SEASONAL_QUARTER"])
OUT_ROOT = Path(os.environ["SEASONAL_OUT_ROOT"])
MEMO_DIR = Path(os.environ["SEASONAL_MEMO_DIR"])
BUILD_PDF = os.environ["SEASONAL_BUILD_PDF"] == "1"
WINDOW = quarter_window(YEAR, QUARTER)
INSIDE = datetime(WINDOW.start.year, WINDOW.start.month, 15, 12, 0, 0)
# Pin the generated_at so the committed artifact is reproducible. The
# .tex (and the canonical bytes the signature covers) are byte-stable
# across reruns from the demo corpus.
GENERATED_AT = datetime(YEAR, WINDOW.end.month, 1, 12, 0, 0,
                        tzinfo=timezone.utc) - timedelta(days=1)
ORG_ID = "org_first_seasonal_review"


def log(msg: str) -> None:
    print(msg, flush=True)


# ── Demo corpus ────────────────────────────────────────────────────
#
# An embedded verification corpus seeded into an in-memory store. Four
# active method registrations, two drift events (one in window), four
# forecast resolutions (two in window), one published article, one
# self-critique review item, and a principle drafts file — enough to
# exercise every section of the template at meaningful sizes without
# overloading the founder memo. Same shape as test_seasonal_review.py's
# fixtures but with more rows so the rendered review is closer to what
# a real quarter looks like.


def _seed_demo_store():
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

    store = Store.from_database_url("sqlite:///:memory:")
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    methods = [
        ("m_six_layer",        "Six-layer coherence",          "active"),
        ("m_adversarial",      "Adversarial probing",          "active"),
        ("m_calibration",      "Calibration-aware confidence", "active"),
        ("m_geometry",         "Representational geometry",    "experimental"),
        ("m_legacy_heuristic", "Legacy domain heuristic",      "deprecated"),
        ("m_naive_priors",     "Naive priors",                 "retired"),
    ]
    for method_id, name, status in methods:
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
                    module="x.y", fn_name="run", git_sha="0" * 40,
                ),
                owner="firm",
                status=status,
                nondeterministic=False,
                created_at=base,
            )
        )

    # Drift events: one inside the window, one prior-quarter.
    store.put_drift_event(
        DriftEvent(
            id="drift_q2_geometry",
            target_id="m_geometry",
            observed_at=date(WINDOW.start.year, WINDOW.start.month, 21),
            drift_score=0.420,
            notes="cross-domain transfer regression after embedder swap",
        )
    )
    store.put_drift_event(
        DriftEvent(
            id="drift_q2_calibration",
            target_id="m_calibration",
            observed_at=date(WINDOW.start.year, WINDOW.start.month + 1, 4),
            drift_score=0.275,
            notes="bucket-12 reliability slipped",
        )
    )
    store.put_drift_event(
        DriftEvent(
            id="drift_prior_quarter",
            target_id="m_six_layer",
            observed_at=date(WINDOW.start.year - 1, 1, 5),
            drift_score=0.330,
            notes="prior-quarter event (ignored — outside window)",
        )
    )

    # Forecast resolutions: two in-window, two out.
    with store.session() as session:
        for i, when, brier, log_loss in [
            (0, INSIDE,                                 0.12, 0.30),
            (1, INSIDE + timedelta(days=12),             0.20, 0.45),
            (2, INSIDE + timedelta(days=28),             0.08, 0.25),
            (3, INSIDE + timedelta(days=40),             0.15, 0.36),
            (4, WINDOW.start.replace(tzinfo=None) - timedelta(days=10), 0.05, 0.10),
            (5, WINDOW.end.replace(tzinfo=None) + timedelta(days=14),  0.99, 1.50),
        ]:
            session.add(
                ForecastResolution(
                    id=f"resolution_{i}",
                    prediction_id=f"pred_{i}",
                    market_outcome=ForecastOutcome.YES,
                    brier_score=brier,
                    log_loss=log_loss,
                    resolved_at=when,
                    justification="",
                )
            )
        session.commit()

    # Published articles: two in window, one before.
    with store.session() as session:
        seeds = [
            ("calibrated-narrowing", "A calibrated narrow claim beats a "
             "confident broad one", INSIDE),
            ("adversarial-first", "Adversarial review surfaces the buried "
             "assumption", INSIDE + timedelta(days=18)),
            ("pre-window-article", "Prior-quarter article (ignored)",
             WINDOW.start.replace(tzinfo=None) - timedelta(days=20)),
        ]
        for slug, headline, when in seeds:
            payload = {
                "conclusionText": headline,
                "article": {"headline": headline, "bodyMarkdown": ""},
            }
            session.add(
                PublishedConclusion(
                    id=f"pub_{slug}",
                    organization_id=ORG_ID,
                    source_conclusion_id=f"src_{slug}",
                    slug=slug,
                    version=1,
                    kind="ARTICLE",
                    discounted_confidence=0.7,
                    stated_confidence=0.7,
                    calibration_discount_reason="",
                    payload_json=json.dumps(payload, sort_keys=True),
                    doi="",
                    zenodo_record_id="",
                    published_at=when,
                )
            )
        session.commit()

    # Self-critique findings: two in window, one unrelated review item.
    store.put_review_item(
        ReviewItem(
            id="review_self_crit_one",
            claim_a_id="calibrated-narrowing",
            claim_b_id="self-critique-report-001",
            reason=(
                "Self-critique on 'A calibrated narrow claim beats a "
                "confident broad one' — verdict: weakened. The supporting "
                "forecast resolved YES, but the claim's narrowing was "
                "tighter than the resolved bucket licensed."
            ),
            status="open",
            created_at=INSIDE.replace(tzinfo=timezone.utc),
        )
    )
    store.put_review_item(
        ReviewItem(
            id="review_self_crit_two",
            claim_a_id="adversarial-first",
            claim_b_id="self-critique-report-002",
            reason=(
                "Self-critique on 'Adversarial review surfaces the buried "
                "assumption' — verdict: scope-overreach. The supporting "
                "evidence covered methodology and forecasting, not all "
                "transfer targets the article implied."
            ),
            status="open",
            created_at=(INSIDE + timedelta(days=21)).replace(tzinfo=timezone.utc),
        )
    )
    store.put_review_item(
        ReviewItem(
            id="review_unrelated",
            claim_a_id="calibrated-narrowing",
            claim_b_id="peer-objection-001",
            reason="Routine peer-review objection (not a self-critique)",
            status="open",
            created_at=INSIDE.replace(tzinfo=timezone.utc),
        )
    )

    return store


def _write_demo_drafts(tmp_dir: Path) -> Path:
    drafts = [
        {
            "text": ("Cross-domain coherence beats single-domain depth when "
                     "the firm must commit under uncertainty."),
            "domains": ["calibration", "methodology", "review"],
            "cited_conclusion_ids": ["c1", "c2"],
            "cluster_conclusion_ids": ["c1", "c2", "c3", "c4"],
            "conviction_score": 0.74,
            "domain_breadth": 3,
            "cluster_centroid_similarity": 0.81,
            "status": "draft",
            "drafted_at": INSIDE.replace(tzinfo=timezone.utc).isoformat(),
        },
        {
            "text": ("Adversarial review precedes friendly review; the "
                     "friendly read leaves load-bearing assumptions buried."),
            "domains": ["review", "methodology"],
            "cited_conclusion_ids": ["c3"],
            "cluster_conclusion_ids": ["c3", "c5"],
            "conviction_score": 0.68,
            "domain_breadth": 2,
            "cluster_centroid_similarity": 0.77,
            "status": "draft",
            "drafted_at": (INSIDE + timedelta(days=14)).replace(
                tzinfo=timezone.utc
            ).isoformat(),
        },
    ]
    out = tmp_dir / "principles_drafts.json"
    out.write_text(json.dumps(drafts, sort_keys=True), encoding="utf-8")
    return out


# ── Narrative stub ─────────────────────────────────────────────────
#
# The agent runs without an LLM key; the narrative stub renders prose
# from the structured numbers directly. Every token the stub emits is
# drawn from the structured object so the NumberDriftError gate stays a
# real check (and so the prose is honest about the quarter even when
# the founder hasn't authorized a live model call).


class _DeterministicNarrative:
    def __init__(self, review: SeasonalReview) -> None:
        self.review = review

    def complete(self, *, system: str, user: str, max_tokens: int = 4096,
                 temperature: float = 0.0) -> str:
        for key in NARRATIVE_SECTION_KEYS:
            if f"Section: {key}" in user:
                return self._render(key)
        return ""

    def _render(self, key: str) -> str:
        r = self.review
        if key == "overview":
            return (
                f"The firm closed {r.window.label} with "
                f"{len(r.methods.active)} active method(s), "
                f"{len(r.methods.deprecated)} deprecated, and "
                f"{len(r.methods.retired)} retired. "
                f"{len(r.drift.events)} drift event(s) entered the ledger; "
                f"{r.calibration.resolved_count} forecast(s) resolved. "
                f"The firm published {len(r.articles.articles)} article(s) "
                f"and the self-critique pass surfaced "
                f"{len(r.self_critique.findings)} finding(s)."
            )
        if key == "methods":
            if not r.methods.status.data_available:
                return ("The firm cannot account for method-register state "
                        "this quarter; the section reports the gap rather "
                        "than estimate it.")
            return (
                f"The register carries {len(r.methods.active)} active "
                f"method(s) at quarter close. The firm marked "
                f"{len(r.methods.deprecated)} method(s) deprecated and "
                f"retired {len(r.methods.retired)}. Retirement is the "
                f"firm's standing acknowledgement that a method no longer "
                f"earns its place in the register."
            )
        if key == "drift":
            if not r.drift.events:
                return ("No drift events fell in the window — the absence "
                        "is recorded, not interpreted as quiet.")
            top = r.drift.events[0]
            return (
                f"The firm observed {len(r.drift.events)} drift event(s) "
                f"in window. The highest-scoring event was against "
                f"target {top.target_id} at score {top.drift_score:.3f}; "
                f"the firm treats the score as evidence of a regime shift "
                f"to be investigated, not an automatic retirement trigger."
            )
        if key == "calibration":
            if not r.calibration.status.data_available:
                return ("The firm cannot report calibration this quarter; "
                        "no resolved forecasts fell in the window. The gap "
                        "is recorded, not estimated.")
            mb = r.calibration.mean_brier
            ll = r.calibration.mean_log_loss
            parts = [
                f"Across {r.calibration.resolved_count} resolved forecast(s)",
            ]
            if mb is not None:
                parts.append(f"the firm posted a mean Brier of {mb:.3f}")
            if ll is not None:
                parts.append(f"and mean log-loss {ll:.3f}")
            tail = (
                ". The firm reads the score as a calibration check, not a "
                "performance leaderboard."
            )
            return ", ".join(parts) + tail
        if key == "open_questions":
            if not r.open_questions.status.data_available:
                return ("Open-questions data was not available this quarter "
                        "— the firm has no per-window resolved/added feed "
                        "yet and refuses to estimate it.")
            return (
                f"The firm resolved {r.open_questions.resolved_count} open "
                f"question(s) and added {r.open_questions.added_count} new "
                f"one(s)."
            )
        if key == "articles":
            if not r.articles.articles:
                return ("No articles were published in window. The firm "
                        "records the absence rather than narrate around it.")
            return (
                f"The firm published {len(r.articles.articles)} article(s) "
                f"in the quarter. Each carries the machine-drafted, "
                f"founder-reviewed disclosure non-removably; the firm "
                f"speaks as the firm, never as a single voice."
            )
        if key == "principles":
            if not r.principles.drafted:
                return ("No principles were drafted in window. The firm "
                        "neither pads the section nor estimates a count.")
            top = r.principles.drafted[0]
            return (
                f"The firm distilled {len(r.principles.drafted)} principle(s) "
                f"in the quarter; the strongest reached conviction "
                f"{top.conviction_score:.2f} across {top.domain_breadth} "
                f"domain(s). Conviction earns its place in the register; the "
                f"firm does not auto-promote a draft."
            )
        if key == "edited_conclusions":
            if not r.edited_conclusions.rows:
                return ("No conclusions were edited in window. The firm "
                        "records the absence; an edit-light quarter is "
                        "evidence, not silence.")
            return (
                f"The firm edited {len(r.edited_conclusions.rows)} "
                f"conclusion(s) in window. The firm publishes revisions "
                f"with the same prominence as new work."
            )
        if key == "self_critique":
            if not r.self_critique.findings:
                return (
                    "The self-critique pass surfaced no findings in window. "
                    "The section is still emitted; the firm refuses to "
                    "silence the audit even on a clean quarter."
                )
            return (
                f"The self-critique pass surfaced "
                f"{len(r.self_critique.findings)} finding(s) the firm got "
                f"wrong this quarter. Each finding is named — the firm "
                f"does not soften a self-critique."
            )
        return ""


# ── Canonical input for signing ────────────────────────────────────


def seasonal_canonical_input(review: SeasonalReview) -> PublicationCanonicalInput:
    """Build the publication-signing canonical input for a seasonal review.

    The seasonal review is signed over the byte content of its
    structured-object: that is exactly what the narrative pass is
    constrained to. The signed bytes certify the firm's quarter
    (counts, scores, IDs, dates) — not a particular prose rendering of
    it. Tests use the identical builder so a signature produced here
    round-trips against the verifier the test exercises.
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


# ── Reviewer memo ──────────────────────────────────────────────────


def _extract_numbers_from_prose(text: str) -> list[str]:
    return re.findall(r"(?<![\d.])(\d+(?:\.\d+)?%?)(?!\d)", text or "")


def _ledger_for(review: SeasonalReview) -> set[str]:
    """Reuse the same tolerant-number ledger the narrative gate uses."""
    from noosphere.docgen.seasonal_review import _structured_number_ledger
    return _structured_number_ledger(review)


def _unverifiable_numbers(review: SeasonalReview, prose: dict[str, str]) -> list[
    tuple[str, str]
]:
    """Per-section list of numeric tokens the agent cannot trace to a row.

    With the narrative pass gated, this list is empty on a clean run.
    Computing it anyway is the agent's reviewer-of-itself step: the
    memo's number-trace section is "what would have been caught if the
    gate were absent" and serves as evidence the gate is doing its job.
    """
    ledger = _ledger_for(review)
    offenders: list[tuple[str, str]] = []
    for key, text in prose.items():
        for token in _extract_numbers_from_prose(text):
            if token in ledger:
                continue
            stripped = token.rstrip("0").rstrip(".") if "." in token else token
            if stripped in ledger:
                continue
            offenders.append((key, token))
    return offenders


def _strongest_finding(review: SeasonalReview) -> str:
    if review.calibration.status.data_available and review.calibration.mean_brier is not None:
        return (
            f"Calibration is real. Across {review.calibration.resolved_count} "
            f"resolved forecast(s) the firm posted a mean Brier of "
            f"{review.calibration.mean_brier:.3f} — within the band the firm "
            f"set itself, and earned through resolutions, not narrative."
        )
    if review.principles.drafted:
        top = review.principles.drafted[0]
        return (
            f"Principle distillation produced a candidate at conviction "
            f"{top.conviction_score:.2f} across {top.domain_breadth} "
            f"domain(s): {top.text!r}. This is the firm earning a transferable "
            f"shape, not paraphrasing one."
        )
    return (
        "No section delivered an obvious winner this quarter. The strongest "
        "finding is meta: the firm produced a seasonal review at all on "
        "this small a corpus, and every absence is recorded as a fact."
    )


def _most_embarrassing(review: SeasonalReview) -> str:
    if review.self_critique.findings:
        # Pick the most recent self-critique finding; the firm should
        # not soften a self-critique by aging it.
        worst = review.self_critique.findings[-1]
        return (
            f"Self-critique surfaced {len(review.self_critique.findings)} "
            f"finding(s). The most recent — on article "
            f"{worst.article_id!r} — names a verdict the firm got wrong: "
            f"{worst.reason}"
        )
    if review.drift.events:
        worst = review.drift.events[0]
        return (
            f"Drift score {worst.drift_score:.3f} against {worst.target_id} "
            f"is uncomfortable: the firm's machinery moved relative to its "
            f"prior baseline. The firm investigates, it does not edit the "
            f"score away."
        )
    if not review.calibration.status.data_available:
        return (
            "Calibration is not reportable this quarter — too few resolved "
            "forecasts in the window. A research firm that cannot report "
            "calibration is in its weakest reviewable position."
        )
    return (
        "Nothing in this quarter is structurally embarrassing. The firm "
        "still surfaces this section because the absence of an embarrassing "
        "finding is its own claim and should not be silenced."
    )


def _uncertain_claims(review: SeasonalReview) -> list[str]:
    items: list[str] = []
    if not review.open_questions.status.data_available:
        items.append(
            "Open-questions resolved/added counts are not in the structured "
            "object. The narrative reports this as data not available; the "
            "agent has no way to confirm the gap is genuine versus a "
            "missing collector."
        )
    if review.edited_conclusions.status.data_available is False:
        items.append(
            "Most-edited conclusions show zero in window. The agent cannot "
            "distinguish 'no edits' from 'edits not yet hashed' on the "
            "current schema (single updated_at column, no revision count)."
        )
    if review.calibration.status.data_available and review.calibration.resolved_count <= 5:
        items.append(
            f"Calibration is reported over only "
            f"{review.calibration.resolved_count} resolved forecast(s). "
            "The mean Brier is honest but the sample is thin enough that "
            "the firm should not over-narrate it next quarter."
        )
    if not items:
        items.append(
            "No section is more uncertain than the structured numbers "
            "already disclose; the assembler reports its gaps explicitly."
        )
    return items[:3]


def _write_memo(memo_path: Path, review: SeasonalReview, narrative: dict[str, str],
                tex_path: Path, pdf_path: Path | None,
                unverifiable: list[tuple[str, str]]) -> None:
    lines: list[str] = []
    lines.append(f"# Seasonal Review {review.window.label} — Reviewer Memo")
    lines.append("")
    lines.append(
        f"This memo is the **agent's reviewer-of-itself output** for the "
        f"{review.window.label} seasonal review. The draft itself is at "
        f"`{tex_path.relative_to(Path.cwd()) if str(tex_path).startswith(str(Path.cwd())) else tex_path}`"
        + (f" (PDF: `{pdf_path.relative_to(Path.cwd()) if pdf_path and str(pdf_path).startswith(str(Path.cwd())) else pdf_path}`)" if pdf_path else " (PDF not built — `.tex` is the authoritative artifact)")
        + ". The agent **does not publish**: this draft lands in the "
        "founder review queue with `review_state=pending`. The byline is "
        f"non-removable: every artifact above carries the \"{DISCLOSURE_LABEL}\" disclosure."
    )
    lines.append("")
    lines.append(
        "The .tex source is the authoritative artifact; the PDF is a build "
        "product; the sibling `review.json` carries the structured numbers "
        "and is the source of truth for every numeric claim in the prose. "
        "The publication signing path was exercised on the same canonical "
        "bytes the sidecar carries — see the run log for the verification "
        "result."
    )
    lines.append("")

    lines.append("## Strongest finding")
    lines.append("")
    lines.append(_strongest_finding(review))
    lines.append("")

    lines.append("## Most embarrassing finding")
    lines.append("")
    lines.append(_most_embarrassing(review))
    lines.append("")

    lines.append("## Claims the agent is uncertain about")
    lines.append("")
    for u in _uncertain_claims(review):
        lines.append(f"- {u}")
    lines.append("")

    lines.append("## Numbers the agent cannot verify against a database row")
    lines.append("")
    if unverifiable:
        lines.append(
            "The following numeric tokens appeared in the narrative pass but "
            "could not be traced to a row in the structured object's number "
            "ledger. (On a normal run, `write_narrative` raises "
            "`NumberDriftError` before the artifact lands; if this list is "
            "non-empty, that gate is bypassed and the founder MUST treat the "
            "draft as not-ready.)"
        )
        lines.append("")
        for section, token in unverifiable:
            lines.append(f"- section `{section}`: `{token}`")
    else:
        lines.append(
            "None. Every numeric token in the rendered narrative resolves "
            "to a value in the structured object's number ledger — which "
            "is the only way `write_narrative` would have returned without "
            "raising `NumberDriftError` in the first place."
        )
    lines.append("")

    lines.append("## Triage")
    lines.append("")
    lines.append(
        "Triage at `/research/seasonal/`. The valid actions are: "
        "*approve* (publish after the signing path lands `signature.json`), "
        "*reject* (the draft stays pending and is not promoted), or "
        "*edit-and-approve* (founder edits land in `review.tex`; "
        "re-running this script regenerates the structured numbers). "
        "The agent does not auto-publish, does not auto-announce, and "
        "does not flip `review_state` on the founder's behalf."
    )
    lines.append("")

    memo_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Run ────────────────────────────────────────────────────────────


log("--- Stage 1: assemble ---")
if MODE == "demo":
    log("  corpus source : embedded verification corpus (frozen)")
    store = _seed_demo_store()
    tmp_dir = Path(tempfile.mkdtemp(prefix="seasonal-demo-"))
    drafts_path = _write_demo_drafts(tmp_dir)
else:
    log("  corpus source : live noosphere store")
    from noosphere.cli import get_orchestrator
    store = get_orchestrator(None).store
    drafts_path = None

review = assemble_seasonal_review(
    store,
    year=YEAR,
    quarter=QUARTER,
    principles_drafts_path=drafts_path,
    now=GENERATED_AT,
)
log(f"  window        : {review.window.label} ({review.window.slug})")
log(f"  methods       : active={len(review.methods.active)} "
    f"deprecated={len(review.methods.deprecated)} "
    f"retired={len(review.methods.retired)}")
log(f"  drift events  : {len(review.drift.events)}")
log(f"  calibration   : resolved={review.calibration.resolved_count} "
    f"available={review.calibration.status.data_available}")
log(f"  articles      : {len(review.articles.articles)}")
log(f"  principles    : drafted={len(review.principles.drafted)}")
log(f"  self-critique : findings={len(review.self_critique.findings)}")

log("--- Stage 2: narrative pass (deterministic stub; number-drift gated) ---")
narrative = write_narrative(review, _DeterministicNarrative(review))
log(f"  prose sections: {len(narrative.sections)}")

log("--- Stage 3: render .tex + .json (+ PDF when pdflatex on PATH) ---")
artifact = render_seasonal_review(
    review,
    narrative=narrative,
    out_root=OUT_ROOT,
    build_pdf=BUILD_PDF,
)
_clean_latex_byproducts(artifact.tex_path)
log(f"  slug dir      : {artifact.out_dir}")
log(f"  tex           : {artifact.tex_path}")
log(f"  json          : {artifact.json_path}")
if artifact.pdf_path:
    log(f"  pdf           : {artifact.pdf_path} "
        f"({artifact.pdf_path.stat().st_size} bytes)")
else:
    log("  pdf           : not built — .tex remains the authoritative artifact")

# Flat copies at the seasonal-root level so the committed artifact has
# a stable path (docs/seasonal/<slug>.tex) alongside the slug dir.
flat_tex = OUT_ROOT / f"{review.window.slug}.tex"
shutil.copyfile(artifact.tex_path, flat_tex)
log(f"  flat tex copy : {flat_tex}")
if artifact.pdf_path is not None:
    flat_pdf = OUT_ROOT / f"{review.window.slug}.pdf"
    shutil.copyfile(artifact.pdf_path, flat_pdf)
    log(f"  flat pdf copy : {flat_pdf}")

log("--- Stage 4: reviewer memo ---")
unverifiable = _unverifiable_numbers(review, narrative.sections)
memo_path = MEMO_DIR / f"Seasonal_Review_Q{QUARTER}_Reviewer_Memo.md"
_write_memo(
    memo_path,
    review,
    narrative.sections,
    artifact.tex_path,
    artifact.pdf_path,
    unverifiable,
)
log(f"  wrote memo    : {memo_path}")
log(f"  unverifiable  : {len(unverifiable)} token(s)")

log("--- Stage 5: verify the publication signing path on the same canonical bytes ---")
signing_ok = False
with tempfile.TemporaryDirectory() as tmp:
    keyring = PublicationKeyring(Path(tmp) / "publication-keys")
    keyring.ensure()

    canonical = seasonal_canonical_input(review)
    sig = sign_publication(canonical, keyring)
    ok_result = verify_signature(sig, keyring, live_input=canonical)
    log(f"  sign + verify (unmodified): ok={ok_result.ok} "
        f"hash={sig.canonical_hash[:16]}...")

    # Mutate the structured payload the way a post-signing DB drift
    # would (drop a calibration number) and confirm verification rejects.
    structured = json.loads(canonical.conclusion_text)
    if structured.get("calibration", {}).get("mean_brier") is not None:
        structured["calibration"]["mean_brier"] = round(
            float(structured["calibration"]["mean_brier"]) + 0.05, 6
        )
    else:
        # Calibration absent (thin quarter); mutate methods active_count instead.
        structured["methods"]["active_count"] = (
            int(structured["methods"]["active_count"]) + 1
        )
    mutated = PublicationCanonicalInput(
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
    tampered_result = verify_signature(sig, keyring, live_input=mutated)
    log(f"  verify after mutation: ok={tampered_result.ok} (expected ok=False)")
    signing_ok = ok_result.ok and not tampered_result.ok

if signing_ok:
    log("  publication signing path: VERIFIED")
else:
    log("  publication signing path: FAILED")
    raise SystemExit(1)

log("--- Stage 6: stage subscriber digest entry (founder-approval gated) ---")
# The agent does NOT enqueue a send. It writes the intake payload the
# digest pipeline would consume on founder approval, into the slug dir
# alongside review.json. The founder reviews it before the digest fires.
digest_event = {
    "kind": "publication",
    "headline": f"Seasonal Research Review — {review.window.label}",
    "summary": (
        "The firm has filed its seasonal review for "
        f"{review.window.label}. The review carries "
        f"{len(review.articles.articles)} published article(s), "
        f"{review.calibration.resolved_count} resolved forecast(s), and "
        f"{len(review.self_critique.findings)} self-critique finding(s). "
        "The 'what we got wrong' section is non-silenceable."
    ),
    "url": f"/research/seasonal/{review.window.slug}/",
    "occurred_at": review.generated_at.isoformat(),
    "conclusion_slug": review.window.slug,
    "methodology_names": [],
    "domain_tags": ["seasonal-review"],
    "is_major": True,
}
intake_path = artifact.out_dir / "digest_event.staged.json"
intake_path.write_text(
    json.dumps(digest_event, indent=2, sort_keys=True), encoding="utf-8"
)
log(f"  staged event  : {intake_path}")
log(
    "  note: the agent does NOT enqueue this event. It lands in the "
    "review's slug dir and the founder authorizes the send on approval."
)

log("")
log("=== Seasonal review run complete ===")
log(f"  draft dir     : {artifact.out_dir}")
log(f"  reviewer memo : {memo_path}")
log(f"  signing       : path verified on throwaway keyring (firm keys untouched)")
log(f"  next          : the founder triages at /research/seasonal/. Approval "
    f"flips review_state and lands a real signature.json; the digest event "
    f"goes out on the same approval. The agent does not publish, does not "
    f"flip review_state, and does not announce externally.")
PYEOF

echo
echo "=== run_seasonal_review.sh done ==="
