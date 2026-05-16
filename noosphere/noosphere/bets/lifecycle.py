"""BetSpec lifecycle ticker.

Wakes periodically (run from ``forecasts.scheduler`` as a sub-loop or
from the CLI for a one-shot sweep) and walks every OPEN BetSpec past
its ``horizon_at`` by more than the configured grace window. Each
bet is handed to its kind-specific resolver. When the resolver
returns a :class:`BetResolution`, the spec is transitioned to
RESOLVED and the resolution is persisted.

ADVISORY and STRATEGIC bets never auto-resolve — their resolver
helpers always return ``None``. The ticker still walks them so we can
fire the STRATEGIC ``commitment_review_at`` triage reminder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from noosphere.bets.resolvers import (
    ScientificFeedProbe,
    resolve_advisory,
    resolve_market,
    resolve_scientific,
    resolve_strategic,
)
from noosphere.bets.resolvers.strategic import commitment_review_due
from noosphere.bets.spec import (
    BetKind,
    BetResolution,
    BetSpec,
    BetStatus,
    ScientificDataSource,
)
from noosphere.observability import get_logger

log = get_logger(__name__)

# By default, the lifecycle ticker only considers bets whose horizon
# has passed by more than this grace window. The prompt spec is "> 24h"
# — set as a constant so tests can monkey-patch it.
DEFAULT_HORIZON_GRACE = timedelta(hours=24)


@dataclass
class LifecycleReport:
    """Aggregated result of one lifecycle pass."""

    attempted: int = 0
    resolved: int = 0
    deferred: int = 0
    review_reminders: int = 0
    errors: list[str] = field(default_factory=list)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def run_lifecycle_once(
    store: Any,
    *,
    organization_id: Optional[str] = None,
    now: Optional[datetime] = None,
    horizon_grace: timedelta | None = None,
    scientific_probes: dict[ScientificDataSource, ScientificFeedProbe] | None = None,
    calibration_recorder: Optional[Callable[[BetSpec, BetResolution], None]] = None,
) -> LifecycleReport:
    """One pass over every OPEN BetSpec; returns aggregate counts."""

    report = LifecycleReport()
    moment = _as_utc(now or _utcnow())
    grace = horizon_grace if horizon_grace is not None else DEFAULT_HORIZON_GRACE
    open_specs = store.list_bet_specs(
        organization_id=organization_id,
        status=BetStatus.OPEN.value,
        limit=500,
    )
    for spec in open_specs:
        report.attempted += 1
        try:
            kind = (
                BetKind(spec.kind) if isinstance(spec.kind, str) else spec.kind
            )
            # STRATEGIC bets surface a triage reminder regardless of horizon.
            if kind == BetKind.STRATEGIC_BET and commitment_review_due(
                spec, now=moment
            ):
                report.review_reminders += 1
                log.info(
                    "bet_strategic_commitment_review_due",
                    bet_spec_id=spec.id,
                    organization_id=spec.organization_id,
                    review_at=(
                        spec.strategic_bet.commitment_review_at.isoformat()
                        if spec.strategic_bet
                        and spec.strategic_bet.commitment_review_at
                        else None
                    ),
                )
            horizon_at = _as_utc(spec.horizon_at)
            if horizon_at + grace > moment:
                report.deferred += 1
                continue
            resolution = _dispatch_resolver(
                spec,
                store=store,
                scientific_probes=scientific_probes,
            )
            if resolution is None:
                report.deferred += 1
                continue
            _commit_resolution(
                spec,
                resolution,
                store=store,
                calibration_recorder=calibration_recorder,
            )
            report.resolved += 1
        except Exception as exc:  # pragma: no cover - defensive
            msg = f"{type(exc).__name__}: {exc}"
            report.errors.append(msg)
            log.warning(
                "bet_lifecycle_resolver_error",
                bet_spec_id=getattr(spec, "id", None),
                error=msg,
            )
    return report


def _dispatch_resolver(
    spec: BetSpec,
    *,
    store: Any,
    scientific_probes: dict[ScientificDataSource, ScientificFeedProbe] | None,
) -> Optional[BetResolution]:
    kind = BetKind(spec.kind) if isinstance(spec.kind, str) else spec.kind
    if kind == BetKind.MARKET_BET:
        return resolve_market(spec, store=store)
    if kind == BetKind.SCIENTIFIC_BET:
        return resolve_scientific(spec, store=store, probes=scientific_probes)
    if kind == BetKind.ADVISORY_BET:
        return resolve_advisory(spec, store=store)
    if kind == BetKind.STRATEGIC_BET:
        return resolve_strategic(spec, store=store)
    raise ValueError(f"unknown BetKind: {kind!r}")  # pragma: no cover


def _commit_resolution(
    spec: BetSpec,
    resolution: BetResolution,
    *,
    store: Any,
    calibration_recorder: Optional[Callable[[BetSpec, BetResolution], None]],
) -> None:
    outcome = resolution.outcome
    spec.status = BetStatus.RESOLVED
    spec.resolved_at = resolution.resolved_at
    spec.outcome = outcome
    spec.outcome_note = resolution.evidence_note
    store.put_bet_spec(spec)
    store.put_bet_resolution(resolution)
    if calibration_recorder is not None:
        try:
            calibration_recorder(spec, resolution)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "bet_lifecycle_calibration_recorder_error",
                bet_spec_id=spec.id,
                error=f"{type(exc).__name__}: {exc}",
            )
    log.info(
        "bet_spec_resolved",
        bet_spec_id=spec.id,
        kind=spec.kind if isinstance(spec.kind, str) else spec.kind.value,
        outcome=outcome if isinstance(outcome, str) else outcome.value,
        memo_id=spec.created_by_memo_id,
        originating_algorithm_id=spec.originating_algorithm_id,
    )


def operator_resolve_bet(
    store: Any,
    bet_spec_id: str,
    *,
    outcome: str,
    evidence_note: str = "",
    evidence_artifact_ids: list[str] | None = None,
    operator_id: str = "operator",
    pnl_usd: float | None = None,
    cost_realized: float | None = None,
    accuracy_score: float | None = None,
    audience_response: str | None = None,
) -> Optional[BetSpec]:
    """Operator-driven resolution. Used by ``noosphere bet resolve``.

    This is the *only* path that can resolve an ADVISORY or STRATEGIC
    bet. MARKET and SCIENTIFIC bets are also resolvable here for
    manual overrides.
    """

    from noosphere.bets.spec import BetOutcome  # local — small surface

    spec = store.get_bet_spec(bet_spec_id)
    if spec is None:
        return None
    parsed = BetOutcome(outcome.upper())
    resolution = BetResolution(
        bet_spec_id=spec.id,
        outcome=parsed,
        evidence_note=evidence_note,
        evidence_artifact_ids=list(evidence_artifact_ids or []),
        resolved_by=operator_id,
        pnl_usd=pnl_usd,
        cost_realized=cost_realized,
        accuracy_score=accuracy_score,
        audience_response=audience_response,
    )
    _commit_resolution(spec, resolution, store=store, calibration_recorder=None)
    return spec


def calibration_record_payload(spec: BetSpec, resolution: BetResolution) -> dict[str, Any]:
    """Shape the calibration tracker consumes when a bet resolves.

    A thin adapter so the algorithm calibration sub-loop can attribute
    a BetSpec resolution to (a) the originating algorithm (if any) and
    (b) the firm's overall calibration record. Kept as a pure
    dictionary so this module doesn't depend on the algorithms
    package.
    """

    return {
        "bet_spec_id": spec.id,
        "organization_id": spec.organization_id,
        "kind": spec.kind if isinstance(spec.kind, str) else spec.kind.value,
        "memo_id": spec.created_by_memo_id,
        "originating_algorithm_id": spec.originating_algorithm_id,
        "outcome": resolution.outcome if isinstance(resolution.outcome, str)
        else resolution.outcome.value,
        "pnl_usd": resolution.pnl_usd,
        "accuracy_score": resolution.accuracy_score,
        "resolved_at": resolution.resolved_at.isoformat(),
    }
