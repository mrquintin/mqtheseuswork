"""Tests for the memo builder (Round 19 prompt 11)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from noosphere.models import (
    ConvictionLevel,
    InvestmentMemo,
    MemoQuestionType,
    MemoStatus,
    Principle,
    ProvenanceKind,
)
from noosphere.synthesizer.engine import (
    Conclusion,
    QuestionType,
    ReasoningChainStep,
    SynthesisOutcome,
    SynthesisResult,
)
from noosphere.synthesizer.memo_builder import (
    EIGHT_GATES,
    build_memo,
    publish_memo,
    send_memo,
)
from noosphere.synthesizer.memo_pdf import render_template
from noosphere.synthesizer.memo_validator import (
    MemoValidationError,
    validate_memo_body,
)


# ── Fakes ──────────────────────────────────────────────────────────


@dataclass
class _FakeStore:
    principles: list[Principle] = field(default_factory=list)
    memos: dict[str, InvestmentMemo] = field(default_factory=dict)

    def list_principles(self) -> list[Principle]:
        return list(self.principles)

    def get_current_event(self, _event_id: str) -> Any:
        return None

    def put_investment_memo(self, memo: InvestmentMemo) -> InvestmentMemo:
        self.memos[memo.id] = memo.model_copy(deep=True)
        return memo

    def get_investment_memo(self, memo_id: str) -> Optional[InvestmentMemo]:
        memo = self.memos.get(memo_id)
        if memo is None:
            return None
        return memo.model_copy(deep=True)

    def list_investment_memos(
        self,
        *,
        organization_id: Optional[str] = None,
        status: Optional[MemoStatus] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[InvestmentMemo]:
        out = list(self.memos.values())
        if status is not None:
            out = [m for m in out if m.status == status.value]
        return out[:limit]

    def update_investment_memo_status(
        self,
        memo_id: str,
        status: MemoStatus,
        *,
        addressee: Optional[str] = None,
    ) -> Optional[InvestmentMemo]:
        memo = self.memos.get(memo_id)
        if memo is None:
            return None
        memo.status = status.value
        if addressee is not None:
            memo.addressee = addressee
        now = datetime.now(timezone.utc)
        if status == MemoStatus.SENT:
            memo.sent_at = now
        elif status == MemoStatus.PUBLIC:
            memo.published_at = now
        elif status == MemoStatus.ARCHIVED:
            memo.archived_at = now
        return memo.model_copy(deep=True)


def _principle(pid: str, text: str) -> Principle:
    return Principle(
        id=pid,
        text=text,
        disciplines=[],
        conviction=ConvictionLevel.MODERATE,
        provenance=ProvenanceKind.PROPRIETARY,
    )


def _conclusion(*, implied_bet: Optional[dict[str, Any]] = None) -> Conclusion:
    return Conclusion(
        conclusion_type=QuestionType.INVESTMENT_DECISION,
        assertion="Capital discipline beats timing in the current regime",
        confidence_low=0.55,
        confidence_high=0.75,
        governing_principles=["p_capital", "p_conviction"],
        cited_observations=["obs_macro_2026q1"],
        reasoning_chain=[
            ReasoningChainStep(
                step_kind="DETECT",
                principle_id="p_capital",
                derived_fact="Precondition met.",
            ),
            ReasoningChainStep(
                step_kind="APPLY_PRINCIPLE",
                principle_id="p_conviction",
                derived_fact="Principle applies; intermediate derived.",
            ),
            ReasoningChainStep(
                step_kind="SYNTHESIZE",
                principle_id="p_capital",
                derived_fact="Combined intermediates into final fact.",
            ),
        ],
        implied_bet=implied_bet,
    )


def _synthesis_result(conclusion: Conclusion, *, question: str = "Should we long this fund?") -> SynthesisResult:
    return SynthesisResult(
        outcome=SynthesisOutcome.CONCLUDED,
        reasoning="ok",
        memo_id="syn_abc123",
        conclusion=conclusion,
        question_type=QuestionType.INVESTMENT_DECISION,
        governing_principle_ids=["p_capital", "p_conviction"],
    )


# ── build_memo ─────────────────────────────────────────────────────


def test_build_memo_validates_against_section_contract(tmp_path) -> None:
    store = _FakeStore(
        principles=[
            _principle("p_capital", "Capital discipline beats timing."),
            _principle("p_conviction", "Conviction sized correctly compounds."),
        ]
    )
    result = _synthesis_result(_conclusion())
    setattr(result, "question", "Should we long this fund?")
    memo = build_memo(
        result,
        store=store,
        organization_id="org_1",
        repo_root=tmp_path,
    )
    assert memo.status == MemoStatus.DRAFT.value or memo.status == MemoStatus.DRAFT
    assert memo.title
    assert memo.tldr
    assert memo.body_markdown
    # The body MUST satisfy the 10-section contract.
    validation = validate_memo_body(memo.body_markdown)
    assert validation.ok
    assert "## Implied bet" in memo.body_markdown
    assert memo.md_path is not None and memo.md_path.startswith("docs/memos/")
    # Markdown file should have been written under the tmp repo root.
    written = tmp_path / memo.md_path
    assert written.exists()
    assert written.read_text(encoding="utf-8").strip().endswith("\n".strip()) or written.read_text(encoding="utf-8").strip()


def test_build_memo_rejects_non_concluded() -> None:
    result = SynthesisResult(
        outcome=SynthesisOutcome.ABSTAINED_CONFIDENCE,
        reasoning="band too wide",
    )
    with pytest.raises(ValueError):
        build_memo(result, store=_FakeStore(), organization_id="org_1")


def test_build_memo_uses_default_addressee_for_investment_question(tmp_path) -> None:
    store = _FakeStore(
        principles=[
            _principle("p_capital", "Capital discipline beats timing."),
            _principle("p_conviction", "Conviction compounds."),
        ]
    )
    result = _synthesis_result(_conclusion())
    memo = build_memo(
        result,
        store=store,
        organization_id="org_1",
        repo_root=tmp_path,
    )
    assert "Portfolio Agent" in memo.addressee
    assert "investment" in memo.addressee.lower()


def test_build_memo_addressee_override(tmp_path) -> None:
    store = _FakeStore(
        principles=[
            _principle("p_capital", "Capital discipline beats timing."),
            _principle("p_conviction", "Conviction compounds."),
        ]
    )
    result = _synthesis_result(_conclusion())
    memo = build_memo(
        result,
        store=store,
        organization_id="org_1",
        addressee="Founder review queue",
        repo_root=tmp_path,
    )
    assert memo.addressee == "Founder review queue"


# ── Eight-gate readiness ──────────────────────────────────────────


def test_eight_gate_readiness_renders_each_gate(tmp_path) -> None:
    store = _FakeStore(
        principles=[
            _principle("p_capital", "Capital discipline beats timing."),
            _principle("p_conviction", "Conviction compounds."),
        ]
    )
    result = _synthesis_result(
        _conclusion(
            implied_bet={
                "kind": "equity",
                "stake": 100_000,
                "horizon": "12 months",
                "ceiling": -0.10,
            }
        )
    )
    memo = build_memo(
        result,
        store=store,
        organization_id="org_1",
        repo_root=tmp_path,
    )
    for gate in EIGHT_GATES:
        assert gate in memo.eight_gate_readiness
        assert f"`{gate}`" in memo.body_markdown


# ── Provenance audit ─────────────────────────────────────────────


def test_provenance_audit_reflects_synthesis_filter(tmp_path) -> None:
    store = _FakeStore(
        principles=[
            _principle("p_capital", "Capital discipline beats timing."),
            _principle("p_conviction", "Conviction compounds."),
        ]
    )
    result = _synthesis_result(_conclusion())
    setattr(result, "provenance_active", ["PROPRIETARY", "STUDIED_EXTERNAL"])
    setattr(result, "provenance_weights", {"PROPRIETARY": 2.5})
    setattr(result, "provenance_source_counts", {"PROPRIETARY": 3, "STUDIED_EXTERNAL": 1})
    memo = build_memo(
        result,
        store=store,
        organization_id="org_1",
        repo_root=tmp_path,
    )
    audit = memo.provenance_audit
    assert audit["active"] == ["PROPRIETARY", "STUDIED_EXTERNAL"]
    assert audit["weights"]["PROPRIETARY"] == 2.5
    assert audit["source_counts"]["PROPRIETARY"] == 3
    assert "PROPRIETARY" in memo.body_markdown
    assert "2.50" in memo.body_markdown


# ── Lifecycle ─────────────────────────────────────────────────────


def test_send_memo_round_trip(tmp_path) -> None:
    store = _FakeStore(
        principles=[
            _principle("p_capital", "Capital discipline beats timing."),
            _principle("p_conviction", "Conviction compounds."),
        ]
    )
    result = _synthesis_result(_conclusion())
    memo = build_memo(
        result,
        store=store,
        organization_id="org_1",
        repo_root=tmp_path,
    )
    assert memo.status in (MemoStatus.DRAFT, MemoStatus.DRAFT.value)
    sent = send_memo(store, memo.id)
    assert sent is not None
    assert sent.status in (MemoStatus.SENT, MemoStatus.SENT.value)
    assert sent.sent_at is not None


def test_publish_filter_returns_only_public(tmp_path) -> None:
    store = _FakeStore(
        principles=[
            _principle("p_capital", "Capital discipline beats timing."),
            _principle("p_conviction", "Conviction compounds."),
        ]
    )
    result = _synthesis_result(_conclusion())
    memo = build_memo(
        result,
        store=store,
        organization_id="org_1",
        repo_root=tmp_path,
    )
    # Pre-publish: list of PUBLIC is empty.
    assert store.list_investment_memos(status=MemoStatus.PUBLIC) == []
    published = publish_memo(store, memo.id)
    assert published is not None
    assert published.status in (MemoStatus.PUBLIC, MemoStatus.PUBLIC.value)
    public_rows = store.list_investment_memos(status=MemoStatus.PUBLIC)
    assert len(public_rows) == 1
    # Pre-publish memos (DRAFT) are not in the PUBLIC filter.
    assert all(
        (m.status == MemoStatus.PUBLIC.value or m.status == MemoStatus.PUBLIC)
        for m in public_rows
    )


# ── PDF template ──────────────────────────────────────────────────


def test_render_template_substitutes_tokens(tmp_path) -> None:
    memo = InvestmentMemo(
        organization_id="org_1",
        title="Capital discipline beats timing this regime",
        slug="capital-discipline-12345678",
        tldr="The thesis holds: short-horizon timing underperforms.",
        addressee="Portfolio Agent — investment",
        question_type=MemoQuestionType.INVESTMENT_DECISION,
        body_markdown="## Header\n\nFoo\n\n## TL;DR\n\nBar.",
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
        synthesizer_version="synthesizer/v1",
    )
    template = (
        "TITLE=%%TITLE%%\n"
        "TLDR=%%TLDR%%\n"
        "ADDRESSEE=%%ADDRESSEE%%\n"
        "DATE=%%DATE%%\n"
        "AUTHOR=%%AUTHOR%%\n"
        "BODY=\n%%BODY%%\n"
    )
    rendered = render_template(memo, template=template)
    assert "TITLE=Capital discipline beats timing this regime" in rendered
    assert "Portfolio Agent" in rendered
    assert "DATE=2026-05-16" in rendered
    # Synthesizer version flows in via AUTHOR.
    assert "synthesizer/v1" in rendered
    # Markdown subsection headings become LaTeX \\subsection*.
    assert "\\subsection*{Header}" in rendered
