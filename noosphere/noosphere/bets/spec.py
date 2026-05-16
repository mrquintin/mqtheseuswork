"""BetSpec — the polymorphic-bet schema (Round 19 prompt 15).

The shape is deliberately conservative: a single ``BetSpec`` row
captures the common contract (proposition / resolution criterion /
horizon / status / outcome) and one of four nullable sub-spec blocks
discriminated by ``kind``. The kind-specific fields are validated
post-construction so a MARKET_BET cannot be saved without a
``market_bet`` block, etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_bet_id() -> str:
    return f"bet_{uuid.uuid4().hex[:24]}"


def _new_resolution_id() -> str:
    return f"betres_{uuid.uuid4().hex[:24]}"


# ── Enums ─────────────────────────────────────────────────────────────────────


class BetKind(str, Enum):
    """The four kinds of bet the firm makes."""

    MARKET_BET = "MARKET_BET"
    ADVISORY_BET = "ADVISORY_BET"
    STRATEGIC_BET = "STRATEGIC_BET"
    SCIENTIFIC_BET = "SCIENTIFIC_BET"


class BetStatus(str, Enum):
    """Lifecycle states common to every kind.

    PROPOSED → AUTHORIZED → OPEN → RESOLVED is the happy path.
    CANCELLED and EXPIRED are terminal alternatives. ADVISORY /
    STRATEGIC / SCIENTIFIC bets skip the AUTHORIZED gate (no eight-gate
    contract); they go straight to OPEN on creation.
    """

    PROPOSED = "PROPOSED"
    AUTHORIZED = "AUTHORIZED"
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class BetOutcome(str, Enum):
    """Outcome stamped at resolution time."""

    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"
    UNDETERMINED = "UNDETERMINED"


class MarketBetExchange(str, Enum):
    POLYMARKET = "POLYMARKET"
    KALSHI = "KALSHI"
    ALPACA = "ALPACA"
    ROBINHOOD = "ROBINHOOD"


class MarketBetSide(str, Enum):
    YES = "YES"
    NO = "NO"
    LONG = "LONG"
    SHORT = "SHORT"


class AdvisoryAudience(str, Enum):
    PUBLIC = "PUBLIC"
    FOUNDER_NETWORK = "FOUNDER_NETWORK"
    INTERNAL = "INTERNAL"


class AdvisoryPositionPill(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class StrategicResourceKind(str, Enum):
    FOUNDER_TIME = "FOUNDER_TIME"
    HIRING_DIRECTION = "HIRING_DIRECTION"
    PARTNERSHIP_PURSUIT = "PARTNERSHIP_PURSUIT"
    PRODUCT_DIRECTION = "PRODUCT_DIRECTION"


class ScientificDataSource(str, Enum):
    """Named external feeds with documented update cadence.

    Constraining the set is the safety contract: SCIENTIFIC bets must
    resolve against a feed with a known release cadence so the resolver
    can't be tricked into "make up a metric and resolve against it".
    """

    BLS = "BLS"
    FRED = "FRED"
    WORLD_BANK = "WORLD_BANK"
    MANUAL_OPERATOR = "MANUAL_OPERATOR"


# ── Kind-specific sub-specs ───────────────────────────────────────────────────


class MarketBetSpec(BaseModel):
    """Wraps a tradable position on a prediction market or equity broker."""

    exchange: MarketBetExchange
    side: MarketBetSide
    stake_usd: Decimal = Field(default=Decimal("0"))
    entry_price: Decimal = Field(default=Decimal("0"))
    external_order_id: Optional[str] = None
    forecast_bet_id: Optional[str] = None
    equity_position_id: Optional[str] = None
    # Snapshot of the eight-gate readiness flags at submission time —
    # informational; the live engine re-evaluates the contract.
    eight_gate_snapshot: dict[str, bool] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def _at_most_one_downstream(self) -> "MarketBetSpec":
        if self.forecast_bet_id and self.equity_position_id:
            raise ValueError(
                "MarketBetSpec carries forecast_bet_id XOR equity_position_id"
            )
        return self


class AdvisoryBetSpec(BaseModel):
    """A public commitment of position; no money moves."""

    published_at: Optional[datetime] = None
    public_url: Optional[str] = None
    position_pill: AdvisoryPositionPill = AdvisoryPositionPill.NEUTRAL
    audience: AdvisoryAudience = AdvisoryAudience.PUBLIC

    model_config = ConfigDict(use_enum_values=True)


class StrategicBetSpec(BaseModel):
    """Internal commitment of firm resources with an opportunity-cost stake."""

    resource_kind: StrategicResourceKind
    cost_estimate: float = 0.0
    cost_unit: str = "hours"
    commitment_review_at: Optional[datetime] = None

    model_config = ConfigDict(use_enum_values=True)


class ScientificBetSpec(BaseModel):
    """A falsifiable prediction resolved by polling a named data feed."""

    data_source: ScientificDataSource
    metric_query: dict[str, Any] = Field(default_factory=dict)
    expected_value: float = 0.0
    tolerance: float = 0.0
    resolution_polling_interval_s: int = 24 * 60 * 60

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def _tolerance_nonneg(self) -> "ScientificBetSpec":
        if self.tolerance < 0:
            raise ValueError("tolerance must be >= 0")
        return self


# ── Core BetSpec ──────────────────────────────────────────────────────────────


class BetSpec(BaseModel):
    """The polymorphic bet entity.

    A ``BetSpec`` row is the *abstract* claim. The kind-specific data
    lives under one of the four sub-spec fields (exactly one is
    populated, matched to ``kind``). Downstream bet rows (ForecastBet
    / EquityPosition) are linked via the ``market_bet`` block.
    """

    id: str = Field(default_factory=_new_bet_id)
    organization_id: str = ""
    kind: BetKind

    proposition: str = ""
    resolution_criterion: str = ""
    horizon_at: datetime

    created_by_memo_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # Calibration provenance — which algorithm (if any) caused the
    # originating memo to be drafted. Used when the lifecycle resolves a
    # bet so the algorithm calibration tracker can attribute the
    # outcome.
    originating_algorithm_id: Optional[str] = None

    market_bet: Optional[MarketBetSpec] = None
    advisory_bet: Optional[AdvisoryBetSpec] = None
    strategic_bet: Optional[StrategicBetSpec] = None
    scientific_bet: Optional[ScientificBetSpec] = None

    status: BetStatus = BetStatus.PROPOSED

    resolved_at: Optional[datetime] = None
    outcome: Optional[BetOutcome] = None
    outcome_note: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def _kind_matches_subspec(self) -> "BetSpec":
        kind_value = self.kind if isinstance(self.kind, str) else self.kind.value
        mapping = {
            "MARKET_BET": ("market_bet", self.market_bet),
            "ADVISORY_BET": ("advisory_bet", self.advisory_bet),
            "STRATEGIC_BET": ("strategic_bet", self.strategic_bet),
            "SCIENTIFIC_BET": ("scientific_bet", self.scientific_bet),
        }
        expected_field, expected_value = mapping[kind_value]
        if expected_value is None:
            raise ValueError(
                f"BetSpec(kind={kind_value!r}) requires the {expected_field!r} block"
            )
        for other_kind, (field, value) in mapping.items():
            if other_kind == kind_value:
                continue
            if value is not None:
                raise ValueError(
                    f"BetSpec(kind={kind_value!r}) must not carry a {field!r} block"
                )
        return self


class BetResolution(BaseModel):
    """One resolution record per BetSpec — append-only."""

    id: str = Field(default_factory=_new_resolution_id)
    bet_spec_id: str
    resolved_at: datetime = Field(default_factory=_utcnow)
    outcome: BetOutcome
    evidence_artifact_ids: list[str] = Field(default_factory=list)
    evidence_note: str = ""

    # Kind-specific outcome metrics. The lifecycle fills whichever
    # applies; the others stay None.
    pnl_usd: Optional[float] = None              # MARKET
    cost_realized: Optional[float] = None        # STRATEGIC
    accuracy_score: Optional[float] = None       # SCIENTIFIC (signed delta, lower=better)
    audience_response: Optional[str] = None      # ADVISORY (operator note)

    resolved_by: str = "agent"

    model_config = ConfigDict(use_enum_values=True)


# ── Helpers ──────────────────────────────────────────────────────────────────


def bet_spec_from_implied_bet(
    implied_bet: dict[str, Any] | None,
    *,
    organization_id: str,
    memo_id: str,
    fallback_proposition: str = "",
    fallback_horizon_at: datetime | None = None,
    originating_algorithm_id: str | None = None,
) -> BetSpec:
    """Build a ``BetSpec`` from an ``InvestmentMemo.implied_bet`` dict.

    The synthesizer's ``implied_bet`` is intentionally loose-typed
    (it predates this module). This helper performs the lossy
    upcast into a BetSpec, defaulting the kind to MARKET_BET when
    the implied bet mentions an exchange — the only shape that
    pre-Round-19 memos produce.

    Raises ``ValueError`` if the implied bet is missing both an
    exchange (MARKET hint) and an explicit ``kind`` field.
    """

    payload = dict(implied_bet or {})
    horizon = payload.get("horizon_at")
    if isinstance(horizon, str):
        try:
            horizon_at = datetime.fromisoformat(horizon.replace("Z", "+00:00"))
        except ValueError:
            horizon_at = fallback_horizon_at or _utcnow()
    elif isinstance(horizon, datetime):
        horizon_at = horizon
    else:
        horizon_at = fallback_horizon_at or _utcnow()
    if horizon_at.tzinfo is None:
        horizon_at = horizon_at.replace(tzinfo=timezone.utc)

    raw_kind = (payload.get("kind") or "").strip().upper()
    if not raw_kind:
        raw_kind = "MARKET_BET" if payload.get("exchange") else ""
    if not raw_kind:
        raise ValueError(
            "implied_bet must carry either 'kind' or 'exchange' to upcast to BetSpec"
        )
    kind = BetKind(raw_kind)

    proposition = str(payload.get("proposition") or fallback_proposition or "")
    resolution_criterion = str(
        payload.get("resolution_criterion") or payload.get("criterion") or ""
    )

    market_bet = None
    advisory_bet = None
    strategic_bet = None
    scientific_bet = None

    if kind == BetKind.MARKET_BET:
        exchange = (payload.get("exchange") or "POLYMARKET").upper()
        market_bet = MarketBetSpec(
            exchange=MarketBetExchange(exchange),
            side=MarketBetSide(str(payload.get("side") or "YES").upper()),
            stake_usd=Decimal(str(payload.get("stake_usd") or 0)),
            entry_price=Decimal(str(payload.get("entry_price") or 0)),
            forecast_bet_id=payload.get("forecast_bet_id"),
            equity_position_id=payload.get("equity_position_id"),
            external_order_id=payload.get("external_order_id"),
            eight_gate_snapshot=dict(payload.get("eight_gate_snapshot") or {}),
        )
    elif kind == BetKind.ADVISORY_BET:
        advisory_bet = AdvisoryBetSpec(
            position_pill=AdvisoryPositionPill(
                str(payload.get("position_pill") or "NEUTRAL").upper()
            ),
            audience=AdvisoryAudience(
                str(payload.get("audience") or "PUBLIC").upper()
            ),
            public_url=payload.get("public_url"),
            published_at=payload.get("published_at"),
        )
    elif kind == BetKind.STRATEGIC_BET:
        strategic_bet = StrategicBetSpec(
            resource_kind=StrategicResourceKind(
                str(payload.get("resource_kind") or "FOUNDER_TIME").upper()
            ),
            cost_estimate=float(payload.get("cost_estimate") or 0.0),
            cost_unit=str(payload.get("cost_unit") or "hours"),
            commitment_review_at=payload.get("commitment_review_at"),
        )
    elif kind == BetKind.SCIENTIFIC_BET:
        scientific_bet = ScientificBetSpec(
            data_source=ScientificDataSource(
                str(payload.get("data_source") or "FRED").upper()
            ),
            metric_query=dict(payload.get("metric_query") or {}),
            expected_value=float(payload.get("expected_value") or 0.0),
            tolerance=float(payload.get("tolerance") or 0.0),
            resolution_polling_interval_s=int(
                payload.get("resolution_polling_interval_s") or 24 * 60 * 60
            ),
        )

    # ADVISORY / STRATEGIC / SCIENTIFIC bets skip the AUTHORIZED gate.
    # MARKET bets start PROPOSED — the operator must run the
    # ``noosphere bet authorize`` step (equivalent to the eight-gate
    # authorize-live path) before the engine fires.
    initial_status = (
        BetStatus.PROPOSED if kind == BetKind.MARKET_BET else BetStatus.OPEN
    )

    return BetSpec(
        organization_id=organization_id,
        kind=kind,
        proposition=proposition,
        resolution_criterion=resolution_criterion,
        horizon_at=horizon_at,
        created_by_memo_id=memo_id,
        originating_algorithm_id=originating_algorithm_id,
        market_bet=market_bet,
        advisory_bet=advisory_bet,
        strategic_bet=strategic_bet,
        scientific_bet=scientific_bet,
        status=initial_status,
    )
