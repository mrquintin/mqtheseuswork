"""SynthesizerEngine — Round 19 prompt 10.

The synthesizer composes:

* a *question* (operator-typed or system-triggered),
* a *retrieval bundle* of principles + algorithm invocations + currents,
* a *governing-principles* subset (≥ 2 required),
* a *reasoning chain* (LLM-produced JSON, each step cites a principle),
* a *contradiction check* that walks STANDING contradictions over the
  principle pairs the chain cites,
* a *conclusion* that includes confidence bounds, citations, and an
  optional ``implied_bet``,
* a *memo* dispatched to the portfolio agent.

Abstention is first-class. ``SynthesisResult.outcome`` is one of:

* ``CONCLUDED`` — a memo was issued.
* ``ABSTAINED_NO_PRINCIPLES`` — fewer than 2 governing principles.
* ``ABSTAINED_CONTRADICTION`` — at least one STANDING contradiction
  between principles cited in the chain has score > 0.65.
* ``ABSTAINED_CONFIDENCE`` — the chain's emitted confidence band is
  too wide (high - low > 0.50).
* ``ABSTAINED_BUDGET`` — hourly token budget is exhausted.
* ``ABSTAINED_QUESTION_UNFORMED`` — the operator's input could not be
  constituted into one of the four supported question types.
* ``REFUSED_NORMATIVE_ONLY`` — the question is normative-only and no
  retrieved principle would operationalise it.

The synthesizer respects the provenance filter from prompt 09. A
``ProvenanceFilter`` callable is invoked over every retrieved item
before it enters the chain; the chain may not cite items the filter
dropped.

Like the contradiction engine and the algorithm runtime, every emitted
conclusion carries a synthesizer version (:data:`SYNTHESIZER_VERSION`)
so future analyses can group by version.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Sequence

from noosphere.llm import LLMClient
from noosphere.models import (
    AlgorithmInvocation,
    CurrentEvent,
    LogicalAlgorithm,
    Principle,
    ProvenanceKind,
    coerce_provenance,
)
from noosphere.synthesizer.budget import (
    BudgetExhausted,
    per_synthesis_reserve,
)
from noosphere.synthesizer.governing import identify_governing


logger = logging.getLogger(__name__)


SYNTHESIZER_VERSION = "synthesizer/v1"

# ── Tunables ────────────────────────────────────────────────────────


#: Minimum count of governing principles required to attempt a chain.
MIN_GOVERNING_PRINCIPLES: int = 2

#: STANDING contradictions strictly above this score abort the chain.
#: Matches the contradiction engine's CONTRADICTION_THRESHOLD so an
#: operator who tunes one knob doesn't surprise the other.
CONTRADICTION_BLOCK_THRESHOLD: float = 0.65

#: Maximum allowed confidence band width (high - low). Wider bands
#: signal the chain didn't actually narrow the question and the
#: synthesizer should abstain.
MAX_CONFIDENCE_BAND_WIDTH: float = 0.50

#: How long an LLM completion may be. Keeps the JSON parse cheap
#: and the prompt cap honest.
DEFAULT_LLM_MAX_TOKENS: int = 1_600


# ── Question types ──────────────────────────────────────────────────


class QuestionType(str, Enum):
    """The four canonical question types the synthesizer supports.

    These are intentionally narrower than the inquiry module's six —
    :mod:`noosphere.inquiry.question_typology` types every question
    the firm encounters, but the synthesizer only emits conclusions for
    the four shapes that map cleanly to a portfolio-agent action.
    Methodological and classificatory questions are answered elsewhere.
    """

    INVESTMENT_DECISION = "INVESTMENT_DECISION"
    PROBABILISTIC_FORECAST = "PROBABILISTIC_FORECAST"
    EXPLANATORY = "EXPLANATORY"
    STRATEGIC_RECOMMENDATION = "STRATEGIC_RECOMMENDATION"


_INVESTMENT_PATTERNS = (
    re.compile(r"\bshould (?:we |the firm )?(?:long|short|buy|sell|invest|hold|exit|enter|allocate|divest)\b", re.IGNORECASE),
    re.compile(r"\b(?:long|short|buy|sell) (?:this|that|the|a|an)\b", re.IGNORECASE),
    re.compile(r"\binvestment (?:decision|case|thesis)\b", re.IGNORECASE),
)
_PROBABILISTIC_PATTERNS = (
    re.compile(r"\bP\([^\)]+\)", re.IGNORECASE),
    re.compile(r"\bprob(?:ability|able|abilities)\b", re.IGNORECASE),
    re.compile(r"\bhow likely\b", re.IGNORECASE),
    re.compile(r"\bwill .+ by (?:19|20)\d{2}\b", re.IGNORECASE),
    re.compile(r"\bodds of\b", re.IGNORECASE),
)
_STRATEGIC_PATTERNS = (
    re.compile(r"\bshould (?:we|the firm|the team|the company)\b", re.IGNORECASE),
    re.compile(r"\bshould .+ commit\b", re.IGNORECASE),
    re.compile(r"\bcourse of action\b", re.IGNORECASE),
    re.compile(r"\ballocate (?:resources|capital|engineering|time)\b", re.IGNORECASE),
)
_EXPLANATORY_PATTERNS = (
    re.compile(r"\bwhy is\b", re.IGNORECASE),
    re.compile(r"\bwhy (?:are|do|does|did|would)\b", re.IGNORECASE),
    re.compile(r"\bexplain\b", re.IGNORECASE),
    re.compile(r"\bwhat drives\b", re.IGNORECASE),
)
_NORMATIVE_PATTERNS = (
    re.compile(r"\bis it (?:good|sound|right|valuable|worthwhile|ethical|moral)\b", re.IGNORECASE),
    re.compile(r"\b(?:morally|ethically) (?:good|right|wrong|bad)\b", re.IGNORECASE),
    re.compile(r"\bshould we believe\b", re.IGNORECASE),
)


def constitute_question(text: str) -> Optional[QuestionType]:
    """Map an operator-typed question to one of the supported types.

    Returns ``None`` when the input is empty or only matches the
    normative-only pattern (the engine raises
    ``REFUSED_NORMATIVE_ONLY`` separately by inspecting the same
    patterns; this function returns ``None`` so the caller can
    distinguish "unformed" from "normative-only").

    Order matters: investment-decision is checked before
    strategic-recommendation because "should we long X?" matches both
    families but the investment shape is the more specific one.
    """

    s = (text or "").strip()
    if not s:
        return None
    if any(p.search(s) for p in _INVESTMENT_PATTERNS):
        return QuestionType.INVESTMENT_DECISION
    if any(p.search(s) for p in _PROBABILISTIC_PATTERNS):
        return QuestionType.PROBABILISTIC_FORECAST
    if any(p.search(s) for p in _STRATEGIC_PATTERNS):
        return QuestionType.STRATEGIC_RECOMMENDATION
    if any(p.search(s) for p in _EXPLANATORY_PATTERNS):
        return QuestionType.EXPLANATORY
    return None


def _is_normative_only(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if any(p.search(s) for p in _NORMATIVE_PATTERNS):
        # Normative-only only triggers when no supported pattern fires.
        for family in (
            _INVESTMENT_PATTERNS,
            _PROBABILISTIC_PATTERNS,
            _STRATEGIC_PATTERNS,
            _EXPLANATORY_PATTERNS,
        ):
            if any(p.search(s) for p in family):
                return False
        return True
    return False


# ── Outcome / result types ──────────────────────────────────────────


class SynthesisOutcome(str, Enum):
    """The closed set of outcomes a single synthesize() call can produce."""

    CONCLUDED = "CONCLUDED"
    ABSTAINED_NO_PRINCIPLES = "ABSTAINED_NO_PRINCIPLES"
    ABSTAINED_CONTRADICTION = "ABSTAINED_CONTRADICTION"
    ABSTAINED_CONFIDENCE = "ABSTAINED_CONFIDENCE"
    ABSTAINED_BUDGET = "ABSTAINED_BUDGET"
    ABSTAINED_QUESTION_UNFORMED = "ABSTAINED_QUESTION_UNFORMED"
    REFUSED_NORMATIVE_ONLY = "REFUSED_NORMATIVE_ONLY"


@dataclass
class ReasoningChainStep:
    """One step in a chain. Each step cites a principle, by id.

    ``observation_id`` is optional — not every step is anchored to an
    observation (e.g. SYNTHESIZE steps fuse derived facts and may not
    cite a fresh observation). ``principle_id`` is required at
    construction time so a chain that omits citations cannot be
    silently persisted.
    """

    step_kind: str
    principle_id: str
    derived_fact: str
    observation_id: Optional[str] = None


@dataclass
class Conclusion:
    """The structured conclusion the synthesizer hands to the memo builder.

    The schema mirrors prompt 10's contract:

    .. code-block:: text

       { conclusion_type, assertion, confidence_low, confidence_high,
         governing_principles, cited_observations, reasoning_chain,
         implied_bet, generated_at, synthesizer_version }
    """

    conclusion_type: QuestionType
    assertion: str
    confidence_low: float
    confidence_high: float
    governing_principles: list[str]
    cited_observations: list[str]
    reasoning_chain: list[ReasoningChainStep]
    implied_bet: Optional[dict[str, Any]] = None
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    synthesizer_version: str = SYNTHESIZER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "conclusion_type": self.conclusion_type.value,
            "assertion": self.assertion,
            "confidence_low": self.confidence_low,
            "confidence_high": self.confidence_high,
            "governing_principles": list(self.governing_principles),
            "cited_observations": list(self.cited_observations),
            "reasoning_chain": [
                {
                    "step_kind": step.step_kind,
                    "principle_id": step.principle_id,
                    "observation_id": step.observation_id,
                    "derived_fact": step.derived_fact,
                }
                for step in self.reasoning_chain
            ],
            "implied_bet": self.implied_bet,
            "generated_at": self.generated_at.isoformat(),
            "synthesizer_version": self.synthesizer_version,
        }


@dataclass
class SynthesisResult:
    """What a single :meth:`SynthesizerEngine.synthesize` call returns.

    ``conclusion`` is populated only when ``outcome == CONCLUDED``. The
    ``memo_id`` (when set) points to the persisted memo a portfolio
    agent will read. The ``reasoning`` field is a human-readable cause
    string — populated for every outcome, never empty.
    """

    outcome: SynthesisOutcome
    reasoning: str
    memo_id: Optional[str] = None
    conclusion: Optional[Conclusion] = None
    question_type: Optional[QuestionType] = None
    governing_principle_ids: list[str] = field(default_factory=list)
    blocking_contradiction_ids: list[str] = field(default_factory=list)
    synthesizer_version: str = SYNTHESIZER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reasoning": self.reasoning,
            "memo_id": self.memo_id,
            "conclusion": self.conclusion.to_dict() if self.conclusion else None,
            "question_type": (
                self.question_type.value if self.question_type else None
            ),
            "governing_principle_ids": list(self.governing_principle_ids),
            "blocking_contradiction_ids": list(self.blocking_contradiction_ids),
            "synthesizer_version": self.synthesizer_version,
        }


# ── Filter / store protocols ────────────────────────────────────────


ProvenanceFilter = Callable[[ProvenanceKind], bool]


def default_provenance_filter() -> ProvenanceFilter:
    """Permit everything *except* OPPOSING_EXTERNAL.

    Matches the default the rest of the synthesis layer ships with —
    studied/endorsed external material is fair game; explicitly
    opposed material is not (prompt 09). Operators can pass a custom
    filter to widen or narrow the policy.
    """

    def _allow(kind: ProvenanceKind) -> bool:
        return kind != ProvenanceKind.OPPOSING_EXTERNAL

    return _allow


class _SynthesizerStore(Protocol):
    """The Store subset the engine touches; ducktyped for tests."""

    def list_principles(self) -> list[Principle]: ...

    def list_algorithms_for_org(
        self, organization_id: str, *, status: Optional[Any] = None
    ) -> list[LogicalAlgorithm]: ...

    def list_invocations_for_algorithm(
        self, algorithm_id: str, *, limit: int = 200
    ) -> list[AlgorithmInvocation]: ...

    def list_current_event_ids_by_status(
        self, statuses: Sequence[Any], limit: int = 40
    ) -> list[str]: ...

    def get_current_event(self, event_id: str) -> Optional[CurrentEvent]: ...

    def list_contradiction_results(
        self, *, method: Optional[str] = None, verdict: Optional[str] = None, limit: int = 200
    ) -> list[Any]: ...

    def get_contradiction_lifecycle(self, contradiction_id: str) -> Optional[Any]: ...

    def put_synthesizer_memo(self, memo: Mapping[str, Any]) -> None: ...


# ── JSON helpers (shared shape with the algorithm runtime) ──────────


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise ValueError("response is not a string")
    s = raw.strip()
    if not s:
        raise ValueError("response is empty")
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        match = _JSON_FENCE_RE.search(s)
        if match is None:
            raise ValueError("response is not parseable JSON")
        obj = json.loads(match.group(1))
    if not isinstance(obj, dict):
        raise ValueError("response is not a JSON object")
    return obj


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _coerce_unit(value: Any, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


# ── System-prompt loader ────────────────────────────────────────────


_PROMPT_PATH = Path(__file__).parent / "_prompts" / "system.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text()


_CHAIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "abstain",
        "assertion",
        "confidence_low",
        "confidence_high",
        "reasoning_chain",
    ],
    "properties": {
        "abstain": {"type": "boolean"},
        "abstain_reason": {"type": ["string", "null"]},
        "assertion": {"type": "string"},
        "confidence_low": {"type": "number"},
        "confidence_high": {"type": "number"},
        "implied_bet": {"type": ["object", "null"]},
        "reasoning_chain": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["step_kind", "principle_id", "derived_fact"],
                "properties": {
                    "step_kind": {
                        "enum": ["DETECT", "APPLY_PRINCIPLE", "SYNTHESIZE"]
                    },
                    "principle_id": {"type": "string"},
                    "observation_id": {"type": ["string", "null"]},
                    "derived_fact": {"type": "string"},
                },
            },
        },
    },
}


# ── Engine ──────────────────────────────────────────────────────────


@dataclass
class _LLMResponse:
    payload: dict[str, Any]
    tokens_used: int


class SynthesizerEngine:
    """The reasoning organ of the firm.

    Parameters
    ----------
    llm:
        :class:`LLMClient`. ``MockLLMClient`` is the standard test seam.
    organization_id:
        Tenant whose algorithms / invocations the engine retrieves.
    llm_max_tokens:
        Per-call ``max_tokens`` for the chain-construction Haiku call.
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        organization_id: str,
        llm_max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> None:
        self._llm = llm
        self._organization_id = organization_id
        self._llm_max_tokens = max(1, int(llm_max_tokens))
        self._system_prompt = _load_system_prompt().replace(
            "{schema}", json.dumps(_CHAIN_SCHEMA, sort_keys=True)
        )

    # ── Public API ─────────────────────────────────────────────

    async def synthesize(
        self,
        question: str,
        *,
        store: _SynthesizerStore,
        budget: Any | None = None,
        provenance_filter: Optional[ProvenanceFilter] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> SynthesisResult:
        """Run one synthesis pass over the operator's question.

        ``budget`` is optional: when supplied it must be an
        :class:`HourlyBudgetGuard`-like object exposing
        ``reserve(prompt, completion)`` / ``record(prompt,
        completion)``. Pass ``None`` for ad-hoc CLI runs that should
        not be metered.
        """

        provenance_filter = provenance_filter or default_provenance_filter()
        context = context or {}

        # 1. Constitute the question.
        if _is_normative_only(question):
            return SynthesisResult(
                outcome=SynthesisOutcome.REFUSED_NORMATIVE_ONLY,
                reasoning=(
                    "The question is normative-only — no retrieved principle "
                    "would operationalise it. Re-phrase as a strategic or "
                    "investment question to get a conclusion."
                ),
            )
        qtype = constitute_question(question)
        if qtype is None:
            return SynthesisResult(
                outcome=SynthesisOutcome.ABSTAINED_QUESTION_UNFORMED,
                reasoning=(
                    "Could not constitute the input into one of the four "
                    "supported question types (INVESTMENT_DECISION, "
                    "PROBABILISTIC_FORECAST, EXPLANATORY, "
                    "STRATEGIC_RECOMMENDATION)."
                ),
            )

        # 2. Budget gate. Reserve up-front so we abstain before the
        #    retrieval cost is incurred when there is no headroom.
        prompt_reserve, completion_reserve = per_synthesis_reserve()
        if budget is not None:
            try:
                budget.authorize(prompt_reserve, completion_reserve)
            except BudgetExhausted as exc:
                return SynthesisResult(
                    outcome=SynthesisOutcome.ABSTAINED_BUDGET,
                    reasoning=f"Hourly synthesizer budget exhausted: {exc}",
                    question_type=qtype,
                )

        # 3. Retrieve principles + invocations + currents, then filter
        #    by provenance.
        principles = self._filter_by_provenance(
            store.list_principles(), provenance_filter
        )
        invocations = self._filter_invocations_by_provenance(
            store, provenance_filter
        )
        currents = self._retrieve_currents(store)

        # 4. Identify governing principles. Operator-supplied
        #    ``context['domain']`` wins when provided; otherwise we
        #    fall back to the question text itself.
        domain_hint = str(context.get("domain") or "").strip() or question
        governing = identify_governing(principles, domain_hint)
        if len(governing) < MIN_GOVERNING_PRINCIPLES:
            return SynthesisResult(
                outcome=SynthesisOutcome.ABSTAINED_NO_PRINCIPLES,
                reasoning=(
                    f"Only {len(governing)} governing principle(s) "
                    f"identified; the synthesizer requires at least "
                    f"{MIN_GOVERNING_PRINCIPLES}."
                ),
                question_type=qtype,
                governing_principle_ids=[p.id for p in governing],
            )

        # 5. Construct the reasoning chain via one Haiku call.
        try:
            response = self._call_llm(
                question=question,
                qtype=qtype,
                governing=governing,
                invocations=invocations,
                currents=currents,
                context=context,
            )
        except _LLMRefusedToReason as exc:
            return SynthesisResult(
                outcome=SynthesisOutcome.ABSTAINED_NO_PRINCIPLES,
                reasoning=f"LLM abstained: {exc}",
                question_type=qtype,
                governing_principle_ids=[p.id for p in governing],
            )

        if budget is not None:
            try:
                budget.charge(prompt_reserve, response.tokens_used)
            except Exception:  # pragma: no cover - charge is best-effort
                pass

        payload = response.payload
        if payload.get("abstain"):
            return SynthesisResult(
                outcome=SynthesisOutcome.ABSTAINED_NO_PRINCIPLES,
                reasoning=(
                    str(payload.get("abstain_reason") or "").strip()
                    or "LLM abstained without a specific reason."
                ),
                question_type=qtype,
                governing_principle_ids=[p.id for p in governing],
            )

        # 6. Validate the chain. No fabricated principles, every step
        #    cites a principle in the governing set.
        try:
            chain = self._parse_chain(payload, governing_ids={p.id for p in governing})
        except _ChainValidationError as exc:
            return SynthesisResult(
                outcome=SynthesisOutcome.ABSTAINED_NO_PRINCIPLES,
                reasoning=f"Reasoning chain failed validation: {exc}",
                question_type=qtype,
                governing_principle_ids=[p.id for p in governing],
            )

        # 7. Contradiction check.
        cited_principle_ids = sorted({step.principle_id for step in chain})
        blocking = self._find_blocking_contradictions(store, cited_principle_ids)
        if blocking:
            return SynthesisResult(
                outcome=SynthesisOutcome.ABSTAINED_CONTRADICTION,
                reasoning=(
                    "The chain cites principles in unresolved STANDING "
                    f"contradiction (ids: {sorted(blocking)})."
                ),
                question_type=qtype,
                governing_principle_ids=[p.id for p in governing],
                blocking_contradiction_ids=sorted(blocking),
            )

        # 8. Confidence-band check.
        confidence_low = _coerce_unit(payload.get("confidence_low"), default=0.0)
        confidence_high = _coerce_unit(payload.get("confidence_high"), default=1.0)
        if confidence_high < confidence_low:
            confidence_low, confidence_high = confidence_high, confidence_low
        if (confidence_high - confidence_low) > MAX_CONFIDENCE_BAND_WIDTH:
            return SynthesisResult(
                outcome=SynthesisOutcome.ABSTAINED_CONFIDENCE,
                reasoning=(
                    f"Confidence band too wide "
                    f"({confidence_high - confidence_low:.2f} > "
                    f"{MAX_CONFIDENCE_BAND_WIDTH:.2f})."
                ),
                question_type=qtype,
                governing_principle_ids=[p.id for p in governing],
            )

        # 9. Build the conclusion + dispatch the memo.
        cited_observations = sorted(
            {step.observation_id for step in chain if step.observation_id}
        )
        conclusion = Conclusion(
            conclusion_type=qtype,
            assertion=str(payload.get("assertion") or "").strip()
            or "(no assertion produced)",
            confidence_low=confidence_low,
            confidence_high=confidence_high,
            governing_principles=[p.id for p in governing],
            cited_observations=cited_observations,
            reasoning_chain=chain,
            implied_bet=self._sanitize_implied_bet(payload.get("implied_bet")),
        )
        memo_id = self._dispatch_memo(
            store=store,
            question=question,
            conclusion=conclusion,
        )
        return SynthesisResult(
            outcome=SynthesisOutcome.CONCLUDED,
            reasoning="Conclusion emitted; memo dispatched.",
            memo_id=memo_id,
            conclusion=conclusion,
            question_type=qtype,
            governing_principle_ids=[p.id for p in governing],
        )

    # ── Retrieval ──────────────────────────────────────────────

    def _filter_by_provenance(
        self,
        principles: Iterable[Principle],
        provenance_filter: ProvenanceFilter,
    ) -> list[Principle]:
        out: list[Principle] = []
        for p in principles:
            kind = coerce_provenance(p.provenance)
            if not provenance_filter(kind):
                continue
            out.append(p)
        return out

    def _filter_invocations_by_provenance(
        self,
        store: _SynthesizerStore,
        provenance_filter: ProvenanceFilter,
    ) -> list[AlgorithmInvocation]:
        """Collect recent invocations belonging to admissible algorithms.

        We pull the org's ACTIVE algorithms first so we can apply
        provenance at the algorithm level — an invocation's provenance
        is inherited from its parent algorithm (prompt 09).
        """

        try:
            algos = store.list_algorithms_for_org(self._organization_id)
        except Exception:
            return []
        out: list[AlgorithmInvocation] = []
        for algo in algos:
            kind = coerce_provenance(getattr(algo, "provenance", None))
            if not provenance_filter(kind):
                continue
            try:
                invocations = store.list_invocations_for_algorithm(algo.id, limit=20)
            except Exception:
                continue
            out.extend(invocations)
        return out

    def _retrieve_currents(
        self, store: _SynthesizerStore
    ) -> list[CurrentEvent]:
        try:
            ids = store.list_current_event_ids_by_status(
                ["OPINED", "ENRICHED"], limit=20
            )
        except Exception:
            return []
        out: list[CurrentEvent] = []
        for event_id in ids:
            try:
                evt = store.get_current_event(event_id)
            except Exception:
                continue
            if evt is not None:
                out.append(evt)
        return out

    # ── LLM call ───────────────────────────────────────────────

    def _call_llm(
        self,
        *,
        question: str,
        qtype: QuestionType,
        governing: Sequence[Principle],
        invocations: Sequence[AlgorithmInvocation],
        currents: Sequence[CurrentEvent],
        context: Mapping[str, Any],
    ) -> _LLMResponse:
        user = json.dumps(
            {
                "question": question,
                "question_type": qtype.value,
                "context": dict(context),
                "governing_principles": [
                    {
                        "id": p.id,
                        "text": p.text,
                        "disciplines": [
                            getattr(d, "value", str(d))
                            for d in (p.disciplines or [])
                        ],
                        "provenance": coerce_provenance(p.provenance).value,
                    }
                    for p in governing
                ],
                "algorithm_invocations": [
                    {
                        "id": inv.id,
                        "algorithm_id": inv.algorithm_id,
                        "derived_output": inv.derived_output,
                        "confidence_low": inv.confidence_low,
                        "confidence_high": inv.confidence_high,
                    }
                    for inv in invocations[:10]
                ],
                "currents": [
                    {
                        "id": evt.id,
                        "title": getattr(evt, "title", None),
                        "summary": getattr(evt, "summary", None)
                        or getattr(evt, "headline", None),
                    }
                    for evt in currents[:10]
                ],
            },
            sort_keys=True,
            default=str,
        )
        try:
            raw = self._llm.complete(
                system=self._system_prompt,
                user=user,
                max_tokens=self._llm_max_tokens,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(
                "synthesizer.llm_error", extra={"error": f"{type(exc).__name__}: {exc}"}
            )
            raise _LLMRefusedToReason(f"LLM call failed: {exc}") from exc
        try:
            obj = _extract_json_object(raw)
        except ValueError as exc:
            raise _LLMRefusedToReason(f"LLM produced unparseable JSON: {exc}") from exc
        tokens_used = (
            _estimate_tokens(self._system_prompt)
            + _estimate_tokens(user)
            + _estimate_tokens(raw)
        )
        return _LLMResponse(payload=obj, tokens_used=tokens_used)

    # ── Chain validation ───────────────────────────────────────

    def _parse_chain(
        self,
        payload: Mapping[str, Any],
        *,
        governing_ids: set[str],
    ) -> list[ReasoningChainStep]:
        steps_raw = payload.get("reasoning_chain")
        if not isinstance(steps_raw, list) or not steps_raw:
            raise _ChainValidationError("reasoning_chain is empty or not a list")
        out: list[ReasoningChainStep] = []
        for i, step in enumerate(steps_raw):
            if not isinstance(step, dict):
                raise _ChainValidationError(f"step {i} is not an object")
            principle_id = str(step.get("principle_id") or "").strip()
            if not principle_id:
                raise _ChainValidationError(
                    f"step {i} did not cite a principle_id"
                )
            if principle_id not in governing_ids:
                raise _ChainValidationError(
                    f"step {i} cites principle {principle_id!r} which is "
                    "not in the supplied governing-principles list "
                    "(fabricated citation refused)"
                )
            step_kind = str(step.get("step_kind") or "APPLY_PRINCIPLE").upper()
            if step_kind not in {"DETECT", "APPLY_PRINCIPLE", "SYNTHESIZE"}:
                raise _ChainValidationError(
                    f"step {i} has unknown step_kind {step_kind!r}"
                )
            derived = str(step.get("derived_fact") or "").strip()
            if not derived:
                raise _ChainValidationError(
                    f"step {i} did not produce a derived_fact"
                )
            obs_id_raw = step.get("observation_id")
            obs_id = str(obs_id_raw).strip() if obs_id_raw else None
            out.append(
                ReasoningChainStep(
                    step_kind=step_kind,
                    principle_id=principle_id,
                    derived_fact=derived,
                    observation_id=obs_id or None,
                )
            )
        return out

    # ── Contradiction check ────────────────────────────────────

    def _find_blocking_contradictions(
        self,
        store: _SynthesizerStore,
        cited_principle_ids: Sequence[str],
    ) -> list[str]:
        """Return contradiction-result ids that block the chain.

        A blocking contradiction has:

        * verdict == ``CONTRADICTORY``,
        * score strictly > :data:`CONTRADICTION_BLOCK_THRESHOLD`,
        * both endpoints among ``cited_principle_ids``, and
        * a lifecycle row whose ``current_status == STANDING`` (or
          when the lifecycle row is absent, the result is treated as
          freshly-detected and still blocking — the absence of a
          lifecycle row is not a permission to ignore the result).
        """

        wanted = set(cited_principle_ids)
        if len(wanted) < 2:
            return []
        try:
            results = store.list_contradiction_results(
                verdict="CONTRADICTORY", limit=200
            )
        except Exception:
            return []
        blocking: list[str] = []
        for row in results:
            a = getattr(row, "principle_a_id", None)
            b = getattr(row, "principle_b_id", None)
            if a not in wanted or b not in wanted:
                continue
            score = float(getattr(row, "score", 0.0) or 0.0)
            if score <= CONTRADICTION_BLOCK_THRESHOLD:
                continue
            lifecycle = None
            try:
                lifecycle = store.get_contradiction_lifecycle(row.id)
            except Exception:
                lifecycle = None
            if lifecycle is not None:
                status = getattr(
                    lifecycle, "current_status", None
                ) or getattr(lifecycle, "status", None)
                status_value = getattr(status, "value", str(status))
                # Only STANDING / DETECTED contradictions block. WEAKENED,
                # RESOLVED_BY_SOURCE, DISPUTED_AS_ERROR, SUBSUMED_BY_SYNTHESIS
                # are explicitly permitted — they have already been
                # adjudicated and should not block fresh synthesis.
                if status_value not in {"STANDING", "DETECTED"}:
                    continue
            blocking.append(row.id)
        return blocking

    # ── Memo dispatch ──────────────────────────────────────────

    def _dispatch_memo(
        self,
        *,
        store: _SynthesizerStore,
        question: str,
        conclusion: Conclusion,
    ) -> str:
        """Hand the conclusion off to the memo builder (prompt 11).

        Prompt 11 has not landed yet, so the memo is rendered inline
        here as a structured dict and persisted via
        ``store.put_synthesizer_memo`` when the store exposes that
        helper. A future prompt 11 will replace this inline builder
        with the full investment-memo format; both shapes share the
        ``memo_id`` and ``conclusion`` keys so consumers don't need to
        be rewritten.
        """

        memo_id = f"syn_{uuid.uuid4().hex[:24]}"
        memo: dict[str, Any] = {
            "id": memo_id,
            "organization_id": self._organization_id,
            "question": question,
            "conclusion": conclusion.to_dict(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "synthesizer_version": SYNTHESIZER_VERSION,
        }
        put_memo = getattr(store, "put_synthesizer_memo", None)
        if callable(put_memo):
            try:
                put_memo(memo)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "synthesizer.memo_persist_failed",
                    extra={
                        "memo_id": memo_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
        return memo_id

    # ── Misc ───────────────────────────────────────────────────

    @staticmethod
    def _sanitize_implied_bet(value: Any) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        if not isinstance(value, dict):
            return None
        # Pass-through; prompt 15 will tighten this to a polymorphic
        # BetSpec. Until then the synthesizer only enforces that the
        # field is a structured object, not a free-text string.
        return dict(value)


# ── Internal exceptions ────────────────────────────────────────────


class _ChainValidationError(Exception):
    """The LLM produced a chain that the engine refuses to accept."""


class _LLMRefusedToReason(Exception):
    """The LLM did not return parseable JSON."""


__all__ = [
    "CONTRADICTION_BLOCK_THRESHOLD",
    "Conclusion",
    "MAX_CONFIDENCE_BAND_WIDTH",
    "MIN_GOVERNING_PRINCIPLES",
    "ProvenanceFilter",
    "QuestionType",
    "ReasoningChainStep",
    "SYNTHESIZER_VERSION",
    "SynthesisOutcome",
    "SynthesisResult",
    "SynthesizerEngine",
    "constitute_question",
    "default_provenance_filter",
]
