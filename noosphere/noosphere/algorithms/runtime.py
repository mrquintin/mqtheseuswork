"""Runtime for the LogicalAlgorithm layer.

The runtime takes ACTIVE algorithms and fires them against the world.
For each algorithm it resolves every declared input, evaluates the
trigger predicate in a sandbox, and (on a true predicate) walks the
reasoning chain step-by-step to produce an :class:`AlgorithmInvocation`
with a derived output and a human-readable trace.

The runtime never places a bet — it persists a structured ``bet_implied``
pointer that the portfolio agent (prompt 12) decides whether to act on.
The runtime never modifies the algorithm; algorithm edits go through
the triage UI (prompt 02).

Idempotency: per (algorithm_id, sha256(canonical_input_json)), the
runtime refuses to emit a second invocation within
``IDEMPOTENCY_WINDOW_SECONDS`` (default 600).

Sandbox: trigger predicates are re-validated through
``validate_trigger_predicate`` on every fire. Three refusals in a row
auto-pause the algorithm via the store helper. The portfolio operator
sees the pause and the structured-log warning explaining why.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence
from types import SimpleNamespace

from noosphere.algorithms.adapters import InputObservation
from noosphere.algorithms.input_resolver import InputResolver
from noosphere.algorithms.schemas import (
    AlgorithmCorrectness,
    AlgorithmStatus,
    ReasoningStepKind,
)
from noosphere.algorithms.validators import (
    AlgorithmValidationError,
    validate_trigger_predicate,
)
from noosphere.llm import LLMClient
from noosphere.models import (
    AlgorithmInputObservation,
    AlgorithmInvocation,
    LogicalAlgorithm,
)
from noosphere.observability import get_logger


logger = get_logger(__name__)


# ── Tunables ────────────────────────────────────────────────────────


DEFAULT_IDEMPOTENCY_WINDOW_SECONDS = 600
DEFAULT_MAX_TOKENS_PER_FIRE = 6_000
DEFAULT_SANDBOX_REFUSAL_THRESHOLD = 3
DEFAULT_LLM_MAX_TOKENS = 600


def _idempotency_window_seconds() -> int:
    raw = os.environ.get("ALGORITHMS_IDEMPOTENCY_WINDOW_S", "").strip()
    if not raw:
        return DEFAULT_IDEMPOTENCY_WINDOW_SECONDS
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_IDEMPOTENCY_WINDOW_SECONDS


def _max_tokens_per_fire() -> int:
    raw = os.environ.get("ALGORITHMS_MAX_TOKENS_PER_FIRE", "").strip()
    if not raw:
        return DEFAULT_MAX_TOKENS_PER_FIRE
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MAX_TOKENS_PER_FIRE


# ── Outcome types ───────────────────────────────────────────────────


@dataclass
class TickResult:
    """Aggregated outcome of a single :meth:`AlgorithmRuntime.tick_once`."""

    fired: int = 0
    skipped_no_input: int = 0
    skipped_predicate_false: int = 0
    skipped_idempotent: int = 0
    skipped_sandbox: int = 0
    skipped_token_cap: int = 0
    errors: list[str] = field(default_factory=list)
    invocation_ids: list[str] = field(default_factory=list)


@dataclass
class ResolutionTickResult:
    """Aggregated outcome of a single :meth:`AlgorithmRuntime.resolution_tick_once`."""

    considered: int = 0
    resolved: int = 0
    skipped_not_due: int = 0
    skipped_unresolvable: int = 0
    errors: list[str] = field(default_factory=list)


# ── Outcome resolver protocol ───────────────────────────────────────


OutcomeResolver = Callable[
    [LogicalAlgorithm, AlgorithmInvocation, InputResolver],
    Awaitable["OutcomeResolution"],
]


@dataclass
class OutcomeResolution:
    """What reality returned for an invocation past its horizon."""

    actual_outcome: dict[str, Any]
    correctness: AlgorithmCorrectness
    brier_equivalent: Optional[float] = None
    resolved_at: Optional[datetime] = None


# ── Sandbox eval ────────────────────────────────────────────────────


class SandboxRefused(Exception):
    """Raised when a trigger predicate fails sandbox re-validation."""


def _safe_eval_predicate(
    predicate: str,
    *,
    declared_input_names: Sequence[str],
    input_values: Mapping[str, Any],
) -> bool:
    """Re-validate then ``eval`` a trigger predicate.

    The validator stack already ran at promotion time, but predicates
    are persisted as strings — a corrupted DB row or an attacker who
    bypassed the store helper could ship a payload we should refuse to
    execute. Re-validating on every fire is cheap insurance.
    """

    try:
        validate_trigger_predicate(predicate, input_names=declared_input_names)
    except AlgorithmValidationError as exc:
        raise SandboxRefused(str(exc)) from exc

    ns = SimpleNamespace(**dict(input_values))
    try:
        result = eval(  # noqa: S307 — sandbox enforced by validator
            predicate,
            {"__builtins__": {}},
            {"input": ns},
        )
    except Exception as exc:
        raise SandboxRefused(f"predicate eval failed: {exc}") from exc
    return bool(result)


# ── JSON canonicalisation for the idempotency key ───────────────────


def canonical_input_hash(trigger_inputs: Mapping[str, Any]) -> str:
    """Deterministic sha256 over the sorted input map.

    Values are JSON-encoded with sort_keys=True so float/dict ordering
    cannot perturb the key. Non-JSON values (datetime, Decimal) are
    coerced via ``default=str`` — the contract is *stable bytes for
    the same observation*, not a round-trippable serialisation.
    """

    canon = json.dumps(dict(trigger_inputs), sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ── JSON helpers for the synthesizer output ─────────────────────────


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
    """Cheap token estimate: chars / 4. Tight enough for budgeting."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ── Store protocol (subset the runtime relies on) ───────────────────


class _RuntimeStore:
    """The Store methods the runtime uses; ducktyped for tests."""

    def list_active_algorithms(
        self, *, organization_id: Optional[str] = None
    ) -> list[LogicalAlgorithm]: ...

    def put_invocation(self, invocation: AlgorithmInvocation) -> None: ...

    def put_input_observation(
        self, observation: AlgorithmInputObservation
    ) -> None: ...

    def list_invocations_for_algorithm(
        self, algorithm_id: str, *, limit: int = 200
    ) -> list[AlgorithmInvocation]: ...

    def list_unresolved_invocations(
        self, *, organization_id: Optional[str] = None, limit: int = 200
    ) -> list[AlgorithmInvocation]: ...

    def set_invocation_resolution(
        self,
        invocation_id: str,
        *,
        actual_outcome: dict[str, Any],
        correctness: Any,
        brier_equivalent: Optional[float] = None,
        resolved_at: Optional[datetime] = None,
    ) -> AlgorithmInvocation: ...

    def set_algorithm_status(
        self,
        algorithm_id: str,
        new_status: Any,
        *,
        retired_reason: Optional[str] = None,
        revoked_principle_ids: Optional[Sequence[str]] = None,
    ) -> LogicalAlgorithm: ...


# ── Runtime ─────────────────────────────────────────────────────────


class AlgorithmRuntime:
    """Drive ACTIVE algorithms forward against live observability.

    Parameters
    ----------
    resolver:
        The :class:`InputResolver` wired up with the production adapter
        registry (or a test registry).
    llm:
        An :class:`LLMClient`. The runtime asks it to write the derived
        fact for ``APPLY_PRINCIPLE`` steps and the structured output
        for the terminal ``OUTPUT`` step. ``MockLLMClient`` is fine for
        tests.
    organization_id:
        Tenant whose ACTIVE algorithms the runtime ticks.
    idempotency_window_seconds:
        How long a (algorithm, input-hash) collision counts as a
        replay. Reads ``ALGORITHMS_IDEMPOTENCY_WINDOW_S`` if unset.
    max_tokens_per_fire:
        Per-fire combined prompt+completion ceiling. Reads
        ``ALGORITHMS_MAX_TOKENS_PER_FIRE`` if unset (default 6000).
    sandbox_refusal_threshold:
        Number of consecutive sandbox refusals after which the runtime
        auto-pauses the algorithm. Default 3.
    outcome_resolver:
        Optional callable the resolution-tick uses to compute the
        actual outcome at horizon. Defaults to a re-resolution of every
        declared input; the returned ``actual_outcome`` then carries the
        current input snapshot and correctness is ``INDETERMINATE``.
    llm_max_tokens:
        Per-call ``max_tokens`` for the LLM. Capped by the per-fire
        budget; if the budget cannot fit one call, the runtime abstains.
    """

    def __init__(
        self,
        *,
        resolver: InputResolver,
        llm: LLMClient,
        organization_id: str,
        idempotency_window_seconds: Optional[int] = None,
        max_tokens_per_fire: Optional[int] = None,
        sandbox_refusal_threshold: int = DEFAULT_SANDBOX_REFUSAL_THRESHOLD,
        outcome_resolver: Optional[OutcomeResolver] = None,
        llm_max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> None:
        self._resolver = resolver
        self._llm = llm
        self._organization_id = organization_id
        self._idempotency_window = (
            idempotency_window_seconds
            if idempotency_window_seconds is not None
            else _idempotency_window_seconds()
        )
        self._max_tokens_per_fire = (
            max_tokens_per_fire
            if max_tokens_per_fire is not None
            else _max_tokens_per_fire()
        )
        self._sandbox_refusal_threshold = max(1, int(sandbox_refusal_threshold))
        self._outcome_resolver = outcome_resolver
        self._llm_max_tokens = max(1, int(llm_max_tokens))
        self._sandbox_refusal_counts: dict[str, int] = {}

    @property
    def resolver(self) -> InputResolver:
        return self._resolver

    # ── Public API ─────────────────────────────────────────────

    async def tick_once(
        self,
        store: _RuntimeStore,
        *,
        now: Optional[datetime] = None,
    ) -> TickResult:
        """Walk every ACTIVE algorithm for the org and fire matches."""

        when = now or datetime.now(timezone.utc)
        result = TickResult()
        try:
            algorithms = store.list_active_algorithms(
                organization_id=self._organization_id
            )
        except Exception as exc:
            result.errors.append(f"list_active_algorithms:{type(exc).__name__}: {exc}")
            return result

        for algorithm in algorithms:
            try:
                await self._tick_one_algorithm(
                    algorithm=algorithm,
                    store=store,
                    when=when,
                    result=result,
                )
            except Exception as exc:
                # Robust to a single algorithm's failure: trap and
                # continue so algorithm B's tick is not stopped by A.
                result.errors.append(
                    f"algorithm:{algorithm.id}:{type(exc).__name__}: {exc}"
                )
                logger.warning(
                    "algorithms.runtime.algorithm_crashed",
                    algorithm_id=algorithm.id,
                    error=f"{type(exc).__name__}: {exc}",
                )
        return result

    async def fire_algorithm(
        self,
        store: _RuntimeStore,
        *,
        algorithm: LogicalAlgorithm,
        forced_inputs: Mapping[str, Any],
        now: Optional[datetime] = None,
        forced: bool = True,
    ) -> Optional[AlgorithmInvocation]:
        """Force-fire an algorithm against an operator-provided input map.

        Used by ``noosphere algorithms fire`` for debugging. The
        invocation row is tagged with ``forced=True`` inside
        ``derived_output['_meta']`` so the founder UI can filter it out
        of the live track-record.
        """

        when = now or datetime.now(timezone.utc)
        observations: dict[str, InputObservation] = {}
        for inp in algorithm.inputs:
            if inp.name not in forced_inputs:
                logger.warning(
                    "algorithms.runtime.forced_missing_input",
                    algorithm_id=algorithm.id,
                    input_name=inp.name,
                )
                return None
            observations[inp.name] = InputObservation(
                value=forced_inputs[inp.name],
                observed_at=when,
                source=inp.observability_source or "manual.fire",
                source_url=None,
                source_artifact_id=None,
            )

        return await self._execute_fire(
            algorithm=algorithm,
            observations=observations,
            store=store,
            when=when,
            forced=forced,
            token_budget=self._max_tokens_per_fire,
        )

    async def resolution_tick_once(
        self,
        store: _RuntimeStore,
        *,
        now: Optional[datetime] = None,
    ) -> ResolutionTickResult:
        """Resolve invocations past their predicted horizon."""

        when = now or datetime.now(timezone.utc)
        result = ResolutionTickResult()
        try:
            unresolved = store.list_unresolved_invocations(
                organization_id=self._organization_id, limit=500
            )
        except Exception as exc:
            result.errors.append(
                f"list_unresolved_invocations:{type(exc).__name__}: {exc}"
            )
            return result

        for invocation in unresolved:
            result.considered += 1
            horizon_s = float(invocation.predicted_horizon or 0.0)
            invoked_at = _as_utc(invocation.invoked_at)
            due_at = invoked_at + timedelta(seconds=horizon_s)
            if when < due_at:
                result.skipped_not_due += 1
                continue
            # Reload the parent algorithm so the outcome resolver has the
            # input schema to walk.
            algorithm = None
            try:
                algorithm = _load_algorithm(store, invocation.algorithm_id)
            except Exception as exc:
                result.errors.append(
                    f"load_algorithm:{invocation.algorithm_id}:{type(exc).__name__}: {exc}"
                )
            if algorithm is None:
                result.skipped_unresolvable += 1
                continue
            try:
                resolution = await self._resolve_outcome(algorithm, invocation)
            except Exception as exc:
                result.errors.append(
                    f"resolve_outcome:{invocation.id}:{type(exc).__name__}: {exc}"
                )
                continue
            if resolution is None:
                result.skipped_unresolvable += 1
                continue
            try:
                store.set_invocation_resolution(
                    invocation.id,
                    actual_outcome=resolution.actual_outcome,
                    correctness=resolution.correctness,
                    brier_equivalent=resolution.brier_equivalent,
                    resolved_at=resolution.resolved_at or when,
                )
            except Exception as exc:
                result.errors.append(
                    f"persist_resolution:{invocation.id}:{type(exc).__name__}: {exc}"
                )
                continue
            result.resolved += 1
            logger.info(
                "algorithms.runtime.invocation_resolved",
                invocation_id=invocation.id,
                algorithm_id=invocation.algorithm_id,
                correctness=getattr(
                    resolution.correctness, "value", str(resolution.correctness)
                ),
                brier_equivalent=resolution.brier_equivalent,
            )
        return result

    # ── Algorithm-scoped helpers ───────────────────────────────

    async def _tick_one_algorithm(
        self,
        *,
        algorithm: LogicalAlgorithm,
        store: _RuntimeStore,
        when: datetime,
        result: TickResult,
    ) -> None:
        # 1. Resolve every declared input.
        observations: dict[str, InputObservation] = {}
        missing: list[str] = []
        for inp in algorithm.inputs:
            obs = await self._resolver.resolve(inp)
            if obs is None:
                missing.append(inp.name)
            else:
                observations[inp.name] = obs
        if missing:
            result.skipped_no_input += 1
            logger.info(
                "algorithms.runtime.skip_input_unavailable",
                algorithm_id=algorithm.id,
                algorithm_name=algorithm.name,
                missing=missing,
            )
            return

        # 2. Sandbox-evaluate the trigger predicate.
        input_values = {name: obs.value for name, obs in observations.items()}
        try:
            fires = _safe_eval_predicate(
                algorithm.trigger_predicate,
                declared_input_names=[inp.name for inp in algorithm.inputs],
                input_values=input_values,
            )
        except SandboxRefused as exc:
            self._record_sandbox_refusal(store, algorithm, reason=str(exc))
            result.skipped_sandbox += 1
            return

        # A clean eval clears the refusal counter for this algorithm.
        self._sandbox_refusal_counts.pop(algorithm.id, None)

        if not fires:
            result.skipped_predicate_false += 1
            logger.info(
                "algorithms.runtime.skip_predicate_false",
                algorithm_id=algorithm.id,
                algorithm_name=algorithm.name,
            )
            return

        # 3. Idempotency.
        if self._is_recent_replay(store, algorithm, input_values, when):
            result.skipped_idempotent += 1
            logger.info(
                "algorithms.runtime.skip_idempotent",
                algorithm_id=algorithm.id,
                algorithm_name=algorithm.name,
                window_s=self._idempotency_window,
            )
            return

        # 4. Walk the reasoning chain.
        invocation = await self._execute_fire(
            algorithm=algorithm,
            observations=observations,
            store=store,
            when=when,
            forced=False,
            token_budget=self._max_tokens_per_fire,
        )
        if invocation is None:
            result.skipped_token_cap += 1
            return
        result.fired += 1
        result.invocation_ids.append(invocation.id)

    async def _execute_fire(
        self,
        *,
        algorithm: LogicalAlgorithm,
        observations: dict[str, InputObservation],
        store: _RuntimeStore,
        when: datetime,
        forced: bool,
        token_budget: int,
    ) -> Optional[AlgorithmInvocation]:
        """Walk the reasoning chain to a persisted invocation.

        Returns None when the per-fire token cap is exceeded before the
        chain finishes — the runtime abstains rather than truncates.
        """

        input_values = {name: obs.value for name, obs in observations.items()}
        trace: list[str] = []
        derived_facts: list[str] = []
        tokens_used = 0
        budget = max(0, int(token_budget))

        def _budget_left() -> int:
            return budget - tokens_used

        for step in algorithm.reasoning_chain:
            step_kind = getattr(step.step_kind, "value", str(step.step_kind))
            if step_kind == ReasoningStepKind.DETECT.value:
                trace.append(
                    f"DETECT: {step.derived_fact or step.predicate or 'observation recorded'}"
                )
                continue
            if step_kind == ReasoningStepKind.APPLY_PRINCIPLE.value:
                if budget and _budget_left() < 200:
                    logger.warning(
                        "algorithms.runtime.abstain_token_cap",
                        algorithm_id=algorithm.id,
                        step_kind=step_kind,
                    )
                    return None
                derived = await self._invoke_principle_step(
                    algorithm=algorithm,
                    step=step,
                    input_values=input_values,
                    derived_facts=derived_facts,
                )
                if derived is None:
                    logger.warning(
                        "algorithms.runtime.principle_step_abstained",
                        algorithm_id=algorithm.id,
                        principle_id=step.principle_id,
                    )
                    return None
                tokens_used += derived.tokens_used
                trace.append(
                    f"APPLY_PRINCIPLE({step.principle_id}): {derived.text}"
                )
                derived_facts.append(derived.text)
                continue
            if step_kind == ReasoningStepKind.SYNTHESIZE.value:
                if budget and _budget_left() < 200:
                    return None
                synth = step.derived_fact or "Combine derived facts."
                trace.append(f"SYNTHESIZE: {synth}")
                derived_facts.append(synth)
                continue
            if step_kind == ReasoningStepKind.OUTPUT.value:
                if budget and _budget_left() < 200:
                    return None
                rendered = await self._invoke_output_step(
                    algorithm=algorithm,
                    input_values=input_values,
                    derived_facts=derived_facts,
                )
                if rendered is None:
                    return None
                tokens_used += rendered.tokens_used
                trace.append(
                    f"OUTPUT: {algorithm.output.name} = "
                    f"{json.dumps(rendered.payload, sort_keys=True, default=str)}"
                )
                invocation = self._persist_invocation(
                    algorithm=algorithm,
                    observations=observations,
                    trigger_inputs=input_values,
                    output_payload=rendered.payload,
                    confidence_low=rendered.confidence_low,
                    confidence_high=rendered.confidence_high,
                    horizon_seconds=rendered.predicted_horizon,
                    trace=trace,
                    when=when,
                    store=store,
                    forced=forced,
                )
                logger.info(
                    "algorithms.runtime.invocation_fired",
                    algorithm_id=algorithm.id,
                    algorithm_name=algorithm.name,
                    invocation_id=invocation.id,
                    trigger_inputs=_sanitize_inputs(input_values),
                    output_headline=_summarise_payload(rendered.payload),
                )
                return invocation

        # Reasoning chain ended without an OUTPUT step. The validator
        # rejects this at promotion time so this branch should not be
        # reachable — emit a warning and abstain.
        logger.warning(
            "algorithms.runtime.chain_without_output",
            algorithm_id=algorithm.id,
        )
        return None

    # ── LLM-backed step helpers ────────────────────────────────

    async def _invoke_principle_step(
        self,
        *,
        algorithm: LogicalAlgorithm,
        step: Any,
        input_values: Mapping[str, Any],
        derived_facts: Sequence[str],
    ) -> Optional["_PrincipleStepResult"]:
        system = (
            "You are the runtime executor for a LogicalAlgorithm. You are "
            "applying ONE named principle to ONE observation set. Reply with "
            "a single sentence — the derived fact — grounded in the inputs. "
            "If the principle does not apply to the inputs, reply with the "
            "single word ABSTAIN."
        )
        user = json.dumps(
            {
                "algorithm": algorithm.name,
                "principle_id": step.principle_id,
                "principle_hint": step.derived_fact or "",
                "inputs": _sanitize_inputs(input_values),
                "facts_so_far": list(derived_facts),
            },
            sort_keys=True,
            default=str,
        )
        try:
            raw = self._llm.complete(
                system=system,
                user=user,
                max_tokens=self._llm_max_tokens,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(
                "algorithms.runtime.llm_principle_error",
                algorithm_id=algorithm.id,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None
        text = (raw or "").strip()
        if not text or text.upper().startswith("ABSTAIN"):
            return None
        tokens = _estimate_tokens(system) + _estimate_tokens(user) + _estimate_tokens(text)
        return _PrincipleStepResult(text=text, tokens_used=tokens)

    async def _invoke_output_step(
        self,
        *,
        algorithm: LogicalAlgorithm,
        input_values: Mapping[str, Any],
        derived_facts: Sequence[str],
    ) -> Optional["_OutputStepResult"]:
        system = (
            "You are the synthesizer for a LogicalAlgorithm. Combine the "
            "derived facts into the algorithm's declared output. Return a "
            "single JSON object with these keys:\n"
            "  output: object|number|boolean — matches the declared type\n"
            "  confidence_low: float in [0, 1]\n"
            "  confidence_high: float in [0, 1]\n"
            "  predicted_horizon_seconds: float (≥ 0; horizon you stand by)\n"
            "Do not include narration. Return JSON only."
        )
        user = json.dumps(
            {
                "algorithm": algorithm.name,
                "output_schema": {
                    "name": algorithm.output.name,
                    "type": getattr(
                        algorithm.output.type, "value", str(algorithm.output.type)
                    ),
                    "units": algorithm.output.units,
                    "range": algorithm.output.range,
                    "fields": algorithm.output.fields,
                },
                "inputs": _sanitize_inputs(input_values),
                "derived_facts": list(derived_facts),
            },
            sort_keys=True,
            default=str,
        )
        try:
            raw = self._llm.complete(
                system=system,
                user=user,
                max_tokens=self._llm_max_tokens,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(
                "algorithms.runtime.llm_output_error",
                algorithm_id=algorithm.id,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None
        try:
            payload = _extract_json_object(raw)
        except ValueError as exc:
            logger.warning(
                "algorithms.runtime.output_parse_failed",
                algorithm_id=algorithm.id,
                error=str(exc),
            )
            return None
        output = payload.get("output")
        if output is None:
            return None
        output_dict: dict[str, Any]
        if isinstance(output, dict):
            output_dict = output
        else:
            output_dict = {algorithm.output.name: output}
        confidence_low = _coerce_unit(payload.get("confidence_low"), default=0.0)
        confidence_high = _coerce_unit(payload.get("confidence_high"), default=1.0)
        if confidence_high < confidence_low:
            confidence_low, confidence_high = confidence_high, confidence_low
        horizon = _coerce_nonneg_float(
            payload.get("predicted_horizon_seconds"), default=0.0
        )
        tokens = _estimate_tokens(system) + _estimate_tokens(user) + _estimate_tokens(raw or "")
        return _OutputStepResult(
            payload=output_dict,
            confidence_low=confidence_low,
            confidence_high=confidence_high,
            predicted_horizon=horizon,
            tokens_used=tokens,
        )

    # ── Persistence + audit ────────────────────────────────────

    def _persist_invocation(
        self,
        *,
        algorithm: LogicalAlgorithm,
        observations: Mapping[str, InputObservation],
        trigger_inputs: dict[str, Any],
        output_payload: dict[str, Any],
        confidence_low: float,
        confidence_high: float,
        horizon_seconds: float,
        trace: list[str],
        when: datetime,
        store: _RuntimeStore,
        forced: bool,
    ) -> AlgorithmInvocation:
        derived_output = dict(output_payload)
        # Carry runtime metadata under a single key so consumers can
        # filter forced invocations out of the live track-record.
        derived_output["_meta"] = {
            "forced": forced,
            "input_hash": canonical_input_hash(trigger_inputs),
        }
        invocation = AlgorithmInvocation(
            algorithm_id=algorithm.id,
            organization_id=algorithm.organization_id,
            invoked_at=when,
            trigger_inputs=dict(trigger_inputs),
            derived_output=derived_output,
            reasoning_trace=list(trace),
            confidence_low=max(0.0, min(1.0, float(confidence_low))),
            confidence_high=max(0.0, min(1.0, float(confidence_high))),
            predicted_horizon=max(0.0, float(horizon_seconds)),
        )
        store.put_invocation(invocation)
        for name, obs in observations.items():
            try:
                store.put_input_observation(
                    AlgorithmInputObservation(
                        id=str(uuid.uuid4()),
                        invocation_id=invocation.id,
                        input_name=name,
                        value=obs.value,
                        observed_at=obs.observed_at,
                        source_artifact_id=obs.source_artifact_id,
                        source_url=obs.source_url,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "algorithms.runtime.observation_persist_failed",
                    invocation_id=invocation.id,
                    input_name=name,
                    error=f"{type(exc).__name__}: {exc}",
                )
        # Prompt 10 — when the algorithm opted into synthesizer triggers,
        # enqueue a synthesis task so the synthesizer tick will pick it up.
        if bool(getattr(algorithm, "triggers_synthesis", False)) and not forced:
            self._enqueue_synthesis_task(
                store=store,
                algorithm=algorithm,
                invocation=invocation,
            )
        return invocation

    def _enqueue_synthesis_task(
        self,
        *,
        store: _RuntimeStore,
        algorithm: LogicalAlgorithm,
        invocation: AlgorithmInvocation,
    ) -> None:
        enqueue = getattr(store, "put_synthesizer_task", None)
        if not callable(enqueue):
            return
        try:
            from noosphere.models import (
                SynthesizerTask,
                SynthesizerTaskTrigger,
            )

            task = SynthesizerTask(
                organization_id=algorithm.organization_id,
                trigger=SynthesizerTaskTrigger.ALGORITHM,
                question=(
                    f"Do we have a take on the {algorithm.name} firing? "
                    f"(invocation {invocation.id})"
                ),
                context_json={
                    "algorithm_id": algorithm.id,
                    "algorithm_name": algorithm.name,
                    "domain": ", ".join(
                        sorted(set(getattr(algorithm, "source_principle_ids", []) or []))
                    ),
                },
                invocation_id=invocation.id,
            )
            enqueue(task)
        except Exception as exc:  # pragma: no cover - best-effort hook
            logger.warning(
                "algorithms.runtime.synthesizer_enqueue_failed",
                algorithm_id=algorithm.id,
                invocation_id=invocation.id,
                error=f"{type(exc).__name__}: {exc}",
            )

    # ── Idempotency + sandbox bookkeeping ──────────────────────

    def _is_recent_replay(
        self,
        store: _RuntimeStore,
        algorithm: LogicalAlgorithm,
        trigger_inputs: Mapping[str, Any],
        now: datetime,
    ) -> bool:
        if self._idempotency_window <= 0:
            return False
        target_hash = canonical_input_hash(trigger_inputs)
        cutoff = now - timedelta(seconds=self._idempotency_window)
        try:
            history = store.list_invocations_for_algorithm(algorithm.id, limit=64)
        except Exception:
            return False
        for inv in history:
            invoked_at = _as_utc(inv.invoked_at)
            if invoked_at < cutoff:
                continue
            inv_hash = (
                inv.derived_output.get("_meta", {}).get("input_hash")
                if isinstance(inv.derived_output, dict)
                else None
            )
            if inv_hash == target_hash:
                return True
            # Fall back to recomputing the hash from trigger_inputs in
            # case an older row was written without the meta block.
            if canonical_input_hash(inv.trigger_inputs or {}) == target_hash:
                return True
        return False

    def _record_sandbox_refusal(
        self,
        store: _RuntimeStore,
        algorithm: LogicalAlgorithm,
        *,
        reason: str,
    ) -> None:
        count = self._sandbox_refusal_counts.get(algorithm.id, 0) + 1
        self._sandbox_refusal_counts[algorithm.id] = count
        logger.warning(
            "algorithms.runtime.sandbox_refused",
            algorithm_id=algorithm.id,
            algorithm_name=algorithm.name,
            count=count,
            reason=reason,
        )
        if count >= self._sandbox_refusal_threshold:
            try:
                store.set_algorithm_status(
                    algorithm.id,
                    AlgorithmStatus.PAUSED,
                )
                logger.warning(
                    "algorithms.runtime.auto_paused",
                    algorithm_id=algorithm.id,
                    refusals=count,
                    reason=reason,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "algorithms.runtime.auto_pause_failed",
                    algorithm_id=algorithm.id,
                    error=f"{type(exc).__name__}: {exc}",
                )
            self._sandbox_refusal_counts.pop(algorithm.id, None)

    # ── Resolution helper ──────────────────────────────────────

    async def _resolve_outcome(
        self,
        algorithm: LogicalAlgorithm,
        invocation: AlgorithmInvocation,
    ) -> Optional[OutcomeResolution]:
        if self._outcome_resolver is not None:
            return await self._outcome_resolver(algorithm, invocation, self._resolver)
        # Default: re-resolve every input and snapshot the current
        # values as the actual outcome. Correctness is INDETERMINATE
        # because the runtime cannot know without an outcome rule —
        # calibration layers (prompt 05) own that judgement.
        snapshot: dict[str, Any] = {}
        for inp in algorithm.inputs:
            obs = await self._resolver.resolve(inp)
            if obs is None:
                continue
            snapshot[inp.name] = obs.value
        if not snapshot:
            return None
        return OutcomeResolution(
            actual_outcome={"observed_inputs": snapshot},
            correctness=AlgorithmCorrectness.INDETERMINATE,
            brier_equivalent=None,
        )


# ── Small dataclasses for step results ──────────────────────────────


@dataclass
class _PrincipleStepResult:
    text: str
    tokens_used: int


@dataclass
class _OutputStepResult:
    payload: dict[str, Any]
    confidence_low: float
    confidence_high: float
    predicted_horizon: float
    tokens_used: int


# ── Utilities ───────────────────────────────────────────────────────


def _as_utc(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_unit(value: Any, *, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _coerce_nonneg_float(value: Any, *, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, v)


def _sanitize_inputs(input_values: Mapping[str, Any]) -> dict[str, Any]:
    """Trim payloads heading into the structured log to keep lines small."""
    out: dict[str, Any] = {}
    for k, v in input_values.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = repr(v)[:120]
    return out


def _summarise_payload(payload: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(payload, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(payload)[:160]
    return encoded[:160]


def _load_algorithm(
    store: Any, algorithm_id: str
) -> Optional[LogicalAlgorithm]:
    getter = getattr(store, "get_algorithm", None)
    if getter is None:
        return None
    try:
        return getter(algorithm_id)
    except Exception:
        return None


__all__ = [
    "AlgorithmRuntime",
    "OutcomeResolution",
    "OutcomeResolver",
    "ResolutionTickResult",
    "SandboxRefused",
    "TickResult",
    "canonical_input_hash",
]
