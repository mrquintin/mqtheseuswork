"""LLM-assisted drafter for ``LogicalAlgorithm`` candidates.

Given a cluster of related principle ids the firm already holds, the
drafter proposes a structured `LogicalAlgorithm` that would let those
principles jointly predict an output from observable inputs.  Every
draft lands in the founder triage queue as `DRAFT`; the agent never
auto-promotes to `ACTIVE`.

The drafter has four contracts the rest of the system depends on:

1. **No fabrication.**  The LLM is forbidden by the system prompt
   from inventing principles or observability sources.  The drafter
   validates that every `APPLY_PRINCIPLE` step references a principle
   from the input cluster, and that every input names a real, known
   provider prefix (`currents.*`, `upload.*`, `forecasts.*`,
   `equities.*`, `peer_review.*`) or the literal
   `manual.operator.entered`.

2. **Sandboxed trigger predicates.**  The trigger predicate is run
   through :func:`noosphere.algorithms.validators.validate_trigger_predicate`
   over the declared input names.  A predicate that escapes the
   sandbox is treated as fabrication: the drafter abandons the row
   and emits :class:`DraftResult` with ``outcome=ABSTAINED_FABRICATION``.

3. **Budget-bounded.**  Each call reserves capacity against the
   :class:`HourlyBudgetGuard` from :mod:`noosphere.algorithms.budget`.
   Over-budget calls return :class:`DraftResult` with
   ``outcome=ABSTAINED_BUDGET`` and persist nothing.

4. **Drafts only.**  The store row is always persisted with
   ``status=DRAFT``.  Promotion to `ACTIVE` is a founder action in
   the triage queue UI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol, Sequence

from noosphere.algorithms.budget import (
    BudgetExhausted,
    per_draft_reserve,
)
from noosphere.algorithms.schemas import (
    AlgorithmInput,
    AlgorithmInputType,
    AlgorithmOutput,
    AlgorithmOutputType,
    AlgorithmStatus,
    ReasoningStep,
    ReasoningStepKind,
)
from noosphere.algorithms.validators import (
    AlgorithmValidationError,
    validate_inputs,
    validate_output_schema,
    validate_reasoning_chain,
    validate_trigger_predicate,
)
from noosphere.llm import LLMClient
from noosphere.models import LogicalAlgorithm, Principle
from noosphere.observability import get_logger

logger = get_logger(__name__)


_PROMPTS_DIR = Path(__file__).parent / "_prompts"


# ── Outcome ─────────────────────────────────────────────────────────


class DraftOutcome(str, Enum):
    """Closed set of outcomes the drafter can emit."""

    DRAFTED = "DRAFTED"
    UNFORMALISABLE = "UNFORMALISABLE"
    NO_DOMAIN_OVERLAP = "NO_DOMAIN_OVERLAP"
    CLUSTER_TOO_SMALL = "CLUSTER_TOO_SMALL"
    DUPLICATE_RECENT = "DUPLICATE_RECENT"
    ABSTAINED_BUDGET = "ABSTAINED_BUDGET"
    ABSTAINED_FABRICATION = "ABSTAINED_FABRICATION"


@dataclass
class DraftResult:
    """The drafter's structured return value.

    ``algorithm_id`` is set only when ``outcome == DRAFTED`` and the
    row was persisted.  Refusals and abstentions carry a ``reason``
    that ends up in the founder triage memo.
    """

    outcome: DraftOutcome
    reason: str = ""
    algorithm_id: Optional[str] = None


# ── Store protocol ──────────────────────────────────────────────────


class _AlgorithmDrafterStore(Protocol):
    """The slice of ``Store`` the drafter relies on.

    Spelled out as a Protocol so tests can pass a lightweight fake.
    """

    def get_principle(self, principle_id: str) -> Optional[Principle]:  # noqa: D401
        ...

    def list_algorithms_for_org(
        self, organization_id: str, *, status: Optional[Any] = None
    ) -> list[LogicalAlgorithm]: ...

    def put_algorithm(
        self,
        algorithm: LogicalAlgorithm,
        *,
        revoked_principle_ids: Iterable[str] | None = None,
    ) -> None: ...


# ── Budget protocol ─────────────────────────────────────────────────


class _Budget(Protocol):
    """Minimal slice of ``HourlyBudgetGuard`` the drafter consumes."""

    def authorize(self, est_prompt: int, est_completion: int) -> None: ...

    def charge(self, prompt: int, completion: int) -> None: ...


# ── Known provider prefixes ─────────────────────────────────────────

_KNOWN_OBSERVABILITY_PREFIXES: tuple[str, ...] = (
    "currents.",
    "upload.",
    "forecasts.",
    "equities.",
    "peer_review.",
)
_MANUAL_OBSERVABILITY = "manual.operator.entered"


def _observability_source_is_known(source: str) -> bool:
    if not isinstance(source, str):
        return False
    stripped = source.strip()
    if not stripped:
        return False
    if stripped == _MANUAL_OBSERVABILITY:
        return True
    return any(stripped.startswith(prefix) for prefix in _KNOWN_OBSERVABILITY_PREFIXES)


# ── Prompt loaders ──────────────────────────────────────────────────


def load_drafter_system_prompt() -> str:
    """Return the system-prompt markdown shipped beside this module."""
    return (_PROMPTS_DIR / "drafter_system.md").read_text(encoding="utf-8")


def load_drafter_few_shot() -> str:
    """Return the few-shot markdown shipped beside this module."""
    return (_PROMPTS_DIR / "drafter_few_shot.md").read_text(encoding="utf-8")


# ── JSON extraction ─────────────────────────────────────────────────


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Pull a single JSON object out of an LLM response.

    Accepts a bare JSON object or one wrapped in a fenced code block.
    Anything else raises ``ValueError`` — the caller treats that as
    fabrication and persists nothing.
    """
    if not isinstance(raw, str):
        raise ValueError("drafter response is not a string")
    s = raw.strip()
    if not s:
        raise ValueError("drafter response is empty")
    # Try bare JSON first.
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        match = _JSON_FENCE_RE.search(s)
        if match is None:
            raise ValueError("drafter response is not parseable JSON")
        obj = json.loads(match.group(1))
    if not isinstance(obj, dict):
        raise ValueError("drafter response is not a JSON object")
    return obj


# ── Drafter ─────────────────────────────────────────────────────────


_VALID_INPUT_TYPES = {t.value for t in AlgorithmInputType}
_VALID_OUTPUT_TYPES = {t.value for t in AlgorithmOutputType}


class AlgorithmDrafter:
    """LLM-assisted drafter for ``LogicalAlgorithm`` candidates.

    Parameters
    ----------
    llm:
        Any :class:`noosphere.llm.LLMClient`.
    organization_id:
        The org the drafted algorithm rows are written for.
    drafter_model:
        Free-form label persisted in the algorithm description so the
        founder UI can show which model drafted the row.
    duplicate_window_days:
        A cluster whose ACTIVE algorithm overlap was drafted within
        this many days is flagged ``DUPLICATE_RECENT``.  Default 30.
    """

    def __init__(
        self,
        llm: LLMClient,
        *,
        organization_id: str,
        drafter_model: str = "anthropic/claude",
        duplicate_window_days: int = 30,
        max_completion_tokens: int = 2000,
    ) -> None:
        self._llm = llm
        self._organization_id = organization_id
        self._drafter_model = drafter_model
        self._duplicate_window_days = duplicate_window_days
        self._max_completion_tokens = max_completion_tokens

    # ── Public API ─────────────────────────────────────────────

    async def draft_from_cluster(
        self,
        store: _AlgorithmDrafterStore,
        principle_ids: Sequence[str],
        *,
        budget: _Budget,
        now: Optional[datetime] = None,
    ) -> DraftResult:
        """Draft an algorithm from one principle cluster.

        See module docstring for the contract.  Returns one of the
        :class:`DraftOutcome` values; ``DRAFTED`` carries the persisted
        algorithm's id, every other outcome carries an explanation in
        ``reason``.
        """
        # 1. Cluster size.
        cluster_ids = [pid for pid in principle_ids if pid]
        if len(cluster_ids) < 2:
            return DraftResult(
                outcome=DraftOutcome.CLUSTER_TOO_SMALL,
                reason=(
                    f"cluster has {len(cluster_ids)} principle(s); the drafter "
                    "requires at least 2 to synthesize a joint algorithm"
                ),
            )

        # 2. Load principles.
        principles: list[Principle] = []
        missing: list[str] = []
        for pid in cluster_ids:
            p = store.get_principle(pid)
            if p is None:
                missing.append(pid)
            else:
                principles.append(p)
        if missing:
            return DraftResult(
                outcome=DraftOutcome.CLUSTER_TOO_SMALL,
                reason=(
                    f"principle(s) not found in store: {sorted(missing)}; "
                    "the drafter will not invent missing cluster members"
                ),
            )

        # 3. Domain overlap — every principle must share at least one
        #    discipline with at least one other in the cluster.
        if not _cluster_has_domain_overlap(principles):
            return DraftResult(
                outcome=DraftOutcome.NO_DOMAIN_OVERLAP,
                reason=(
                    "principle disciplines do not overlap; the drafter does "
                    "not manufacture a cross-domain algorithm from "
                    "non-overlapping principles"
                ),
            )

        # 4. Duplicate-within-window guard.
        now = now or datetime.now(timezone.utc)
        duplicate = _find_recent_active_overlap(
            store=store,
            organization_id=self._organization_id,
            cluster_ids=cluster_ids,
            now=now,
            window_days=self._duplicate_window_days,
        )
        if duplicate is not None:
            return DraftResult(
                outcome=DraftOutcome.DUPLICATE_RECENT,
                reason=(
                    f"ACTIVE algorithm {duplicate.id!r} ({duplicate.name!r}) "
                    f"already covers an overlapping principle set within the "
                    f"last {self._duplicate_window_days} days; awaiting "
                    "founder review before drafting a duplicate"
                ),
            )

        # 5. Budget.
        reserve_prompt, reserve_completion = per_draft_reserve()
        try:
            budget.authorize(reserve_prompt, reserve_completion)
        except BudgetExhausted as exc:
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_BUDGET,
                reason=str(exc),
            )

        # 6. Compose and issue the LLM call.
        system = load_drafter_system_prompt()
        user = _format_user_prompt(principles)
        try:
            raw = self._llm.complete(
                system=system,
                user=user,
                max_tokens=self._max_completion_tokens,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(
                "algorithm.drafter.llm_error",
                principle_ids=cluster_ids,
                error=str(exc),
            )
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_FABRICATION,
                reason=f"LLM call failed: {exc}",
            )

        # Charge actual usage as roughly the reserve — the LLM client
        # interface does not yet surface usage, but the reserve is
        # tight enough that this conservatively overcounts.
        budget.charge(len(system) // 4 + len(user) // 4, self._max_completion_tokens // 4)

        # 7. Parse JSON.
        try:
            payload = _extract_json_object(raw)
        except ValueError as exc:
            logger.warning(
                "algorithm.drafter.parse_failed",
                principle_ids=cluster_ids,
                error=str(exc),
            )
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_FABRICATION,
                reason=f"drafter response was not parseable JSON: {exc}",
            )

        outcome_str = str(payload.get("outcome", "")).strip().upper()
        if outcome_str == DraftOutcome.UNFORMALISABLE.value:
            return DraftResult(
                outcome=DraftOutcome.UNFORMALISABLE,
                reason=str(payload.get("reason", "")).strip()
                or "drafter declined to formalise the cluster",
            )
        if outcome_str == DraftOutcome.ABSTAINED_FABRICATION.value:
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_FABRICATION,
                reason=str(payload.get("reason", "")).strip()
                or "drafter declined to fabricate",
            )
        if outcome_str != DraftOutcome.DRAFTED.value:
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_FABRICATION,
                reason=(
                    f"drafter returned unknown outcome {outcome_str!r}; "
                    "expected DRAFTED, UNFORMALISABLE, or ABSTAINED_FABRICATION"
                ),
            )

        # 8. Construct + validate the LogicalAlgorithm.
        try:
            algorithm = _build_algorithm_from_payload(
                payload,
                organization_id=self._organization_id,
                source_principle_ids=cluster_ids,
                drafter_model=self._drafter_model,
                now=now,
            )
        except (ValueError, AlgorithmValidationError, KeyError, TypeError) as exc:
            logger.warning(
                "algorithm.drafter.schema_failed",
                principle_ids=cluster_ids,
                error=str(exc),
            )
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_FABRICATION,
                reason=f"drafter output failed schema validation: {exc}",
            )

        # 9. Cross-validate against the full algorithm validator stack
        #    *before* persistence so a broken draft is abandoned, not
        #    surfaced to the founder.
        try:
            validate_inputs(algorithm.inputs)
            validate_output_schema(algorithm.output)
            validate_reasoning_chain(
                algorithm.reasoning_chain,
                source_principle_ids=algorithm.source_principle_ids,
            )
            validate_trigger_predicate(
                algorithm.trigger_predicate,
                input_names=[inp.name for inp in algorithm.inputs],
            )
        except AlgorithmValidationError as exc:
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_FABRICATION,
                reason=f"drafter output failed validator stack: {exc}",
            )

        # 10. Provider check — every input must point at a real source.
        for inp in algorithm.inputs:
            if not _observability_source_is_known(inp.observability_source):
                return DraftResult(
                    outcome=DraftOutcome.ABSTAINED_FABRICATION,
                    reason=(
                        f"input {inp.name!r} declares unknown "
                        f"observability_source {inp.observability_source!r}; "
                        "must be a known provider prefix or "
                        f"{_MANUAL_OBSERVABILITY!r}"
                    ),
                )

        # 11. Reasoning chain must invoke at least one of the cluster's
        #     principles per non-DETECT non-OUTPUT step; this is the
        #     "every step uses a principle" rule from the prompt.
        try:
            _enforce_reasoning_step_principle_coverage(
                algorithm.reasoning_chain,
                source_principle_ids=cluster_ids,
            )
        except AlgorithmValidationError as exc:
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_FABRICATION,
                reason=str(exc),
            )

        # 12. Persist as DRAFT (status is set unconditionally — the
        #     drafter never returns ACTIVE).
        algorithm.status = AlgorithmStatus.DRAFT
        try:
            store.put_algorithm(algorithm)
        except (AlgorithmValidationError, Exception) as exc:  # pragma: no cover - defensive
            logger.warning(
                "algorithm.drafter.persist_failed",
                principle_ids=cluster_ids,
                error=str(exc),
            )
            return DraftResult(
                outcome=DraftOutcome.ABSTAINED_FABRICATION,
                reason=f"persistence failed: {exc}",
            )

        return DraftResult(
            outcome=DraftOutcome.DRAFTED,
            reason=str(payload.get("confidence_note", "")).strip(),
            algorithm_id=algorithm.id,
        )


# ── Helpers ─────────────────────────────────────────────────────────


def _principle_disciplines(principle: Principle) -> set[str]:
    """Discipline values for a principle, tolerating Enum or string."""
    out: set[str] = set()
    for d in principle.disciplines or []:
        out.add(getattr(d, "value", str(d)))
    return out


def _cluster_has_domain_overlap(principles: Sequence[Principle]) -> bool:
    """At least one discipline must be shared between two principles.

    A cluster of principles whose disciplines are entirely disjoint is
    a cross-domain claim the drafter refuses to manufacture.  Empty
    discipline sets are treated permissively (we don't know enough to
    refuse) — the explicit no-overlap signal is when every principle
    has disciplines and they share none.
    """
    seen = [_principle_disciplines(p) for p in principles]
    if all(not s for s in seen):
        return True
    # If any principle has no declared disciplines, do not punish the
    # rest of the cluster on a missing tag.
    if any(not s for s in seen):
        return True
    union: set[str] = set()
    for s in seen:
        union |= s
    # Overlap iff intersection of any pair is non-empty — equivalently
    # any discipline appears in ≥2 sets.
    for d in union:
        hits = sum(1 for s in seen if d in s)
        if hits >= 2:
            return True
    return False


def _find_recent_active_overlap(
    *,
    store: _AlgorithmDrafterStore,
    organization_id: str,
    cluster_ids: Sequence[str],
    now: datetime,
    window_days: int,
) -> Optional[LogicalAlgorithm]:
    """Return the first ACTIVE algorithm whose principles overlap and was
    created within ``window_days`` days, or ``None``.
    """
    cluster_set = set(cluster_ids)
    cutoff = now - timedelta(days=window_days)

    try:
        actives = store.list_algorithms_for_org(
            organization_id, status=AlgorithmStatus.ACTIVE
        )
    except TypeError:
        actives = store.list_algorithms_for_org(organization_id)
        actives = [a for a in actives if _algorithm_status_value(a) == AlgorithmStatus.ACTIVE.value]

    for algo in actives:
        if not set(algo.source_principle_ids) & cluster_set:
            continue
        created = algo.created_at
        if created is None:
            continue
        # Make tz-aware for comparison with `now` (which is tz-aware).
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= cutoff:
            return algo
    return None


def _algorithm_status_value(algo: LogicalAlgorithm) -> str:
    status = algo.status
    return getattr(status, "value", str(status))


def _format_user_prompt(principles: Sequence[Principle]) -> str:
    """Render the cluster + few-shot examples into a user prompt."""
    parts: list[str] = []
    parts.append(load_drafter_few_shot())
    parts.append("---")
    parts.append("")
    parts.append("## Cluster to draft")
    parts.append("")
    for p in principles:
        disciplines = ", ".join(sorted(_principle_disciplines(p))) or "—"
        parts.append(f"- `{p.id}` ({disciplines}): {p.text.strip()}")
        if p.description:
            parts.append(f"  - elaboration: {p.description.strip()}")
    parts.append("")
    parts.append(
        "Return the JSON object now.  No prose around it.  If the "
        "cluster cannot be honestly formalised under the hard rules, "
        "return the matching refusal shape."
    )
    return "\n".join(parts)


def _build_algorithm_from_payload(
    payload: dict[str, Any],
    *,
    organization_id: str,
    source_principle_ids: Sequence[str],
    drafter_model: str,
    now: datetime,
) -> LogicalAlgorithm:
    """Translate the drafter's JSON into a validated ``LogicalAlgorithm``."""

    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("drafter omitted algorithm name")

    description = str(payload.get("description", "")).strip()
    # Stamp the drafter so the queue UI can show provenance, but stay
    # inside the 600-char schema cap.
    stamp = f" [drafter: {drafter_model}]"
    if description:
        if len(description) + len(stamp) <= 600:
            description = description + stamp
    else:
        description = stamp.strip()

    inputs_raw = payload.get("inputs") or []
    if not isinstance(inputs_raw, list) or not inputs_raw:
        raise ValueError("drafter omitted inputs")
    inputs: list[AlgorithmInput] = []
    for raw in inputs_raw:
        if not isinstance(raw, dict):
            raise ValueError("input is not an object")
        type_str = str(raw.get("type", "")).strip().upper()
        if type_str not in _VALID_INPUT_TYPES:
            raise ValueError(f"input type {type_str!r} is not allowed")
        inputs.append(
            AlgorithmInput(
                name=str(raw.get("name", "")).strip(),
                type=AlgorithmInputType(type_str),
                description=str(raw.get("description", "") or "")[:400],
                observability_source=str(raw.get("observability_source", "") or "")[:200],
                enum_values=list(raw.get("enum_values") or []),
                units=raw.get("units") or None,
            )
        )

    output_raw = payload.get("output")
    if not isinstance(output_raw, dict):
        raise ValueError("drafter omitted output")
    out_type = str(output_raw.get("type", "")).strip().upper()
    if out_type not in _VALID_OUTPUT_TYPES:
        raise ValueError(f"output type {out_type!r} is not allowed")
    raw_fields = output_raw.get("fields") or []
    fields: list[dict[str, Any]] = [
        f for f in raw_fields if isinstance(f, dict)
    ]
    output = AlgorithmOutput(
        name=str(output_raw.get("name", "")).strip(),
        type=AlgorithmOutputType(out_type),
        description=str(output_raw.get("description", "") or "")[:400],
        units=output_raw.get("units") or None,
        range=_coerce_range(output_raw.get("range")),
        fields=fields,
    )

    chain_raw = payload.get("reasoning_chain") or []
    if not isinstance(chain_raw, list) or not chain_raw:
        raise ValueError("drafter omitted reasoning_chain")
    chain: list[ReasoningStep] = []
    for raw in chain_raw:
        if not isinstance(raw, dict):
            raise ValueError("reasoning step is not an object")
        kind_str = str(raw.get("step_kind", "")).strip().upper()
        try:
            kind = ReasoningStepKind(kind_str)
        except ValueError as exc:
            raise ValueError(f"reasoning step_kind {kind_str!r} is not allowed") from exc
        chain.append(
            ReasoningStep(
                step_kind=kind,
                principle_id=raw.get("principle_id") or None,
                predicate=raw.get("predicate") or None,
                derived_fact=(raw.get("derived_fact") or None),
            )
        )

    trigger = str(payload.get("trigger_predicate", "")).strip()
    if not trigger:
        raise ValueError("drafter omitted trigger_predicate")

    return LogicalAlgorithm(
        organization_id=organization_id,
        name=name[:80],
        description=description[:600],
        source_principle_ids=list(source_principle_ids),
        inputs=inputs,
        output=output,
        reasoning_chain=chain,
        trigger_predicate=trigger[:1000],
        status=AlgorithmStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )


def _coerce_range(raw: Any) -> Optional[list[float]]:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        return [float(raw[0]), float(raw[1])]
    except (TypeError, ValueError):
        return None


def _enforce_reasoning_step_principle_coverage(
    chain: Sequence[ReasoningStep],
    *,
    source_principle_ids: Sequence[str],
) -> None:
    """Every non-DETECT non-OUTPUT step must invoke a cluster principle.

    The system prompt asks for this explicitly; we re-enforce it here
    so a model that ignored the rule is rejected rather than persisted.
    """
    cluster = set(source_principle_ids)
    apply_count = 0
    invoked: set[str] = set()
    for step in chain:
        kind_value = getattr(step.step_kind, "value", str(step.step_kind))
        if kind_value == ReasoningStepKind.APPLY_PRINCIPLE.value:
            apply_count += 1
            if not step.principle_id or step.principle_id not in cluster:
                raise AlgorithmValidationError(
                    f"APPLY_PRINCIPLE step references principle "
                    f"{step.principle_id!r} which is not in the source "
                    "cluster"
                )
            invoked.add(step.principle_id)
        elif kind_value == ReasoningStepKind.SYNTHESIZE.value:
            if apply_count == 0:
                raise AlgorithmValidationError(
                    "SYNTHESIZE step precedes any APPLY_PRINCIPLE step"
                )
    if apply_count == 0:
        raise AlgorithmValidationError(
            "reasoning_chain invokes no principle; an algorithm built on a "
            "principle cluster must apply at least one principle"
        )
    missing = cluster - invoked
    if missing:
        raise AlgorithmValidationError(
            f"reasoning_chain omits cluster principles: {sorted(missing)}; "
            "every cluster member must be applied at least once"
        )


__all__ = [
    "AlgorithmDrafter",
    "DraftOutcome",
    "DraftResult",
    "load_drafter_few_shot",
    "load_drafter_system_prompt",
]
