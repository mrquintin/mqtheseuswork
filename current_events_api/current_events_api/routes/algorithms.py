"""Public REST routes for the LogicalAlgorithm surface.

These endpoints back the founder-facing `/algorithms` page and its
drill pages. Operator-only fields (token counts, internal hashes,
forced/_meta annotations) are stripped here — the public surface
sees only what the firm is willing to publish.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from current_events_api.deps import enforce_read_rate_limit, get_store
from noosphere.algorithms.schemas import AlgorithmStatus
from noosphere.models import (
    AlgorithmInputObservation,
    AlgorithmInvocation,
    LogicalAlgorithm,
)
from noosphere.store import Store

router = APIRouter(prefix="/v1/algorithms", tags=["algorithms"])


def _org_filter() -> Optional[str]:
    return (
        os.environ.get("ALGORITHMS_ORG_ID")
        or os.environ.get("FORECASTS_ORG_ID")
        or None
    )


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _strip_meta(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if k == "_meta":
                continue
            out[k] = v
        return out
    return payload


def _public_algorithm(algo: LogicalAlgorithm) -> dict[str, Any]:
    return {
        "id": algo.id,
        "name": algo.name,
        "description": algo.description,
        "status": _enum_value(algo.status),
        "sourcePrincipleIds": list(algo.source_principle_ids),
        "inputs": [
            {
                "name": inp.name,
                "type": _enum_value(inp.type),
                "description": inp.description,
                "observabilitySource": inp.observability_source,
                "enumValues": list(inp.enum_values),
                "units": inp.units,
            }
            for inp in algo.inputs
        ],
        "output": {
            "name": algo.output.name,
            "type": _enum_value(algo.output.type),
            "description": algo.output.description,
            "units": algo.output.units,
            "range": algo.output.range,
            "fields": list(algo.output.fields),
        },
        "reasoningChain": [
            {
                "stepKind": _enum_value(step.step_kind),
                "principleId": step.principle_id,
                "predicate": step.predicate,
                "derivedFact": step.derived_fact,
            }
            for step in algo.reasoning_chain
        ],
        "triggerPredicate": algo.trigger_predicate,
        "retiredReason": algo.retired_reason,
        "createdAt": algo.created_at.isoformat() if algo.created_at else None,
        "updatedAt": algo.updated_at.isoformat() if algo.updated_at else None,
        "lastInvokedAt": (
            algo.last_invoked_at.isoformat() if algo.last_invoked_at else None
        ),
    }


def _public_invocation(inv: AlgorithmInvocation) -> dict[str, Any]:
    bet = None
    if inv.bet_implied is not None:
        bet = {
            "venue": inv.bet_implied.venue,
            "instrument": inv.bet_implied.instrument,
            "direction": inv.bet_implied.direction,
            "sizingHint": inv.bet_implied.sizing_hint,
            "rationale": inv.bet_implied.rationale,
        }
    return {
        "id": inv.id,
        "algorithmId": inv.algorithm_id,
        "invokedAt": inv.invoked_at.isoformat() if inv.invoked_at else None,
        "triggerInputs": dict(inv.trigger_inputs or {}),
        "derivedOutput": _strip_meta(inv.derived_output or {}),
        "reasoningTrace": list(inv.reasoning_trace or []),
        "confidenceLow": inv.confidence_low,
        "confidenceHigh": inv.confidence_high,
        "predictedHorizon": inv.predicted_horizon,
        "betImplied": bet,
        "resolvedAt": inv.resolved_at.isoformat() if inv.resolved_at else None,
        "actualOutcome": inv.actual_outcome,
        "correctness": _enum_value(inv.correctness) if inv.correctness else None,
        "brierEquivalent": inv.brier_equivalent,
    }


def _public_observation(obs: AlgorithmInputObservation) -> dict[str, Any]:
    return {
        "id": obs.id,
        "invocationId": obs.invocation_id,
        "inputName": obs.input_name,
        "value": obs.value,
        "observedAt": obs.observed_at.isoformat() if obs.observed_at else None,
        "sourceArtifactId": obs.source_artifact_id,
        "sourceUrl": obs.source_url,
    }


def _hit_rate(invocations: list[AlgorithmInvocation]) -> dict[str, Any]:
    """Correctness ratio across resolved invocations.

    Only CORRECT counts as a hit; PARTIALLY_CORRECT contributes 0.5.
    INDETERMINATE / unresolved invocations are excluded from the
    denominator — the founder's guidance is not to penalise the
    algorithm for outcomes we have not graded.
    """

    resolved = [
        inv
        for inv in invocations
        if inv.correctness is not None
        and _enum_value(inv.correctness) != "INDETERMINATE"
    ]
    n = len(resolved)
    if n == 0:
        return {"ratio": None, "n": 0}
    score = 0.0
    for inv in resolved:
        c = _enum_value(inv.correctness)
        if c == "CORRECT":
            score += 1.0
        elif c == "PARTIALLY_CORRECT":
            score += 0.5
    return {"ratio": round(score / n, 4), "n": n}


@router.get("", dependencies=[Depends(enforce_read_rate_limit)])
def list_algorithms(
    store: Annotated[Store, Depends(get_store)],
    status_filter: Annotated[
        Optional[str], Query(alias="status", description="ACTIVE | PAUSED | RETIRED")
    ] = None,
) -> dict[str, Any]:
    """List algorithms (default ACTIVE) with hit-rate + last-fired metadata."""

    org = _org_filter()
    if org is None:
        # Public surface needs a tenant scope; fall back to first org.
        algorithms: list[LogicalAlgorithm] = []
    else:
        if status_filter:
            try:
                normalised = AlgorithmStatus(status_filter.upper())
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"unknown status: {status_filter}",
                ) from exc
            algorithms = store.list_algorithms_for_org(
                organization_id=org, status=normalised
            )
        else:
            algorithms = store.list_active_algorithms(organization_id=org)

    rows: list[dict[str, Any]] = []
    for algo in algorithms:
        try:
            invocations = store.list_invocations_for_algorithm(algo.id, limit=200)
        except Exception:
            invocations = []
        last_inv = invocations[0] if invocations else None
        row = _public_algorithm(algo)
        row["hitRate"] = _hit_rate(invocations)
        row["latestInvocationId"] = last_inv.id if last_inv else None
        row["latestInvocationAt"] = (
            last_inv.invoked_at.isoformat() if last_inv and last_inv.invoked_at else None
        )
        rows.append(row)
    return {"algorithms": rows}


@router.get("/{algorithm_id}", dependencies=[Depends(enforce_read_rate_limit)])
def get_algorithm(
    algorithm_id: str,
    store: Annotated[Store, Depends(get_store)],
    invocations_limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> dict[str, Any]:
    algo = store.get_algorithm(algorithm_id)
    if algo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "algorithm_not_found")
    try:
        invocations = store.list_invocations_for_algorithm(
            algo.id, limit=invocations_limit
        )
    except Exception:
        invocations = []
    full_history = invocations
    try:
        full_history = store.list_invocations_for_algorithm(algo.id, limit=500)
    except Exception:
        pass

    body = _public_algorithm(algo)
    body["hitRate"] = _hit_rate(full_history)
    body["invocations"] = [_public_invocation(inv) for inv in invocations]
    body["calibration"] = _calibration_series(full_history)
    body["betLog"] = [
        {
            "invocationId": inv.id,
            "invokedAt": inv.invoked_at.isoformat() if inv.invoked_at else None,
            "bet": _public_invocation(inv).get("betImplied"),
            "correctness": (
                _enum_value(inv.correctness) if inv.correctness else None
            ),
            "brierEquivalent": inv.brier_equivalent,
        }
        for inv in full_history
        if inv.bet_implied is not None
    ]
    return body


@router.get(
    "/{algorithm_id}/invocations/{invocation_id}",
    dependencies=[Depends(enforce_read_rate_limit)],
)
def get_invocation(
    algorithm_id: str,
    invocation_id: str,
    store: Annotated[Store, Depends(get_store)],
) -> dict[str, Any]:
    inv = store.get_invocation(invocation_id)
    if inv is None or inv.algorithm_id != algorithm_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invocation_not_found")
    algo = store.get_algorithm(algorithm_id)
    if algo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "algorithm_not_found")
    try:
        observations = store.list_observations_for_invocation(invocation_id)
    except Exception:
        observations = []
    return {
        "algorithm": _public_algorithm(algo),
        "invocation": _public_invocation(inv),
        "observations": [_public_observation(obs) for obs in observations],
    }


def _calibration_series(invocations: list[AlgorithmInvocation]) -> list[dict[str, Any]]:
    """Cumulative correctness ratio per resolved invocation index.

    Returned oldest-first so the spark chart on the detail page can
    render left-to-right without reversing on the client.
    """

    ordered = sorted(
        [
            inv
            for inv in invocations
            if inv.correctness is not None
            and _enum_value(inv.correctness) != "INDETERMINATE"
        ],
        key=lambda inv: inv.invoked_at,
    )
    out: list[dict[str, Any]] = []
    score = 0.0
    for idx, inv in enumerate(ordered, start=1):
        c = _enum_value(inv.correctness)
        if c == "CORRECT":
            score += 1.0
        elif c == "PARTIALLY_CORRECT":
            score += 0.5
        ratio = score / idx
        out.append(
            {
                "index": idx,
                "invocationId": inv.id,
                "ratio": round(ratio, 4),
                "correctness": c,
                "brierEquivalent": inv.brier_equivalent,
            }
        )
    return out
