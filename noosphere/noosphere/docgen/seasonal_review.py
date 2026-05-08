"""Quarterly research review assembler.

Two passes:

1. ``assemble_seasonal_review`` walks the firm's own machinery for one
   quarter window and produces a fully derived ``SeasonalReview``
   object — no LLM commentary, just the numbers and the names. Sections
   whose underlying data is missing are recorded with
   ``data_available=False`` and a short reason rather than estimated.
2. ``write_narrative`` runs an LLM pass over the structured object and
   produces narrative prose for each section. The prose is constrained
   to cite numbers from the structured object: every decimal-bearing
   number it emits must already appear in the structured object's
   number ledger, or :func:`render_seasonal_review` raises
   :class:`NumberDriftError`.

The PDF build reuses the same pdflatex pattern as the auto-paper
generator (``paper_generator.py``); the .tex file is the source of
truth and the .pdf is a build artifact.

The "what we got wrong" section (self-critique) cannot be silenced.
When no findings are recorded for the quarter, the section is still
emitted with the explicit string "No self-critique findings were
recorded for this quarter." rather than dropped — silence in this
section would defeat the whole point of the review being audit-ready.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_FILENAME = "seasonal_template.tex.jinja"

DEFAULT_REVIEW_ROOT = Path("docs/seasonal")
DISCLOSURE_LABEL = "machine-drafted, founder-reviewed"

# "what we got wrong" — required section; cannot be silenced. The
# string below is the canonical empty-state placeholder so tests can
# assert it on a quarter with no findings.
SELF_CRITIQUE_EMPTY_NOTE = (
    "No self-critique findings were recorded for this quarter."
)
DATA_NOT_AVAILABLE_NOTE = "data not available"


# ── LaTeX escape (shared shape with paper_generator) ────────────────

_TEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_escape(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    return "".join(_TEX_SPECIAL.get(ch, ch) for ch in s)


# ── Quarter window helpers ──────────────────────────────────────────


@dataclass(frozen=True)
class QuarterWindow:
    """Inclusive-start, exclusive-end UTC window covering one quarter."""

    year: int
    quarter: int  # 1..4
    start: datetime  # inclusive, UTC-aware
    end: datetime  # exclusive, UTC-aware

    @property
    def label(self) -> str:
        return f"{self.year} Q{self.quarter}"

    @property
    def slug(self) -> str:
        return f"{self.year}_Q{self.quarter}_Review"


def quarter_window(year: int, quarter: int) -> QuarterWindow:
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1..4, got {quarter!r}")
    start_month = (quarter - 1) * 3 + 1
    start = datetime(year, start_month, 1, tzinfo=timezone.utc)
    if quarter == 4:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, start_month + 3, 1, tzinfo=timezone.utc)
    return QuarterWindow(year=year, quarter=quarter, start=start, end=end)


def parse_quarter(text: str) -> QuarterWindow:
    """Parse ``2026Q2``/``2026-Q2``/``2026 Q2`` to a QuarterWindow."""
    m = re.match(r"^\s*(\d{4})\s*[-_ ]?\s*Q?([1-4])\s*$", text or "", re.I)
    if not m:
        raise ValueError(f"cannot parse quarter spec {text!r}; want e.g. 2026Q2")
    return quarter_window(int(m.group(1)), int(m.group(2)))


# ── Section dataclasses ─────────────────────────────────────────────


@dataclass(frozen=True)
class SectionStatus:
    """Whether a section's underlying data was available for the quarter."""

    data_available: bool
    note: str = ""


@dataclass(frozen=True)
class MethodPerformanceRow:
    method_id: str
    name: str
    version: str
    status: str  # experimental | active | deprecated | retired


@dataclass(frozen=True)
class MethodsSection:
    status: SectionStatus
    active: tuple[MethodPerformanceRow, ...] = ()
    deprecated: tuple[MethodPerformanceRow, ...] = ()
    retired: tuple[MethodPerformanceRow, ...] = ()


@dataclass(frozen=True)
class DriftRow:
    target_id: str
    drift_score: float
    observed_at: date
    notes: str


@dataclass(frozen=True)
class DriftSection:
    status: SectionStatus
    events: tuple[DriftRow, ...] = ()


@dataclass(frozen=True)
class CalibrationSection:
    status: SectionStatus
    resolved_count: int = 0
    mean_brier: Optional[float] = None
    mean_log_loss: Optional[float] = None


@dataclass(frozen=True)
class OpenQuestionsSection:
    status: SectionStatus
    resolved_count: int = 0
    added_count: int = 0


@dataclass(frozen=True)
class ArticleRow:
    slug: str
    title: str
    published_at: datetime


@dataclass(frozen=True)
class ArticlesSection:
    status: SectionStatus
    articles: tuple[ArticleRow, ...] = ()


@dataclass(frozen=True)
class PrincipleRow:
    text: str
    domain_breadth: int
    conviction_score: float


@dataclass(frozen=True)
class PrinciplesSection:
    status: SectionStatus
    drafted: tuple[PrincipleRow, ...] = ()


@dataclass(frozen=True)
class EditedConclusionRow:
    conclusion_id: str
    text_excerpt: str
    edits_in_window: int


@dataclass(frozen=True)
class EditedConclusionsSection:
    status: SectionStatus
    rows: tuple[EditedConclusionRow, ...] = ()


@dataclass(frozen=True)
class SelfCritiqueRow:
    review_item_id: str
    article_id: str
    reason: str
    created_at: datetime


@dataclass(frozen=True)
class SelfCritiqueSection:
    """Required section. ``status.data_available`` is True even when the
    findings list is empty — the section is *always* emitted; what
    varies is whether any findings were recorded.
    """

    status: SectionStatus
    findings: tuple[SelfCritiqueRow, ...] = ()


# ── Top-level review ───────────────────────────────────────────────


@dataclass(frozen=True)
class SeasonalReview:
    window: QuarterWindow
    generated_at: datetime
    methods: MethodsSection
    drift: DriftSection
    calibration: CalibrationSection
    open_questions: OpenQuestionsSection
    articles: ArticlesSection
    principles: PrinciplesSection
    edited_conclusions: EditedConclusionsSection
    self_critique: SelfCritiqueSection

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": {
                "year": self.window.year,
                "quarter": self.window.quarter,
                "label": self.window.label,
                "slug": self.window.slug,
                "start": self.window.start.isoformat(),
                "end": self.window.end.isoformat(),
            },
            "generated_at": self.generated_at.isoformat(),
            "methods": _methods_dict(self.methods),
            "drift": _drift_dict(self.drift),
            "calibration": _calibration_dict(self.calibration),
            "open_questions": _open_questions_dict(self.open_questions),
            "articles": _articles_dict(self.articles),
            "principles": _principles_dict(self.principles),
            "edited_conclusions": _edited_dict(self.edited_conclusions),
            "self_critique": _self_critique_dict(self.self_critique),
        }


def _section_dict(section: SectionStatus) -> dict[str, Any]:
    return {"data_available": section.data_available, "note": section.note}


def _methods_dict(s: MethodsSection) -> dict[str, Any]:
    def row(r: MethodPerformanceRow) -> dict[str, Any]:
        return {
            "method_id": r.method_id,
            "name": r.name,
            "version": r.version,
            "status": r.status,
        }

    return {
        "status": _section_dict(s.status),
        "active_count": len(s.active),
        "deprecated_count": len(s.deprecated),
        "retired_count": len(s.retired),
        "active": [row(r) for r in s.active],
        "deprecated": [row(r) for r in s.deprecated],
        "retired": [row(r) for r in s.retired],
    }


def _drift_dict(s: DriftSection) -> dict[str, Any]:
    return {
        "status": _section_dict(s.status),
        "event_count": len(s.events),
        "events": [
            {
                "target_id": e.target_id,
                "drift_score": e.drift_score,
                "observed_at": e.observed_at.isoformat(),
                "notes": e.notes,
            }
            for e in s.events
        ],
    }


def _calibration_dict(s: CalibrationSection) -> dict[str, Any]:
    return {
        "status": _section_dict(s.status),
        "resolved_count": s.resolved_count,
        "mean_brier": s.mean_brier,
        "mean_log_loss": s.mean_log_loss,
    }


def _open_questions_dict(s: OpenQuestionsSection) -> dict[str, Any]:
    return {
        "status": _section_dict(s.status),
        "resolved_count": s.resolved_count,
        "added_count": s.added_count,
    }


def _articles_dict(s: ArticlesSection) -> dict[str, Any]:
    return {
        "status": _section_dict(s.status),
        "article_count": len(s.articles),
        "articles": [
            {
                "slug": a.slug,
                "title": a.title,
                "published_at": a.published_at.isoformat(),
            }
            for a in s.articles
        ],
    }


def _principles_dict(s: PrinciplesSection) -> dict[str, Any]:
    return {
        "status": _section_dict(s.status),
        "drafted_count": len(s.drafted),
        "drafted": [
            {
                "text": p.text,
                "domain_breadth": p.domain_breadth,
                "conviction_score": p.conviction_score,
            }
            for p in s.drafted
        ],
    }


def _edited_dict(s: EditedConclusionsSection) -> dict[str, Any]:
    return {
        "status": _section_dict(s.status),
        "row_count": len(s.rows),
        "rows": [
            {
                "conclusion_id": r.conclusion_id,
                "text_excerpt": r.text_excerpt,
                "edits_in_window": r.edits_in_window,
            }
            for r in s.rows
        ],
    }


def _self_critique_dict(s: SelfCritiqueSection) -> dict[str, Any]:
    return {
        "status": _section_dict(s.status),
        "finding_count": len(s.findings),
        "findings": [
            {
                "review_item_id": f.review_item_id,
                "article_id": f.article_id,
                "reason": f.reason,
                "created_at": f.created_at.isoformat(),
            }
            for f in s.findings
        ],
    }


# ── Assembler ──────────────────────────────────────────────────────


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _within(dt: datetime, window: QuarterWindow) -> bool:
    aware = _utc(dt)
    return window.start <= aware < window.end


def _safe_call(label: str, fn) -> Any:
    """Return fn() or None on any exception. Lets a missing/legacy
    store method drop a section to "data not available" without
    crashing the whole review.
    """
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("seasonal_review.%s: %s", label, exc)
        return None


def _collect_methods(store: Any, window: QuarterWindow) -> MethodsSection:
    methods = _safe_call("list_methods", lambda: store.list_methods())
    if methods is None:
        return MethodsSection(
            status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE)
        )
    by_status: dict[str, list[MethodPerformanceRow]] = {
        "active": [],
        "deprecated": [],
        "retired": [],
        "experimental": [],
    }
    for m in methods:
        row = MethodPerformanceRow(
            method_id=getattr(m, "method_id", ""),
            name=getattr(m, "name", ""),
            version=getattr(m, "version", ""),
            status=str(getattr(m, "status", "")),
        )
        by_status.setdefault(row.status, []).append(row)
    if not methods:
        return MethodsSection(
            status=SectionStatus(False, "no methods registered"),
        )
    active = tuple(by_status.get("active", []) + by_status.get("experimental", []))
    return MethodsSection(
        status=SectionStatus(True, ""),
        active=active,
        deprecated=tuple(by_status.get("deprecated", [])),
        retired=tuple(by_status.get("retired", [])),
    )


def _collect_drift(store: Any, window: QuarterWindow) -> DriftSection:
    events = _safe_call("list_drift_events", lambda: store.list_drift_events())
    if events is None:
        return DriftSection(status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE))
    in_window: list[DriftRow] = []
    for e in events:
        observed = getattr(e, "observed_at", None)
        if observed is None:
            continue
        as_dt = (
            datetime.combine(observed, datetime.min.time(), tzinfo=timezone.utc)
            if isinstance(observed, date) and not isinstance(observed, datetime)
            else _utc(observed)
        )
        if not _within(as_dt, window):
            continue
        in_window.append(
            DriftRow(
                target_id=str(getattr(e, "target_id", "")),
                drift_score=float(getattr(e, "drift_score", 0.0)),
                observed_at=observed if isinstance(observed, date)
                else as_dt.date(),
                notes=str(getattr(e, "notes", "")),
            )
        )
    in_window.sort(key=lambda r: (-r.drift_score, r.target_id))
    if not in_window:
        # Drift is a regularly-emitted signal; empty window is still
        # "available data, none observed" rather than missing data.
        return DriftSection(status=SectionStatus(True, ""), events=())
    return DriftSection(status=SectionStatus(True, ""), events=tuple(in_window))


def _collect_calibration(store: Any, window: QuarterWindow) -> CalibrationSection:
    from sqlmodel import select

    from noosphere.models import ForecastResolution

    def _query() -> list[ForecastResolution]:
        with store.session() as s:
            return list(
                s.exec(
                    select(ForecastResolution).where(
                        ForecastResolution.resolved_at >= window.start.replace(tzinfo=None)
                    ).where(
                        ForecastResolution.resolved_at < window.end.replace(tzinfo=None)
                    )
                ).all()
            )

    rows = _safe_call("forecast_resolutions", _query)
    if rows is None:
        return CalibrationSection(
            status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE)
        )
    if not rows:
        return CalibrationSection(
            status=SectionStatus(
                False,
                "no resolved forecasts in window",
            )
        )
    briers = [r.brier_score for r in rows if r.brier_score is not None]
    log_losses = [r.log_loss for r in rows if r.log_loss is not None]
    return CalibrationSection(
        status=SectionStatus(True, ""),
        resolved_count=len(rows),
        mean_brier=sum(briers) / len(briers) if briers else None,
        mean_log_loss=sum(log_losses) / len(log_losses) if log_losses else None,
    )


def _collect_open_questions(
    store: Any, window: QuarterWindow
) -> OpenQuestionsSection:
    """The firm tracks open questions as a derived view rather than as
    a first-class store table. Without a quarterly-resolved/added feed,
    we report "data not available" — consistent with the constraint
    that missing metrics are omitted, not estimated.
    """
    fetcher = getattr(store, "list_open_questions_for_window", None)
    if fetcher is None:
        return OpenQuestionsSection(
            status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE)
        )
    payload = _safe_call("list_open_questions_for_window", lambda: fetcher(window))
    if payload is None:
        return OpenQuestionsSection(
            status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE)
        )
    return OpenQuestionsSection(
        status=SectionStatus(True, ""),
        resolved_count=int(payload.get("resolved_count", 0)),
        added_count=int(payload.get("added_count", 0)),
    )


def _collect_articles(store: Any, window: QuarterWindow) -> ArticlesSection:
    from sqlmodel import select

    from noosphere.models import PublishedConclusion

    def _query() -> list[PublishedConclusion]:
        with store.session() as s:
            return list(
                s.exec(
                    select(PublishedConclusion)
                    .where(PublishedConclusion.kind == "ARTICLE")
                    .where(
                        PublishedConclusion.published_at
                        >= window.start.replace(tzinfo=None)
                    )
                    .where(
                        PublishedConclusion.published_at
                        < window.end.replace(tzinfo=None)
                    )
                    .order_by(PublishedConclusion.published_at)
                ).all()
            )

    rows = _safe_call("published_articles", _query)
    if rows is None:
        return ArticlesSection(
            status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE)
        )
    if not rows:
        return ArticlesSection(
            status=SectionStatus(False, "no articles published in window")
        )
    out: list[ArticleRow] = []
    for r in rows:
        title = r.slug
        try:
            payload = json.loads(r.payload_json) if r.payload_json else {}
            article_block = payload.get("article") if isinstance(payload, dict) else {}
            if isinstance(article_block, dict):
                t = article_block.get("headline") or payload.get("conclusionText")
                if t:
                    title = str(t)
        except Exception:
            pass
        published = _utc(r.published_at)
        out.append(
            ArticleRow(
                slug=str(r.slug),
                title=str(title)[:240],
                published_at=published,
            )
        )
    return ArticlesSection(status=SectionStatus(True, ""), articles=tuple(out))


def _collect_principles(
    store: Any,
    window: QuarterWindow,
    *,
    drafts_path: Optional[Path] = None,
) -> PrinciplesSection:
    """Principle distillation produces a JSON drafts file (see
    ``noosphere principles distill --out``) rather than persisting
    directly to the store. If ``drafts_path`` is provided we read it;
    otherwise we report data not available — never estimated.
    """
    if drafts_path is None:
        return PrinciplesSection(
            status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE)
        )
    p = Path(drafts_path)
    if not p.exists():
        return PrinciplesSection(
            status=SectionStatus(False, f"drafts file not found: {p}")
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return PrinciplesSection(
            status=SectionStatus(False, f"drafts file not parsable: {p}")
        )
    if not isinstance(data, list):
        return PrinciplesSection(
            status=SectionStatus(False, f"drafts file is not a JSON array: {p}")
        )
    drafted: list[PrincipleRow] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        drafted_at_raw = row.get("drafted_at")
        if drafted_at_raw:
            try:
                dt = datetime.fromisoformat(str(drafted_at_raw).replace("Z", "+00:00"))
                if not _within(dt, window):
                    continue
            except ValueError:
                pass
        drafted.append(
            PrincipleRow(
                text=str(row.get("text", "")),
                domain_breadth=int(row.get("domain_breadth", 0)),
                conviction_score=float(row.get("conviction_score", 0.0)),
            )
        )
    if not drafted:
        return PrinciplesSection(
            status=SectionStatus(False, "no principles drafted in window")
        )
    drafted.sort(key=lambda r: -r.conviction_score)
    return PrinciplesSection(
        status=SectionStatus(True, ""), drafted=tuple(drafted)
    )


def _collect_edited_conclusions(
    store: Any, window: QuarterWindow
) -> EditedConclusionsSection:
    fetcher = getattr(store, "list_conclusions", None)
    if fetcher is None:
        return EditedConclusionsSection(
            status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE)
        )
    conclusions = _safe_call("list_conclusions", fetcher)
    if conclusions is None:
        return EditedConclusionsSection(
            status=SectionStatus(False, DATA_NOT_AVAILABLE_NOTE)
        )
    edited: list[EditedConclusionRow] = []
    for c in conclusions:
        updated = getattr(c, "updated_at", None)
        created = getattr(c, "created_at", None)
        if updated is None:
            continue
        if not _within(updated, window):
            continue
        # An edit (vs initial creation) is "updated_at strictly after
        # created_at and the update fell in the quarter window".
        if created is not None and _utc(updated) <= _utc(created):
            continue
        text = (getattr(c, "text", "") or "")[:200]
        # The Conclusion model exposes only a single ``updated_at`` —
        # there is no revision count column. We record one edit per
        # in-window update; downstream the row count itself signals
        # how active the quarter was.
        edited.append(
            EditedConclusionRow(
                conclusion_id=str(getattr(c, "id", "")),
                text_excerpt=text,
                edits_in_window=1,
            )
        )
    if not edited:
        return EditedConclusionsSection(
            status=SectionStatus(False, "no conclusions edited in window")
        )
    edited.sort(key=lambda r: r.conclusion_id)
    return EditedConclusionsSection(
        status=SectionStatus(True, ""), rows=tuple(edited)
    )


_SELF_CRITIQUE_REASON_PREFIX = "Self-critique on"


def _collect_self_critique(
    store: Any, window: QuarterWindow
) -> SelfCritiqueSection:
    """Required section. Pulls open ``ReviewItem`` rows whose ``reason``
    starts with the self-critique prefix
    (see ``scheduler_self_critique._finding_reason``) and that were
    created in the window.
    """
    fetcher = getattr(store, "list_open_review_items", None)
    if fetcher is None:
        # Even when the queue surface is missing the section is still
        # emitted; the spec is explicit that it cannot be silenced.
        return SelfCritiqueSection(
            status=SectionStatus(True, DATA_NOT_AVAILABLE_NOTE),
        )
    items = _safe_call("list_open_review_items", fetcher) or []
    findings: list[SelfCritiqueRow] = []
    for item in items:
        reason = str(getattr(item, "reason", "") or "")
        if not reason.startswith(_SELF_CRITIQUE_REASON_PREFIX):
            continue
        created_at = getattr(item, "created_at", None)
        if created_at is None or not _within(created_at, window):
            continue
        findings.append(
            SelfCritiqueRow(
                review_item_id=str(getattr(item, "id", "")),
                article_id=str(getattr(item, "claim_a_id", "")),
                reason=reason,
                created_at=_utc(created_at),
            )
        )
    findings.sort(key=lambda r: r.created_at)
    return SelfCritiqueSection(
        status=SectionStatus(True, ""), findings=tuple(findings)
    )


def assemble_seasonal_review(
    store: Any,
    *,
    year: int,
    quarter: int,
    principles_drafts_path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> SeasonalReview:
    """Assemble the structured review for ``year`` Q``quarter``.

    Pure derivation — no LLM calls. Sections whose underlying data is
    missing for the window are marked ``data_available=False`` rather
    than estimated.
    """
    window = quarter_window(year, quarter)
    return SeasonalReview(
        window=window,
        generated_at=_utc(now or datetime.now(timezone.utc)),
        methods=_collect_methods(store, window),
        drift=_collect_drift(store, window),
        calibration=_collect_calibration(store, window),
        open_questions=_collect_open_questions(store, window),
        articles=_collect_articles(store, window),
        principles=_collect_principles(
            store, window, drafts_path=principles_drafts_path
        ),
        edited_conclusions=_collect_edited_conclusions(store, window),
        self_critique=_collect_self_critique(store, window),
    )


# ── Narrative writer ────────────────────────────────────────────────


SEASONAL_VOICE_SYSTEM_PROMPT = (
    "You write quarterly research-review prose in the firm's voice. The "
    "firm reasons collectively: write 'the firm holds', 'the firm "
    "observed', 'the firm revised'. Never speak as an individual "
    "founder. Do not narrate what each section says in sequence — "
    "argue from the numbers. Do not write a recap.\n\n"
    "Hard constraint: every numeric value you emit must already appear "
    "in the structured object handed to you. You may not introduce a "
    "new percentage, count, ratio, or score. If a section has "
    "data_available=false, write one sentence acknowledging the gap "
    "(no estimate). For the self-critique section: never soften or "
    "omit findings — name what the firm got wrong."
)


class LLMLike(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str: ...


# Section keys the narrative pass produces. Kept as a tuple so the
# template's loop over sections is order-stable across runs.
NARRATIVE_SECTION_KEYS: tuple[str, ...] = (
    "overview",
    "methods",
    "drift",
    "calibration",
    "open_questions",
    "articles",
    "principles",
    "edited_conclusions",
    "self_critique",
)


def _section_user_prompt(review: SeasonalReview, key: str) -> str:
    """Build the user-side prompt for one section.

    The prompt embeds the structured-object slice as JSON so the LLM
    can quote numbers verbatim; the system prompt forbids inventing
    new ones.
    """
    payload = review.to_dict()
    if key == "overview":
        slice_payload = {
            "window": payload["window"],
            "methods_summary": {
                "active_count": payload["methods"]["active_count"],
                "deprecated_count": payload["methods"]["deprecated_count"],
                "retired_count": payload["methods"]["retired_count"],
            },
            "drift_event_count": payload["drift"]["event_count"],
            "calibration": payload["calibration"],
            "articles_count": payload["articles"]["article_count"],
            "self_critique_count": payload["self_critique"]["finding_count"],
        }
    else:
        slice_payload = payload[key]
    return (
        f"Quarter: {review.window.label}\n"
        f"Section: {key}\n\n"
        f"Structured slice (cite only these numbers):\n"
        f"{json.dumps(slice_payload, indent=2, default=str)}\n\n"
        "Write 80-220 words of prose for this section in the firm's "
        "voice. Do not include section headings; the renderer adds "
        "them. Do not invent numbers. Do not estimate."
    )


@dataclass(frozen=True)
class NarrativeProse:
    sections: dict[str, str]

    def get(self, key: str, default: str = "") -> str:
        return self.sections.get(key, default)


class NumberDriftError(RuntimeError):
    """Raised when narrative prose contains a numeric value that does
    not appear in the structured-object's number ledger.
    """


# Numbers we accept as "trivially universal" and so don't require
# the structured object to authorize: 0..9 and small year fragments
# like "2026" only when they match the review year. The grammar is
# intentionally narrow — anything decimal-bearing must come from the
# structured object.
_NUMBER_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?%?)(?!\d)")


def _structured_number_ledger(review: SeasonalReview) -> set[str]:
    """The set of numeric tokens the narrative is allowed to emit.

    Includes integers and floats from every counted/scored field in
    the structured object, plus simple variants ("3", "3.0", "3.00").
    """
    ledger: set[str] = set()

    def add_int(n: int) -> None:
        ledger.add(str(n))

    def add_float(x: float) -> None:
        for fmt in (f"{x:.0f}", f"{x:.1f}", f"{x:.2f}", f"{x:.3f}"):
            ledger.add(fmt)
            if "." in fmt:
                ledger.add(fmt.rstrip("0").rstrip("."))
        # Percentage-rounded variant.
        ledger.add(f"{round(x * 100):.0f}")

    payload = review.to_dict()
    add_int(review.window.year)
    add_int(review.window.quarter)
    for section_key in (
        "methods",
        "drift",
        "calibration",
        "open_questions",
        "articles",
        "principles",
        "edited_conclusions",
        "self_critique",
    ):
        section = payload[section_key]
        for k, v in section.items():
            if k == "status":
                continue
            if isinstance(v, int):
                add_int(v)
            elif isinstance(v, float):
                add_float(v)
            elif isinstance(v, list):
                add_int(len(v))
                for row in v:
                    if not isinstance(row, dict):
                        continue
                    for sub in row.values():
                        if isinstance(sub, int):
                            add_int(sub)
                        elif isinstance(sub, float):
                            add_float(sub)
    # Single-digit literals are common in prose ("a single", "two") —
    # we still allow 0-9 so phrasing like "across 4 active methods"
    # stays stable. The constraint stings only for invented decimals
    # or counts that do not match the ledger.
    for n in range(0, 10):
        ledger.add(str(n))
    return ledger


def _check_no_invented_numbers(prose: str, ledger: set[str]) -> list[str]:
    """Return numeric tokens in ``prose`` that are NOT in ``ledger``."""
    offenders: list[str] = []
    for match in _NUMBER_RE.finditer(prose or ""):
        token = match.group(1)
        if token in ledger:
            continue
        # Drop trailing zeroes for tolerant matching: "0.30" → "0.3".
        if "." in token:
            stripped = token.rstrip("0").rstrip(".") or "0"
            if stripped in ledger:
                continue
        offenders.append(token)
    return offenders


def write_narrative(
    review: SeasonalReview,
    llm_client: LLMLike,
    *,
    max_tokens: int = 800,
    temperature: float = 0.0,
) -> NarrativeProse:
    """Generate narrative prose for each section, validating that no
    numeric value is invented relative to the structured object.

    Drift between the prose and the structured object is a *build*
    failure — the function raises :class:`NumberDriftError` rather
    than silently shipping fabricated numbers.
    """
    ledger = _structured_number_ledger(review)
    sections: dict[str, str] = {}
    for key in NARRATIVE_SECTION_KEYS:
        prose = llm_client.complete(
            system=SEASONAL_VOICE_SYSTEM_PROMPT,
            user=_section_user_prompt(review, key),
            max_tokens=max_tokens,
            temperature=temperature,
        ).strip()
        offenders = _check_no_invented_numbers(prose, ledger)
        if offenders:
            raise NumberDriftError(
                f"narrative section {key!r} introduced numbers not in "
                f"the structured object: {sorted(set(offenders))!r}"
            )
        sections[key] = prose
    return NarrativeProse(sections=sections)


# ── LaTeX rendering ────────────────────────────────────────────────


def _build_template_context(
    review: SeasonalReview,
    narrative: Optional[NarrativeProse],
) -> dict[str, Any]:
    payload = review.to_dict()
    prose = (narrative.sections if narrative else {})

    def section_ctx(key: str) -> dict[str, Any]:
        sect = payload[key]
        return {
            "available": sect["status"]["data_available"],
            "note_tex": tex_escape(sect["status"]["note"]),
            "data": sect,
            "prose_tex": tex_escape(prose.get(key, "")),
        }

    return {
        "review": {
            "window_label_tex": tex_escape(review.window.label),
            "slug": review.window.slug,
            "slug_tex": tex_escape(review.window.slug),
            "generated_at_tex": tex_escape(
                review.generated_at.strftime("%Y-%m-%d %H:%M UTC")
            ),
            "disclosure_tex": tex_escape(DISCLOSURE_LABEL),
            "overview_prose_tex": tex_escape(prose.get("overview", "")),
            "self_critique_empty_note_tex": tex_escape(SELF_CRITIQUE_EMPTY_NOTE),
            "methods": {
                **section_ctx("methods"),
                "active": [
                    {
                        "name_tex": tex_escape(r["name"]),
                        "version_tex": tex_escape(r["version"]),
                        "method_id_tex": tex_escape(r["method_id"]),
                    }
                    for r in payload["methods"]["active"]
                ],
                "deprecated": [
                    {
                        "name_tex": tex_escape(r["name"]),
                        "version_tex": tex_escape(r["version"]),
                        "method_id_tex": tex_escape(r["method_id"]),
                    }
                    for r in payload["methods"]["deprecated"]
                ],
                "retired": [
                    {
                        "name_tex": tex_escape(r["name"]),
                        "version_tex": tex_escape(r["version"]),
                        "method_id_tex": tex_escape(r["method_id"]),
                    }
                    for r in payload["methods"]["retired"]
                ],
            },
            "drift": {
                **section_ctx("drift"),
                "events": [
                    {
                        "target_id_tex": tex_escape(e["target_id"]),
                        "drift_score_tex": f"{e['drift_score']:.3f}",
                        "observed_at_tex": tex_escape(e["observed_at"]),
                        "notes_tex": tex_escape(e["notes"]),
                    }
                    for e in payload["drift"]["events"]
                ],
            },
            "calibration": section_ctx("calibration"),
            "open_questions": section_ctx("open_questions"),
            "articles": {
                **section_ctx("articles"),
                "articles": [
                    {
                        "slug_tex": tex_escape(a["slug"]),
                        "title_tex": tex_escape(a["title"]),
                        "published_at_tex": tex_escape(a["published_at"][:10]),
                    }
                    for a in payload["articles"]["articles"]
                ],
            },
            "principles": {
                **section_ctx("principles"),
                "drafted": [
                    {
                        "text_tex": tex_escape(p["text"]),
                        "domain_breadth_tex": str(p["domain_breadth"]),
                        "conviction_score_tex": f"{p['conviction_score']:.2f}",
                    }
                    for p in payload["principles"]["drafted"]
                ],
            },
            "edited_conclusions": {
                **section_ctx("edited_conclusions"),
                "rows": [
                    {
                        "conclusion_id_tex": tex_escape(r["conclusion_id"]),
                        "text_excerpt_tex": tex_escape(r["text_excerpt"]),
                        "edits_in_window_tex": str(r["edits_in_window"]),
                    }
                    for r in payload["edited_conclusions"]["rows"]
                ],
            },
            "self_critique": {
                **section_ctx("self_critique"),
                "findings": [
                    {
                        "review_item_id_tex": tex_escape(f["review_item_id"]),
                        "article_id_tex": tex_escape(f["article_id"]),
                        "reason_tex": tex_escape(f["reason"]),
                    }
                    for f in payload["self_critique"]["findings"]
                ],
            },
        }
    }


def _render_template(context: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
        block_start_string="\\BLOCK{",
        block_end_string="}",
        variable_start_string="\\VAR{",
        variable_end_string="}",
        comment_start_string="\\#{",
        comment_end_string="}",
        line_statement_prefix="%%",
        line_comment_prefix="%#",
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(_TEMPLATE_FILENAME)
    return template.render(**context)


# ── Output artifact ─────────────────────────────────────────────────


@dataclass(frozen=True)
class SeasonalReviewArtifact:
    slug: str
    out_dir: Path
    tex_path: Path
    json_path: Path
    pdf_path: Optional[Path]
    review_state: str  # pending | approved | published
    pdflatex_log: Optional[str] = None


def _run_pdflatex(out_dir: Path, tex_path: Path) -> tuple[Optional[Path], str]:
    if shutil.which("pdflatex") is None:
        return None, "pdflatex not on PATH; .tex remains the source of truth"
    try:
        proc = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                str(out_dir),
                str(tex_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:  # pragma: no cover - environment-dependent
        return None, f"pdflatex invocation failed: {exc!r}"
    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        return None, log
    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.exists():
        return None, log
    return pdf_path, log


def render_seasonal_review(
    review: SeasonalReview,
    *,
    narrative: Optional[NarrativeProse] = None,
    out_root: Path = DEFAULT_REVIEW_ROOT,
    build_pdf: bool = True,
) -> SeasonalReviewArtifact:
    """Render the structured review (and optional narrative prose) to
    ``<out_root>/<slug>/`` as ``review.tex`` + ``review.json``.

    The .tex file is the narrative-bearing artifact; the .json file is
    the structured object the web view consumes. Both are written
    every run; the PDF is best-effort.
    """
    if narrative is not None:
        ledger = _structured_number_ledger(review)
        for key, prose in narrative.sections.items():
            offenders = _check_no_invented_numbers(prose, ledger)
            if offenders:
                raise NumberDriftError(
                    f"narrative section {key!r} contains numbers not in "
                    f"the structured object: {sorted(set(offenders))!r}"
                )

    context = _build_template_context(review, narrative)
    tex_body = _render_template(context)

    out_dir = Path(out_root) / review.window.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / "review.tex"
    json_path = out_dir / "review.json"
    tex_path.write_text(tex_body, encoding="utf-8")

    sidecar = {
        "slug": review.window.slug,
        "window": {
            "year": review.window.year,
            "quarter": review.window.quarter,
            "label": review.window.label,
            "start": review.window.start.isoformat(),
            "end": review.window.end.isoformat(),
        },
        "generated_at": review.generated_at.isoformat(),
        "structured": review.to_dict(),
        "narrative": (
            narrative.sections if narrative else {}
        ),
        "disclosure": DISCLOSURE_LABEL,
        "review_state": "pending",
    }
    json_path.write_text(json.dumps(sidecar, indent=2, default=str), encoding="utf-8")

    pdf_path: Optional[Path] = None
    log: Optional[str] = None
    if build_pdf:
        pdf_path, log = _run_pdflatex(out_dir, tex_path)

    return SeasonalReviewArtifact(
        slug=review.window.slug,
        out_dir=out_dir,
        tex_path=tex_path,
        json_path=json_path,
        pdf_path=pdf_path,
        review_state="pending",
        pdflatex_log=log,
    )


# ── Founder triage ──────────────────────────────────────────────────


_ALLOWED_REVIEW_STATES = {"pending", "approved", "rejected", "published"}


def discover_seasonal_reviews(
    out_root: Path = DEFAULT_REVIEW_ROOT,
) -> list[dict[str, Any]]:
    """List existing reviews under ``out_root`` for the founder queue."""
    drafts: list[dict[str, Any]] = []
    if not Path(out_root).exists():
        return drafts
    for child in sorted(Path(out_root).iterdir()):
        if not child.is_dir():
            continue
        sidecar_path = child / "review.json"
        if not sidecar_path.exists():
            continue
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        data.setdefault("slug", child.name)
        data["tex_path"] = str(child / "review.tex")
        pdf = child / "review.pdf"
        data["pdf_path"] = str(pdf) if pdf.exists() else None
        drafts.append(data)
    return drafts


def set_review_state(
    *,
    out_root: Path,
    slug: str,
    review_state: str,
    reviewer: Optional[str] = None,
) -> dict[str, Any]:
    """Update ``review.json``'s review_state. Sign-off (``approved``
    or ``published``) is required before the public surface treats
    the review as anything other than a pending draft.
    """
    if review_state not in _ALLOWED_REVIEW_STATES:
        raise ValueError(
            f"review_state {review_state!r} not in {sorted(_ALLOWED_REVIEW_STATES)}"
        )
    sidecar = Path(out_root) / slug / "review.json"
    if not sidecar.exists():
        raise FileNotFoundError(f"seasonal review sidecar not found: {sidecar}")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    data["review_state"] = review_state
    if reviewer:
        data["reviewer"] = reviewer
    data["review_updated_at"] = datetime.now(timezone.utc).isoformat()
    sidecar.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return data


__all__ = [
    "DATA_NOT_AVAILABLE_NOTE",
    "DEFAULT_REVIEW_ROOT",
    "DISCLOSURE_LABEL",
    "NARRATIVE_SECTION_KEYS",
    "NumberDriftError",
    "QuarterWindow",
    "SELF_CRITIQUE_EMPTY_NOTE",
    "SEASONAL_VOICE_SYSTEM_PROMPT",
    "SeasonalReview",
    "SeasonalReviewArtifact",
    "NarrativeProse",
    "assemble_seasonal_review",
    "discover_seasonal_reviews",
    "parse_quarter",
    "quarter_window",
    "render_seasonal_review",
    "set_review_state",
    "tex_escape",
    "write_narrative",
]
