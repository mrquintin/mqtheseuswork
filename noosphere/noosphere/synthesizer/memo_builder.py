"""Memo builder — Round 19 prompt 11.

The synthesizer (prompt 10) emits a structured
:class:`~noosphere.synthesizer.engine.SynthesisResult`. The memo
builder takes that result, renders the canonical 10-section
investment-memo body, validates the body against the section
contract, persists an :class:`~noosphere.models.InvestmentMemo` row,
writes markdown to disk under ``docs/memos/<yyyy>/<mm>/``, and shells
out to the pdflatex pipeline to produce the PDF.

The builder is the single place memos are produced — both the
synthesizer engine (when an operator runs a query) and the CLI
``noosphere memo build`` command call it. Memos always start in
:attr:`MemoStatus.DRAFT`; lifecycle transitions are operator-driven
via :func:`send_memo` / :func:`archive_memo` / :func:`publish_memo`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from noosphere.models import (
    InvestmentMemo,
    MemoQuestionType,
    MemoStatus,
    Principle,
    ProvenanceKind,
    coerce_provenance,
    memo_paths,
    memo_slug,
)
from noosphere.synthesizer.memo_pdf import build_memo_pdf
from noosphere.synthesizer.memo_validator import (
    MemoValidationError,
    validate_memo_body,
)


logger = logging.getLogger(__name__)


_REPO_ROOT = Path(__file__).resolve().parents[3]


# ── Question type bridging ─────────────────────────────────────────


_ENGINE_TO_MEMO_QTYPE: dict[str, MemoQuestionType] = {
    "INVESTMENT_DECISION": MemoQuestionType.INVESTMENT_DECISION,
    "PROBABILISTIC_FORECAST": MemoQuestionType.FORECAST,
    "FORECAST": MemoQuestionType.FORECAST,
    "EXPLANATORY": MemoQuestionType.EXPLANATORY,
    "STRATEGIC_RECOMMENDATION": MemoQuestionType.STRATEGIC,
    "STRATEGIC": MemoQuestionType.STRATEGIC,
}


def _coerce_question_type(value: Any) -> MemoQuestionType:
    if isinstance(value, MemoQuestionType):
        return value
    raw = getattr(value, "value", None) or str(value or "")
    return _ENGINE_TO_MEMO_QTYPE.get(raw, MemoQuestionType.EXPLANATORY)


# ── Eight-gate readiness ──────────────────────────────────────────


#: The eight gates a polymorphic bet must clear before the portfolio
#: agent will fire it. Prompt 15 owns the canonical definition; until
#: then we surface a deterministic readiness panel so the operator
#: sees what is and isn't ready when a memo carries an implied bet.
EIGHT_GATES: tuple[str, ...] = (
    "thesis_articulated",
    "principles_govern",
    "no_standing_contradiction",
    "confidence_band_narrow",
    "stake_sized",
    "horizon_set",
    "exit_condition_defined",
    "addressee_authorised",
)


def _eight_gate_readiness(
    *,
    memo_question_type: MemoQuestionType,
    implied_bet: Optional[Mapping[str, Any]],
    governing_count: int,
    confidence_band: float,
    addressee: str,
) -> dict[str, bool]:
    """Compute a deterministic readiness map. Operator sees what is and isn't ready."""

    bet = dict(implied_bet or {})
    has_thesis = memo_question_type in (
        MemoQuestionType.INVESTMENT_DECISION,
        MemoQuestionType.STRATEGIC,
        MemoQuestionType.FORECAST,
    )
    return {
        "thesis_articulated": has_thesis,
        "principles_govern": governing_count >= 2,
        "no_standing_contradiction": True,  # memos only build on CONCLUDED
        "confidence_band_narrow": confidence_band <= 0.50,
        "stake_sized": bool(bet.get("stake") or bet.get("stake_range")),
        "horizon_set": bool(bet.get("horizon")),
        "exit_condition_defined": bool(
            bet.get("ceiling") or bet.get("ceilings") or bet.get("exit")
        ),
        "addressee_authorised": bool(addressee and addressee.strip()),
    }


# ── Markdown rendering ────────────────────────────────────────────


def _truncate(text: str, *, words: int) -> str:
    parts = (text or "").split()
    if len(parts) <= words:
        return " ".join(parts)
    return " ".join(parts[:words]).rstrip(",.;:") + "…"


def _principle_line(principle_id: str, principles: Mapping[str, Principle]) -> str:
    p = principles.get(principle_id)
    if p is None:
        return f"- **{principle_id}** — _(principle not resolved; details elided)_"
    disciplines = ", ".join(
        getattr(d, "value", str(d)) for d in (p.disciplines or [])
    ) or "general"
    return (
        f"- **{principle_id}** — {p.text} "
        f"(_{disciplines}_; [details](/principles/{principle_id}))"
    )


def _input_row(
    obs_id: str,
    inputs_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    info = inputs_by_id.get(obs_id) or {}
    name = info.get("name") or info.get("title") or obs_id
    value = info.get("value")
    source = info.get("source") or info.get("artifact") or "n/a"
    observed_at = info.get("observed_at") or info.get("timestamp") or ""
    value_str = "—" if value is None else str(value)
    return f"| {obs_id} | {name} | {value_str} | {source} | {observed_at} |"


def _provenance_audit_block(
    *,
    provenance_active: Sequence[str],
    provenance_weights: Mapping[str, float],
    source_counts: Mapping[str, int],
) -> str:
    lines = ["Active provenance kinds:"]
    if not provenance_active:
        lines.append("- (none recorded)")
    for kind in provenance_active:
        weight = provenance_weights.get(kind, 1.0)
        count = source_counts.get(kind, 0)
        lines.append(
            f"- **{kind}** — weighting {weight:.2f}; sources: {count}"
        )
    return "\n".join(lines)


def _implied_bet_block(
    *,
    bet: Optional[Mapping[str, Any]],
    readiness: Mapping[str, bool],
) -> str:
    if not bet:
        lines = ["This memo does not imply a bet. The conclusion is reasoning-only."]
    else:
        kind = bet.get("kind") or bet.get("bet_kind") or "unspecified"
        shape = bet.get("shape") or bet.get("bet_shape") or {}
        stake = bet.get("stake") or bet.get("stake_range") or shape.get("stake")
        side = bet.get("side") or shape.get("side")
        horizon = bet.get("horizon") or shape.get("horizon")
        ceilings = bet.get("ceiling") or bet.get("ceilings") or shape.get("ceiling")
        lines = [
            f"- **Bet kind**: {kind}",
            f"- **Side**: {side or '—'}",
            f"- **Stake**: {stake or '—'}",
            f"- **Horizon**: {horizon or '—'}",
            f"- **Ceilings**: {ceilings or '—'}",
        ]
    lines.append("")
    lines.append("Eight-gate readiness:")
    for gate, ok in readiness.items():
        mark = "✅" if ok else "⬜"
        lines.append(f"- {mark} `{gate}`")
    return "\n".join(lines)


def render_memo_body(
    memo: InvestmentMemo,
    *,
    principles: Mapping[str, Principle],
    inputs_by_id: Mapping[str, Mapping[str, Any]],
    provenance_active: Sequence[str],
    provenance_weights: Mapping[str, float],
    source_counts: Mapping[str, int],
) -> str:
    """Render the 10-section memo body for ``memo`` as markdown.

    Pure: this does NOT mutate ``memo``. The builder calls this, then
    assigns the result to :attr:`memo.body_markdown` before validation.
    """

    confidence_band = f"{memo.confidence_low:.2f}–{memo.confidence_high:.2f}"
    header_lines = [
        f"**Title**: {memo.title}",
        f"**Author**: Theseus — {memo.synthesizer_version}",
        f"**Date**: {memo.created_at.date().isoformat()}",
        f"**Question type**: {memo.question_type.value if hasattr(memo.question_type, 'value') else memo.question_type}",
        f"**Confidence band**: {confidence_band}",
        f"**Addressee**: {memo.addressee or 'Portfolio Agent'}",
    ]

    if memo.governing_principle_ids:
        governing_block = "\n".join(
            _principle_line(pid, principles) for pid in memo.governing_principle_ids
        )
    else:
        governing_block = "- _(no governing principles recorded)_"

    if memo.observed_input_ids:
        table_header = (
            "| ID | Name | Value | Source | Observed at |\n"
            "| --- | --- | --- | --- | --- |"
        )
        table_rows = "\n".join(
            _input_row(obs_id, inputs_by_id) for obs_id in memo.observed_input_ids
        )
        inputs_block = f"{table_header}\n{table_rows}"
    else:
        inputs_block = "_No observed inputs recorded for this memo._"

    if memo.reasoning_chain:
        steps: list[str] = []
        for idx, step in enumerate(memo.reasoning_chain, start=1):
            kind = step.get("step_kind") or "STEP"
            pid = step.get("principle_id") or "(no principle)"
            obs = step.get("observation_id") or "—"
            derived = step.get("derived_fact") or step.get("text") or ""
            steps.append(
                f"**Step {idx} — {kind}**: applied principle `{pid}` to "
                f"observation `{obs}` → derived: {derived}"
            )
        reasoning_block = "\n\n".join(steps)
    else:
        reasoning_block = "_(reasoning chain empty — synthesizer abstained on this surface)_"

    sections = [
        "## Header",
        "\n".join(header_lines),
        "",
        "## TL;DR",
        memo.tldr.strip() or "_(no TL;DR provided)_",
        "",
        "## Question constituted",
        memo.question_constituted.strip() or memo.title,
        "",
        "## Governing principles",
        governing_block,
        "",
        "## Observed inputs",
        inputs_block,
        "",
        "## Reasoning chain",
        reasoning_block,
        "",
        "## Implied bet",
        _implied_bet_block(
            bet=memo.implied_bet, readiness=memo.eight_gate_readiness
        ),
        "",
        "## What would update us",
        memo.what_would_update_us.strip()
        or (
            "The conclusion would weaken if any governing principle "
            "loses standing, or if a confirming observation flips."
        ),
        "",
        "## Abstentions and caveats",
        memo.abstentions_and_caveats.strip()
        or (
            f"Confidence band rationale: the synthesizer narrowed to "
            f"{confidence_band} given the governing-principle set above."
        ),
        "",
        "## Provenance audit",
        _provenance_audit_block(
            provenance_active=provenance_active,
            provenance_weights=provenance_weights,
            source_counts=source_counts,
        ),
        "",
    ]
    return "\n".join(sections).strip() + "\n"


# ── Public entrypoint ─────────────────────────────────────────────


def _coerce_principles(value: Any) -> dict[str, Principle]:
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items() if isinstance(v, Principle)}
    if isinstance(value, Iterable):
        out: dict[str, Principle] = {}
        for p in value:
            if isinstance(p, Principle):
                out[p.id] = p
        return out
    return {}


def _default_addressee(question_type: MemoQuestionType) -> str:
    track = {
        MemoQuestionType.INVESTMENT_DECISION: "investment",
        MemoQuestionType.FORECAST: "forecast",
        MemoQuestionType.STRATEGIC: "strategy",
        MemoQuestionType.EXPLANATORY: "research",
    }[question_type]
    return f"Portfolio Agent — {track}"


def _derive_title(synthesis_result: Any, conclusion: Any) -> str:
    """Title is derived from the conclusion's assertion, trimmed."""

    assertion = getattr(conclusion, "assertion", None) or ""
    if not assertion:
        return "Untitled memo"
    # Strip a trailing period and clip to ~10 words.
    return _truncate(assertion.rstrip("."), words=12) or "Untitled memo"


def build_memo(
    synthesis_result: Any,
    *,
    store: Any,
    organization_id: str,
    addressee: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> InvestmentMemo:
    """Build, persist, and render the canonical investment memo.

    Parameters
    ----------
    synthesis_result:
        A :class:`~noosphere.synthesizer.engine.SynthesisResult` (or
        any object exposing the same fields). The outcome MUST be
        ``CONCLUDED`` — the builder will raise :class:`ValueError`
        otherwise so an operator cannot accidentally ship an
        abstention as a memo.
    store:
        Persistence handle. Must expose ``put_investment_memo``.
    organization_id:
        Tenant the memo belongs to.
    addressee:
        Optional override; defaults to the per-question-type
        portfolio-agent string.

    Returns
    -------
    The persisted :class:`InvestmentMemo`. The memo is created in
    :attr:`MemoStatus.DRAFT`; operator review + send is a separate
    step.
    """

    outcome = getattr(synthesis_result, "outcome", None)
    outcome_value = getattr(outcome, "value", None) or str(outcome or "")
    if outcome_value != "CONCLUDED":
        raise ValueError(
            f"cannot build memo from non-CONCLUDED synthesis result "
            f"(outcome={outcome_value!r})"
        )
    conclusion = getattr(synthesis_result, "conclusion", None)
    if conclusion is None:
        raise ValueError("synthesis result has no conclusion attached")

    root = repo_root or _REPO_ROOT

    question_type = _coerce_question_type(
        getattr(conclusion, "conclusion_type", None)
        or getattr(synthesis_result, "question_type", None)
    )
    addressee = addressee or _default_addressee(question_type)

    title = _derive_title(synthesis_result, conclusion)
    confidence_low = float(getattr(conclusion, "confidence_low", 0.0) or 0.0)
    confidence_high = float(getattr(conclusion, "confidence_high", 0.0) or 0.0)

    governing_ids = list(getattr(conclusion, "governing_principles", []) or [])
    observed_ids = list(getattr(conclusion, "cited_observations", []) or [])
    chain_steps = list(getattr(conclusion, "reasoning_chain", []) or [])
    chain_payload = [
        {
            "step_kind": getattr(step, "step_kind", None),
            "principle_id": getattr(step, "principle_id", None),
            "observation_id": getattr(step, "observation_id", None),
            "derived_fact": getattr(step, "derived_fact", None),
        }
        for step in chain_steps
    ]
    implied_bet = getattr(conclusion, "implied_bet", None)
    synthesizer_version = (
        getattr(conclusion, "synthesizer_version", None)
        or getattr(synthesis_result, "synthesizer_version", None)
        or "synthesizer/v1"
    )

    # Provenance audit. Engines that wired prompt 09 surface a
    # ``provenance_filter`` summary alongside the result; until then
    # we record what we have on hand (PROPRIETARY + STUDIED_EXTERNAL +
    # ENDORSED_EXTERNAL by default per prompt 09).
    provenance_active = list(
        getattr(synthesis_result, "provenance_active", None)
        or [k.value for k in ProvenanceKind if k != ProvenanceKind.OPPOSING_EXTERNAL]
    )
    provenance_weights = dict(
        getattr(synthesis_result, "provenance_weights", None) or {}
    )
    if not provenance_weights:
        provenance_weights = {
            ProvenanceKind.PROPRIETARY.value: 2.0,
            ProvenanceKind.STUDIED_EXTERNAL.value: 1.0,
            ProvenanceKind.ENDORSED_EXTERNAL.value: 1.0,
        }
    source_counts = dict(
        getattr(synthesis_result, "provenance_source_counts", None) or {}
    )

    confidence_band = max(0.0, confidence_high - confidence_low)
    readiness = _eight_gate_readiness(
        memo_question_type=question_type,
        implied_bet=implied_bet if isinstance(implied_bet, Mapping) else None,
        governing_count=len(governing_ids),
        confidence_band=confidence_band,
        addressee=addressee,
    )

    now = datetime.now(timezone.utc)
    memo = InvestmentMemo(
        organization_id=organization_id,
        synthesizer_result_id=getattr(synthesis_result, "memo_id", None),
        title=title,
        tldr=_build_tldr(conclusion=conclusion, addressee=addressee),
        question_constituted=getattr(synthesis_result, "question", "")
        or getattr(synthesis_result, "question_text", "")
        or title,
        question_type=question_type,
        confidence_low=confidence_low,
        confidence_high=confidence_high,
        governing_principle_ids=governing_ids,
        observed_input_ids=observed_ids,
        reasoning_chain=chain_payload,
        implied_bet=dict(implied_bet) if isinstance(implied_bet, Mapping) else None,
        eight_gate_readiness=readiness,
        what_would_update_us=_default_what_would_update_us(governing_ids),
        abstentions_and_caveats=_default_caveats(
            confidence_low=confidence_low,
            confidence_high=confidence_high,
        ),
        provenance_audit={
            "active": provenance_active,
            "weights": provenance_weights,
            "source_counts": source_counts,
        },
        status=MemoStatus.DRAFT,
        addressee=addressee,
        synthesizer_version=synthesizer_version,
        created_at=now,
        updated_at=now,
    )
    memo.slug = memo_slug(memo.title, memo.id)
    md_rel, pdf_rel = memo_paths(created_at=memo.created_at, slug=memo.slug)
    memo.md_path = md_rel

    # Principle metadata for the rendered body. Best-effort lookup —
    # the builder is happy to render with a partial principle map.
    principles_by_id = _load_principles(store, governing_ids)
    inputs_by_id = _load_inputs(store, observed_ids)

    memo.body_markdown = render_memo_body(
        memo,
        principles=principles_by_id,
        inputs_by_id=inputs_by_id,
        provenance_active=provenance_active,
        provenance_weights=provenance_weights,
        source_counts=source_counts,
    )

    # The 10-section contract is load-bearing. A memo that fails this
    # check is REJECTED at build time — the operator never ships it.
    validate_memo_body(memo.body_markdown)

    # Persist before writing files so the row is the system-of-record.
    put_investment_memo = getattr(store, "put_investment_memo", None)
    if callable(put_investment_memo):
        put_investment_memo(memo)
    else:
        logger.warning(
            "synthesizer.memo_builder.store_missing_helper",
            extra={"memo_id": memo.id},
        )

    # Write markdown to disk.
    md_abs = root / md_rel
    md_abs.parent.mkdir(parents=True, exist_ok=True)
    md_abs.write_text(memo.body_markdown, encoding="utf-8")

    # Build the PDF if pdflatex is available. PDF is a derived artifact.
    try:
        pdf_path = build_memo_pdf(memo, repo_root=root)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "synthesizer.memo_builder.pdf_failed",
            extra={"memo_id": memo.id, "error": f"{type(exc).__name__}: {exc}"},
        )
        pdf_path = None
    if pdf_path is not None:
        memo.pdf_path = pdf_path
        if callable(put_investment_memo):
            put_investment_memo(memo)

    logger.info(
        "synthesizer.memo_builder.built",
        extra={
            "memo_id": memo.id,
            "status": memo.status if isinstance(memo.status, str) else memo.status.value,
            "md_path": memo.md_path,
            "pdf_path": memo.pdf_path,
        },
    )
    return memo


# ── Lifecycle helpers ─────────────────────────────────────────────


def send_memo(
    store: Any,
    memo_id: str,
    *,
    addressee: Optional[str] = None,
) -> Optional[InvestmentMemo]:
    """Transition a memo DRAFT/UNDER_REVIEW → SENT. Stamps ``sent_at``."""

    update = getattr(store, "update_investment_memo_status", None)
    if not callable(update):
        return None
    return update(memo_id, MemoStatus.SENT, addressee=addressee)


def archive_memo(store: Any, memo_id: str) -> Optional[InvestmentMemo]:
    update = getattr(store, "update_investment_memo_status", None)
    if not callable(update):
        return None
    return update(memo_id, MemoStatus.ARCHIVED)


def publish_memo(store: Any, memo_id: str) -> Optional[InvestmentMemo]:
    update = getattr(store, "update_investment_memo_status", None)
    if not callable(update):
        return None
    return update(memo_id, MemoStatus.PUBLIC)


# ── Internal helpers ──────────────────────────────────────────────


def _build_tldr(*, conclusion: Any, addressee: str) -> str:
    assertion = (getattr(conclusion, "assertion", None) or "").rstrip(".")
    confidence_low = float(getattr(conclusion, "confidence_low", 0.0) or 0.0)
    confidence_high = float(getattr(conclusion, "confidence_high", 0.0) or 0.0)
    governing = getattr(conclusion, "governing_principles", []) or []
    governing_text = (
        f"The governing principle is `{governing[0]}`."
        if governing
        else "No single principle dominates."
    )
    bet = getattr(conclusion, "implied_bet", None)
    bet_text = ""
    if isinstance(bet, Mapping):
        kind = bet.get("kind") or bet.get("bet_kind")
        if kind:
            bet_text = f" The implied bet is {kind}."
    body = (
        f"{assertion}. "
        f"Confidence {confidence_low:.2f}–{confidence_high:.2f}. "
        f"{governing_text}{bet_text}"
    )
    return _truncate(body, words=80)


def _default_what_would_update_us(governing_ids: Sequence[str]) -> str:
    if not governing_ids:
        return (
            "Updates: any new principle that materially changes the "
            "domain we cited; any contradicting observation surfaced "
            "by the prompt-06 engine; any provenance change downgrading "
            "the principle sources."
        )
    head = governing_ids[0]
    return (
        f"We would weaken on any of: (1) principle `{head}` losing "
        f"STANDING in the firm's contradiction lifecycle; (2) a fresh "
        f"observation that flips the governing precondition; (3) a "
        f"provenance downgrade on any cited principle. We would "
        f"strengthen on a confirming algorithm invocation."
    )


def _default_caveats(*, confidence_low: float, confidence_high: float) -> str:
    band = confidence_high - confidence_low
    return (
        f"Confidence band rationale: the synthesizer narrowed to a "
        f"{band:.2f}-wide band (low={confidence_low:.2f}, "
        f"high={confidence_high:.2f}). No STANDING contradictions "
        f"block the chain (else the synthesizer would have abstained)."
    )


def _load_principles(store: Any, ids: Sequence[str]) -> dict[str, Principle]:
    if not ids:
        return {}
    out: dict[str, Principle] = {}
    list_principles = getattr(store, "list_principles", None)
    if callable(list_principles):
        try:
            for p in list_principles():
                if p.id in ids:
                    out[p.id] = p
        except Exception:
            pass
    return out


def _load_inputs(store: Any, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Best-effort observed-input lookup.

    The synthesizer's observation citations point at currents, algorithm
    invocations, etc. — multiple stores. We resolve what we can; the
    renderer falls back to the bare id for unresolved rows.
    """

    if not ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    get_event = getattr(store, "get_current_event", None)
    for obs_id in ids:
        if callable(get_event):
            try:
                evt = get_event(obs_id)
            except Exception:
                evt = None
            if evt is not None:
                out[obs_id] = {
                    "name": getattr(evt, "title", None) or obs_id,
                    "value": getattr(evt, "summary", None),
                    "source": getattr(evt, "source", "currents"),
                    "observed_at": (
                        getattr(evt, "observed_at", None)
                        or getattr(evt, "created_at", None)
                    ),
                }
                continue
        out[obs_id] = {"name": obs_id, "source": "n/a"}
    return out


__all__ = [
    "EIGHT_GATES",
    "archive_memo",
    "build_memo",
    "publish_memo",
    "render_memo_body",
    "send_memo",
]
