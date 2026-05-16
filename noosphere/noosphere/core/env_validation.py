"""Environment variable validation for Theseus services.

This module is the single source of truth for which env vars exist,
which modes they are required in, what range / enum values they
accept, and what their defaults are. The boot-time check on the API
and scheduler, the ``noosphere env`` CLI, the operator docs, and the
credential validator all consume this registry rather than each
sprinkling their own ``os.getenv`` calls.

Constraints worth knowing:

* Secrets are never returned, logged, or printed. A SECRET row that
  is present is rendered as ``"***"``; a missing one is rendered as
  ``None``.
* MODE is one source of truth. ``THESEUS_MODE`` controls which rows
  are "required"; everything else flows from the validation report.
* Adding a new ``os.getenv`` somewhere in the codebase REQUIRES a
  matching row in :data:`REGISTRY`. ``tests/static/test_no_unregistered_getenv.py``
  scans for drift.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence


__all__ = [
    "Mode",
    "VarType",
    "Status",
    "EnvRequirement",
    "VarReport",
    "ValidationReport",
    "REGISTRY",
    "registry_lookup",
    "validate_env",
    "required_vars_for_mode",
    "parse_mode",
]


class Mode(str, Enum):
    """Operating modes. ``THESEUS_MODE`` selects one of these."""

    ALGORITHMS_ONLY = "algorithms-only"
    SYNTHESIZER = "synthesizer"
    FULL = "full"
    LIVE_TRADING = "live-trading"


# Mode inclusion lattice. A var required in ALGORITHMS_ONLY is also
# required in every richer mode; SYNTHESIZER adds vars on top of that,
# etc. This is the canonical reading of "required for this mode".
_MODE_INCLUDES: dict[Mode, tuple[Mode, ...]] = {
    Mode.ALGORITHMS_ONLY: (Mode.ALGORITHMS_ONLY,),
    Mode.SYNTHESIZER: (Mode.ALGORITHMS_ONLY, Mode.SYNTHESIZER),
    Mode.FULL: (Mode.ALGORITHMS_ONLY, Mode.SYNTHESIZER, Mode.FULL),
    Mode.LIVE_TRADING: (
        Mode.ALGORITHMS_ONLY,
        Mode.SYNTHESIZER,
        Mode.FULL,
        Mode.LIVE_TRADING,
    ),
}


class VarType(str, Enum):
    NUMBER = "NUMBER"
    STRING = "STRING"
    ENUM = "ENUM"
    DURATION = "DURATION"
    SECRET = "SECRET"
    BOOLEAN = "BOOLEAN"


class Status(str, Enum):
    PASS = "PASS"
    MISSING = "MISSING"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INVALID_ENUM = "INVALID_ENUM"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    OPTIONAL_MISSING = "OPTIONAL_MISSING"


@dataclass(frozen=True)
class EnvRequirement:
    """One row in the canonical env-var registry."""

    var_name: str
    required_in_modes: tuple[Mode, ...]
    type: VarType
    enum_values: tuple[str, ...] | None = None
    range: tuple[float, float] | None = None
    default: str | None = None
    notes: str = ""
    prompt_of_origin: str = ""

    def is_required(self, mode: Mode) -> bool:
        # A var "required in mode X" is required in every mode that
        # includes X. ALGORITHMS_ONLY-required vars are required
        # everywhere; LIVE_TRADING-required vars only in LIVE_TRADING.
        included = set(_MODE_INCLUDES[mode])
        return any(m in included for m in self.required_in_modes)


@dataclass(frozen=True)
class VarReport:
    var_name: str
    status: Status
    required: bool
    type: VarType
    message: str
    masked_value: str | None  # never the raw secret


@dataclass(frozen=True)
class ValidationReport:
    mode: Mode
    rows: tuple[VarReport, ...]

    def ok(self) -> bool:
        return not self.failures()

    def failures(self) -> tuple[VarReport, ...]:
        return tuple(r for r in self.rows if r.required and r.status != Status.PASS)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "ok": self.ok(),
            "rows": [
                {
                    "var": r.var_name,
                    "status": r.status.value,
                    "required": r.required,
                    "type": r.type.value,
                    "message": r.message,
                    "value": r.masked_value,
                }
                for r in self.rows
            ],
        }


# ─── Registry ─────────────────────────────────────────────────────────


def _row(
    var: str,
    modes: Iterable[Mode],
    typ: VarType,
    *,
    enum: Sequence[str] | None = None,
    rng: tuple[float, float] | None = None,
    default: str | None = None,
    notes: str = "",
    prompt: str = "",
) -> EnvRequirement:
    return EnvRequirement(
        var_name=var,
        required_in_modes=tuple(modes),
        type=typ,
        enum_values=tuple(enum) if enum is not None else None,
        range=rng,
        default=default,
        notes=notes,
        prompt_of_origin=prompt,
    )


# Mode constants for shorthand.
_A = Mode.ALGORITHMS_ONLY
_S = Mode.SYNTHESIZER
_F = Mode.FULL
_L = Mode.LIVE_TRADING


REGISTRY: tuple[EnvRequirement, ...] = (
    # ── Algorithms-only baseline ──────────────────────────────────
    _row(
        "DATABASE_URL", (_A,), VarType.SECRET,
        notes="Production Postgres URL (or sqlite:/// for local).",
        prompt="round11/01",
    ),
    _row(
        "ANTHROPIC_API_KEY", (_A,), VarType.SECRET,
        notes="Anthropic API key used by Haiku 4.5 generation calls.",
        prompt="round11/01",
    ),
    _row(
        "FORECASTS_INGEST_ORG_ID", (_A,), VarType.STRING,
        notes="Organization id Forecasts writes rows under.",
        prompt="round11/01",
    ),
    _row(
        "FORECASTS_OPERATOR_SECRET", (_A,), VarType.SECRET,
        notes="32-byte hex secret used to HMAC operator routes.",
        prompt="round11/01",
    ),
    _row(
        "ALGORITHMS_BUDGET_HOURLY_PROMPT_TOKENS", (_A,), VarType.NUMBER,
        rng=(1, 1e9),
        notes="Hourly prompt-token budget for the algorithm runtime.",
        prompt="round19/03",
    ),
    _row(
        "ALGORITHMS_BUDGET_HOURLY_COMPLETION_TOKENS", (_A,), VarType.NUMBER,
        rng=(1, 1e9),
        notes="Hourly completion-token budget for the algorithm runtime.",
        prompt="round19/03",
    ),
    _row(
        "ALGORITHMS_TICK_INTERVAL_S", (_A,), VarType.DURATION,
        rng=(1, 86400), default="60",
        notes="Seconds between algorithm runtime ticks.",
        prompt="round19/03",
    ),
    _row(
        "ALGORITHMS_MAX_TOKENS_PER_FIRE", (_A,), VarType.NUMBER,
        rng=(1, 1_000_000),
        notes="Per-fire token ceiling for a single algorithm invocation.",
        prompt="round19/03",
    ),

    # ── Synthesizer adds these ────────────────────────────────────
    _row(
        "SYNTHESIZER_BUDGET_HOURLY_PROMPT_TOKENS", (_S,), VarType.NUMBER,
        rng=(1, 1e9),
        notes="Hourly prompt-token budget for the synthesizer engine.",
        prompt="round19/10",
    ),
    _row(
        "SYNTHESIZER_BUDGET_HOURLY_COMPLETION_TOKENS", (_S,), VarType.NUMBER,
        rng=(1, 1e9),
        notes="Hourly completion-token budget for the synthesizer engine.",
        prompt="round19/10",
    ),

    # ── Full mode adds these ──────────────────────────────────────
    _row(
        "CLUSTER_JOIN_THRESHOLD", (_F,), VarType.NUMBER,
        rng=(0.0, 1.0), default="0.75",
        notes="Embedding cosine threshold for cluster join (0..1).",
        prompt="round19/07",
    ),
    _row(
        "MIN_CLUSTER_SIZE", (_F,), VarType.NUMBER,
        rng=(2, 10_000), default="3",
        notes="Minimum members for a stable cluster to surface.",
        prompt="round19/07",
    ),
    _row(
        "CROSS_CLUSTER_SAMPLE_FRACTION", (_F,), VarType.NUMBER,
        rng=(0.0, 1.0), default="0.05",
        notes="Fraction of cross-cluster pairs sampled per sweep.",
        prompt="round19/07",
    ),
    _row(
        "CROSS_CLUSTER_RANDOM_FRACTION", (_F,), VarType.NUMBER,
        rng=(0.0, 1.0), default="0.01",
        notes="Fraction of fully-random cross-cluster pairs sampled.",
        prompt="round19/07",
    ),
    _row(
        "CLUSTER_DRIFT_THRESHOLD", (_F,), VarType.NUMBER,
        rng=(0.0, 1.0), default="0.15",
        notes="Drift threshold before a cluster centroid is re-fit.",
        prompt="round19/07",
    ),
    _row(
        "CONTRADICTION_THRESHOLD", (_F,), VarType.NUMBER,
        rng=(0.0, 1.0), default="0.7",
        notes="NLI contradiction probability to count as contradiction.",
        prompt="round19/06",
    ),
    _row(
        "DIALECTIC_LIVE_CONTRADICTION_THRESHOLD", (_F,), VarType.NUMBER,
        rng=(0.0, 1.0), default="0.6",
        notes="Threshold for surfacing contradictions in live dialectic.",
        prompt="round19/14",
    ),
    _row(
        "DIALECTIC_LIVE_LATENCY_TARGET_S", (_F,), VarType.DURATION,
        rng=(0.1, 300), default="3.0",
        notes="Target end-to-end latency for live dialectic recording.",
        prompt="round19/14",
    ),
    _row(
        "DIALECTIC_AUDIO_RETENTION_DAYS", (_F,), VarType.NUMBER,
        rng=(0, 3650), default="30",
        notes="Days to retain raw dialectic audio before purge.",
        prompt="round19/14",
    ),
    _row(
        "GRAPH_REASONER_MAX_TOKENS_PER_EDGE", (_F,), VarType.NUMBER,
        rng=(1, 1_000_000), default="2000",
        notes="Token ceiling per graph-reasoner edge inference.",
        prompt="round19/13",
    ),
    _row(
        "MEMO_DISPATCH_DEFAULT_MODE", (_F,), VarType.ENUM,
        enum=("HUMAN", "AUTO_PAPER", "AUTO_LIVE"),
        default="HUMAN",
        notes="Default dispatch mode for new memos.",
        prompt="round19/11",
    ),

    # ── Live trading adds these (Round 10 + Round 18 block) ───────
    _row(
        "FORECASTS_LIVE_TRADING_ENABLED", (_L,), VarType.BOOLEAN,
        enum=("true", "false"), default="false",
        notes="Master switch for live prediction-market trading.",
        prompt="round10",
    ),
    _row(
        "FORECASTS_MAX_STAKE_USD", (_L,), VarType.NUMBER,
        rng=(0, 1e9), default="5",
        notes="Per-bet stake ceiling in USD.",
        prompt="round10",
    ),
    _row(
        "FORECASTS_MAX_DAILY_LOSS_USD", (_L,), VarType.NUMBER,
        rng=(0, 1e9), default="20",
        notes="Daily loss ceiling in USD. Kill switch auto-engages here.",
        prompt="round10",
    ),
    _row(
        "FORECASTS_KILL_SWITCH_AUTO_THRESHOLD_USD", (_L,), VarType.NUMBER,
        rng=(0, 1e9), default="15",
        notes="Auto kill-switch threshold (< daily loss ceiling).",
        prompt="round10",
    ),
    _row(
        "POLYMARKET_PRIVATE_KEY", (_L,), VarType.SECRET,
        notes="Polymarket dedicated wallet private key.",
        prompt="round10",
    ),
    _row(
        "KALSHI_API_KEY_ID", (_L,), VarType.STRING,
        notes="Kalshi live API key id.",
        prompt="round10",
    ),
    _row(
        "KALSHI_API_PRIVATE_KEY", (_L,), VarType.SECRET,
        notes="Kalshi live API RSA private key (PEM).",
        prompt="round10",
    ),
    _row(
        "AUTO_PAPER_REQUIRES_CALIBRATION_THRESHOLD", (_L,), VarType.NUMBER,
        rng=(0.0, 1.0), default="0.2",
        notes="Mean-Brier threshold below which an algorithm may auto-paper.",
        prompt="round18",
    ),
)


# ─── Public API ───────────────────────────────────────────────────────


def registry_lookup(var: str) -> EnvRequirement | None:
    for row in REGISTRY:
        if row.var_name == var:
            return row
    return None


def required_vars_for_mode(mode: Mode) -> tuple[str, ...]:
    return tuple(r.var_name for r in REGISTRY if r.is_required(mode))


def parse_mode(raw: str | None) -> Mode:
    raw = (raw or "").strip().lower()
    if not raw:
        return Mode.ALGORITHMS_ONLY
    for m in Mode:
        if m.value == raw:
            return m
    valid = ", ".join(m.value for m in Mode)
    raise ValueError(f"Unknown THESEUS_MODE={raw!r}. Valid: {valid}")


def _mask(req: EnvRequirement, raw: str | None) -> str | None:
    if raw is None:
        return None
    if req.type == VarType.SECRET:
        return "***"
    # Defensive truncation for very long string values; keeps stdout sane.
    if len(raw) > 80:
        return raw[:77] + "..."
    return raw


def _validate_row(
    req: EnvRequirement,
    env: Mapping[str, str],
    mode: Mode,
) -> VarReport:
    raw = env.get(req.var_name)
    required = req.is_required(mode)
    masked = _mask(req, raw)

    if raw is None or raw == "":
        # Use the documented default if any.
        if req.default is not None and req.default != "":
            raw_effective = req.default
            masked = _mask(req, raw_effective) if required else None
            status, message = _check_type_range_enum(req, raw_effective)
            if status == Status.PASS:
                return VarReport(
                    req.var_name, Status.PASS, required, req.type,
                    f"defaulted to {req.default!r}",
                    masked,
                )
            # default itself fails — should never happen but be explicit.
            return VarReport(
                req.var_name, status, required, req.type, message, masked,
            )
        if required:
            return VarReport(
                req.var_name, Status.MISSING, True, req.type,
                f"required in mode {mode.value!r} but not set",
                None,
            )
        return VarReport(
            req.var_name, Status.OPTIONAL_MISSING, False, req.type,
            "optional and not set",
            None,
        )

    status, message = _check_type_range_enum(req, raw)
    return VarReport(req.var_name, status, required, req.type, message, masked)


def _check_type_range_enum(req: EnvRequirement, raw: str) -> tuple[Status, str]:
    if req.type in (VarType.NUMBER, VarType.DURATION):
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return Status.TYPE_MISMATCH, f"value {raw!r} is not numeric"
        if math.isnan(val) or math.isinf(val):
            return Status.OUT_OF_RANGE, f"value {raw!r} is NaN/inf"
        if req.range is not None:
            lo, hi = req.range
            if val < lo or val > hi:
                return Status.OUT_OF_RANGE, (
                    f"value {raw!r} out of range [{lo}, {hi}]"
                )
        return Status.PASS, "ok"
    if req.type == VarType.ENUM:
        allowed = req.enum_values or ()
        if raw not in allowed:
            return Status.INVALID_ENUM, (
                f"value {raw!r} not in {{{', '.join(allowed)}}}"
            )
        return Status.PASS, "ok"
    if req.type == VarType.BOOLEAN:
        allowed = req.enum_values or ("true", "false")
        if raw.lower() not in allowed:
            return Status.INVALID_ENUM, (
                f"value {raw!r} not boolean ({', '.join(allowed)})"
            )
        return Status.PASS, "ok"
    # STRING and SECRET: presence is enough — no value-level checks here.
    return Status.PASS, "ok"


def validate_env(
    mode: Mode,
    env: Mapping[str, str] | None = None,
) -> ValidationReport:
    """Validate the process env (or a passed-in mapping) against the registry.

    Does not log, print, or return any secret value — secrets surface
    as ``"***"`` in the masked_value field and as themselves nowhere.
    """
    source = dict(os.environ) if env is None else dict(env)
    rows = tuple(_validate_row(req, source, mode) for req in REGISTRY)
    return ValidationReport(mode=mode, rows=rows)
