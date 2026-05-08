"""Drift-alert policy with hysteresis.

The drift estimator emits a severity per (method, window) on every
nightly tick. Naively translating that into an alert state — the method
is "drifting" iff the most recent assessment was "warn" or "escalate" —
would flip the public banner on and off every time a thin window
straddles the threshold. The user-visible state must be sticky.

This module owns the state machine. Inputs are the chronologically
ordered DriftEventRecords for one (method, version, domain). Output is
a stable `AlertState` plus a small ledger of transitions. The rule is:

* Enter `WARN` on first severity ≥ "warn".
* Escalate to `ESCALATE` on severity ≥ "escalate".
* Do NOT clear the alert until `HYSTERESIS_CLEAN_WINDOWS` consecutive
  windows of severity "ok" are observed.

There is no "auto-downgrade from ESCALATE to WARN" path: once a method
escalates, it stays escalated until a human or two clean windows in a
row clear it. Otherwise an oscillating method would land in WARN, look
calmer, and not get attention it warranted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional, Sequence

from noosphere.evaluation.method_drift import (
    ESCALATE_SIGMA,
    HYSTERESIS_CLEAN_WINDOWS,
    WARN_SIGMA,
    DriftEventRecord,
)


class AlertState(str, Enum):
    OK = "ok"
    WARN = "warn"
    ESCALATE = "escalate"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class AlertTransition:
    at: datetime
    from_state: AlertState
    to_state: AlertState
    triggering_event_id: str
    reason: str


@dataclass
class AlertResult:
    state: AlertState
    last_active_at: Optional[datetime]
    last_event_id: Optional[str]
    consecutive_clean: int
    transitions: list[AlertTransition]

    @property
    def is_active(self) -> bool:
        return self.state in (AlertState.WARN, AlertState.ESCALATE)


def reduce_events(
    events: Sequence[DriftEventRecord],
    *,
    clean_window_threshold: int = HYSTERESIS_CLEAN_WINDOWS,
) -> AlertResult:
    """Replay events in chronological order to derive the current alert
    state. Events are expected to share (organization, method, version,
    domain, window_days) — mixing different windows in one call is the
    caller's problem.

    Insufficient-data events neither escalate nor clear: they preserve
    the current state and reset the clean-window counter to 0, because
    a window we couldn't measure is not a clean window.
    """
    state = AlertState.OK
    last_active_at: Optional[datetime] = None
    last_event_id: Optional[str] = None
    consecutive_clean = 0
    transitions: list[AlertTransition] = []

    ordered = sorted(events, key=lambda e: e.observed_at)
    for ev in ordered:
        sev = ev.severity
        prior_state = state
        if sev == "insufficient":
            consecutive_clean = 0
            # State unchanged; surface the gap on the operator panel.
            continue
        if sev == "escalate":
            state = AlertState.ESCALATE
            consecutive_clean = 0
            last_active_at = ev.observed_at
            last_event_id = ev.id
            if prior_state != state:
                transitions.append(
                    AlertTransition(
                        at=ev.observed_at,
                        from_state=prior_state,
                        to_state=state,
                        triggering_event_id=ev.id,
                        reason=(
                            f"σ={ev.sigma:.2f} ≥ {ESCALATE_SIGMA} and p={ev.p_value:.3f}"
                            if ev.sigma is not None and ev.p_value is not None
                            else "escalate"
                        ),
                    )
                )
            continue
        if sev == "warn":
            consecutive_clean = 0
            last_active_at = ev.observed_at
            last_event_id = ev.id
            # Do not downgrade from ESCALATE to WARN automatically.
            if prior_state == AlertState.OK:
                state = AlertState.WARN
                transitions.append(
                    AlertTransition(
                        at=ev.observed_at,
                        from_state=prior_state,
                        to_state=state,
                        triggering_event_id=ev.id,
                        reason=(
                            f"σ={ev.sigma:.2f} ≥ {WARN_SIGMA} and p={ev.p_value:.3f}"
                            if ev.sigma is not None and ev.p_value is not None
                            else "warn"
                        ),
                    )
                )
            continue
        # severity == "ok"
        if state == AlertState.OK:
            consecutive_clean = 0  # already clean, no countdown to track
            continue
        consecutive_clean += 1
        if consecutive_clean >= clean_window_threshold:
            transitions.append(
                AlertTransition(
                    at=ev.observed_at,
                    from_state=state,
                    to_state=AlertState.OK,
                    triggering_event_id=ev.id,
                    reason=f"{consecutive_clean} consecutive clean windows",
                )
            )
            state = AlertState.OK
            consecutive_clean = 0

    return AlertResult(
        state=state,
        last_active_at=last_active_at,
        last_event_id=last_event_id,
        consecutive_clean=consecutive_clean,
        transitions=transitions,
    )


def severity_penalty_multiplier(state: AlertState) -> float:
    """MQS-coupling: how much to scale the Severity sub-score when a
    method has an active drift alert. Documented verbatim in
    docs/methods/MQS_Specification.md (§ Drift coupling).

    A method that is drifting cannot project the same Severity
    confidence onto a new conclusion that it could when its calibration
    was stable. The penalty is multiplicative on the *Severity sub-score
    only* — drift does not blanket-discount the whole composite, since
    Domain Sensitivity and Compressibility are not affected by recent
    calibration.

    Penalty schedule:
    * OK / INSUFFICIENT → 1.00 (no penalty)
    * WARN              → 0.85
    * ESCALATE          → 0.65
    """
    if state == AlertState.WARN:
        return 0.85
    if state == AlertState.ESCALATE:
        return 0.65
    return 1.00


__all__ = [
    "AlertResult",
    "AlertState",
    "AlertTransition",
    "reduce_events",
    "severity_penalty_multiplier",
]
