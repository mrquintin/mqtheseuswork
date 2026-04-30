"""Forecasts data model.

Revision ID: 004_forecasts_data_model
Revises: 003_currents_data_model
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql

revision = "004_forecasts_data_model"
down_revision = "003_currents_data_model"
branch_labels = None
depends_on = None

FORECAST_SOURCE = ("POLYMARKET", "KALSHI")
FORECAST_MARKET_STATUS = ("OPEN", "CLOSED", "RESOLVED", "CANCELLED")
FORECAST_PREDICTION_STATUS = (
    "PUBLISHED",
    "ABSTAINED_INSUFFICIENT_SOURCES",
    "ABSTAINED_MARKET_EXPIRED",
    "ABSTAINED_NEAR_DUPLICATE",
    "ABSTAINED_BUDGET",
    "ABSTAINED_CITATION_FABRICATION",
    "ABSTAINED_REVOKED_SOURCES",
)
FORECAST_SUPPORT_LABEL = ("DIRECT", "INDIRECT", "CONTRARY")
FORECAST_OUTCOME = ("YES", "NO", "CANCELLED", "AMBIGUOUS")
FORECAST_BET_MODE = ("PAPER", "LIVE")
FORECAST_EXCHANGE = ("POLYMARKET", "KALSHI")
FORECAST_BET_SIDE = ("YES", "NO")
FORECAST_BET_STATUS = (
    "PENDING",
    "AUTHORIZED",
    "CONFIRMED",
    "SUBMITTED",
    "FILLED",
    "CANCELLED",
    "SETTLED",
    "FAILED",
)
FORECAST_FOLLOW_UP_ROLE = ("USER", "ASSISTANT")

_TABLES = (
    "ForecastFollowUpMessage",
    "ForecastFollowUpSession",
    "ForecastBet",
    "ForecastResolution",
    "ForecastCitation",
    "ForecastPrediction",
    "ForecastPortfolioState",
    "ForecastMarket",
)
_ENUMS = (
    "ForecastFollowUpRole",
    "ForecastBetStatus",
    "ForecastBetSide",
    "ForecastExchange",
    "ForecastBetMode",
    "ForecastOutcome",
    "ForecastSupportLabel",
    "ForecastPredictionStatus",
    "ForecastMarketStatus",
    "ForecastSource",
)


def _inspector() -> sa.Inspector:
    return sa_inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in set(_inspector().get_table_names())


def _index_exists(table: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in _inspector().get_indexes(table)}


def _constraint_exists(table: str, constraint_name: str) -> bool:
    foreign_keys = _inspector().get_foreign_keys(table)
    unique_constraints = _inspector().get_unique_constraints(table)
    checks = _inspector().get_check_constraints(table)
    return constraint_name in {fk["name"] for fk in foreign_keys} | {
        uq["name"] for uq in unique_constraints
    } | {ck["name"] for ck in checks}


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _create_pg_enum(name: str, values: tuple[str, ...]) -> None:
    if _is_postgres():
        postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)


def _drop_pg_enum(name: str) -> None:
    if _is_postgres():
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)


def _enum_type(name: str, values: tuple[str, ...]) -> sa.types.TypeEngine:
    if _is_postgres():
        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.String()


def _json_type() -> sa.types.TypeEngine:
    if _is_postgres():
        return postgresql.JSONB()
    return sa.JSON()


def _create_tables() -> None:
    if not _table_exists("ForecastMarket"):
        op.create_table(
            "ForecastMarket",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column("source", _enum_type("ForecastSource", FORECAST_SOURCE), nullable=False),
            sa.Column("externalId", sa.Text(), nullable=False),
            sa.Column("title", sa.String(length=280), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("resolutionCriteria", sa.Text(), nullable=True),
            sa.Column("category", sa.Text(), nullable=True),
            sa.Column("currentYesPrice", sa.Numeric(8, 6), nullable=True),
            sa.Column("currentNoPrice", sa.Numeric(8, 6), nullable=True),
            sa.Column("volume", sa.Numeric(18, 4), nullable=True),
            sa.Column("openTime", sa.DateTime(timezone=False), nullable=True),
            sa.Column("closeTime", sa.DateTime(timezone=False), nullable=True),
            sa.Column("resolvedAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column("resolvedOutcome", _enum_type("ForecastOutcome", FORECAST_OUTCOME), nullable=True),
            sa.Column("rawPayload", _json_type(), nullable=False),
            sa.Column("status", _enum_type("ForecastMarketStatus", FORECAST_MARKET_STATUS), nullable=False, server_default="OPEN"),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("updatedAt", sa.DateTime(timezone=False), nullable=False),
        )

    if not _table_exists("ForecastPrediction"):
        op.create_table(
            "ForecastPrediction",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("marketId", sa.Text(), nullable=False),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column("probabilityYes", sa.Numeric(8, 6), nullable=True),
            sa.Column("confidenceLow", sa.Numeric(8, 6), nullable=True),
            sa.Column("confidenceHigh", sa.Numeric(8, 6), nullable=True),
            sa.Column("headline", sa.String(length=140), nullable=False),
            sa.Column("reasoning", sa.Text(), nullable=False),
            sa.Column("status", _enum_type("ForecastPredictionStatus", FORECAST_PREDICTION_STATUS), nullable=False),
            sa.Column("abstentionReason", sa.Text(), nullable=True),
            sa.Column("topicHint", sa.Text(), nullable=True),
            sa.Column("modelName", sa.Text(), nullable=False),
            sa.Column("promptTokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completionTokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("liveAuthorizedAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column("liveAuthorizedBy", sa.Text(), nullable=True),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("updatedAt", sa.DateTime(timezone=False), nullable=False),
        )

    if not _table_exists("ForecastCitation"):
        op.create_table(
            "ForecastCitation",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("predictionId", sa.Text(), nullable=False),
            sa.Column("sourceType", sa.Text(), nullable=False),
            sa.Column("sourceId", sa.Text(), nullable=False),
            sa.Column("quotedSpan", sa.Text(), nullable=False),
            sa.Column("supportLabel", _enum_type("ForecastSupportLabel", FORECAST_SUPPORT_LABEL), nullable=False),
            sa.Column("retrievalScore", sa.Float(), nullable=True),
            sa.Column("isRevoked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("revokedReason", sa.Text(), nullable=True),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        )

    if not _table_exists("ForecastResolution"):
        op.create_table(
            "ForecastResolution",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("predictionId", sa.Text(), nullable=False),
            sa.Column("marketOutcome", _enum_type("ForecastOutcome", FORECAST_OUTCOME), nullable=False),
            sa.Column("brierScore", sa.Float(), nullable=True),
            sa.Column("logLoss", sa.Float(), nullable=True),
            sa.Column("calibrationBucket", sa.Numeric(3, 1), nullable=True),
            sa.Column("resolvedAt", sa.DateTime(timezone=False), nullable=False),
            sa.Column("justification", sa.Text(), nullable=False),
            sa.Column("rawSettlement", _json_type(), nullable=True),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        )

    if not _table_exists("ForecastBet"):
        op.create_table(
            "ForecastBet",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("predictionId", sa.Text(), nullable=False),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column("mode", _enum_type("ForecastBetMode", FORECAST_BET_MODE), nullable=False, server_default="PAPER"),
            sa.Column("exchange", _enum_type("ForecastExchange", FORECAST_EXCHANGE), nullable=False),
            sa.Column("side", _enum_type("ForecastBetSide", FORECAST_BET_SIDE), nullable=False),
            sa.Column("stakeUsd", sa.Numeric(12, 2), nullable=False),
            sa.Column("entryPrice", sa.Numeric(8, 6), nullable=False),
            sa.Column("exitPrice", sa.Numeric(8, 6), nullable=True),
            sa.Column("status", _enum_type("ForecastBetStatus", FORECAST_BET_STATUS), nullable=False),
            sa.Column("externalOrderId", sa.Text(), nullable=True),
            sa.Column("clientOrderId", sa.Text(), nullable=True),
            sa.Column("settlementPnlUsd", sa.Numeric(12, 2), nullable=True),
            sa.Column("liveAuthorizedAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column("confirmedAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column("submittedAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("settledAt", sa.DateTime(timezone=False), nullable=True),
            sa.CheckConstraint('"mode" != \'LIVE\' OR "liveAuthorizedAt" IS NOT NULL', name="ForecastBet_live_requires_authorizedAt_check"),
        )

    if not _table_exists("ForecastPortfolioState"):
        op.create_table(
            "ForecastPortfolioState",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column("paperBalanceUsd", sa.Numeric(12, 2), nullable=False),
            sa.Column("liveBalanceUsd", sa.Numeric(12, 2), nullable=True),
            sa.Column("dailyLossUsd", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("dailyLossResetAt", sa.DateTime(timezone=False), nullable=False),
            sa.Column("killSwitchEngaged", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("killSwitchReason", sa.Text(), nullable=True),
            sa.Column("totalResolved", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("meanBrier90d", sa.Float(), nullable=True),
            sa.Column("meanLogLoss90d", sa.Float(), nullable=True),
            sa.Column("updatedAt", sa.DateTime(timezone=False), nullable=False),
        )

    if not _table_exists("ForecastFollowUpSession"):
        op.create_table(
            "ForecastFollowUpSession",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("predictionId", sa.Text(), nullable=False),
            sa.Column("clientFingerprint", sa.Text(), nullable=False),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("lastActivityAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        )

    if not _table_exists("ForecastFollowUpMessage"):
        op.create_table(
            "ForecastFollowUpMessage",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("sessionId", sa.Text(), nullable=False),
            sa.Column("role", _enum_type("ForecastFollowUpRole", FORECAST_FOLLOW_UP_ROLE), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("citations", _json_type(), nullable=True),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        )


def _create_indexes() -> None:
    if _table_exists("ForecastMarket"):
        if not _index_exists("ForecastMarket", "ForecastMarket_source_externalId_key"):
            op.create_index("ForecastMarket_source_externalId_key", "ForecastMarket", ["source", "externalId"], unique=True)
        if not _index_exists("ForecastMarket", "ForecastMarket_organizationId_status_closeTime_idx"):
            op.create_index("ForecastMarket_organizationId_status_closeTime_idx", "ForecastMarket", ["organizationId", "status", "closeTime"])
        if not _index_exists("ForecastMarket", "ForecastMarket_source_category_idx"):
            op.create_index("ForecastMarket_source_category_idx", "ForecastMarket", ["source", "category"])
        if not _index_exists("ForecastMarket", "ForecastMarket_updatedAt_idx"):
            op.create_index("ForecastMarket_updatedAt_idx", "ForecastMarket", ["updatedAt"])

    if _table_exists("ForecastPrediction"):
        if not _index_exists("ForecastPrediction", "ForecastPrediction_organizationId_status_createdAt_idx"):
            op.create_index("ForecastPrediction_organizationId_status_createdAt_idx", "ForecastPrediction", ["organizationId", "status", "createdAt"])
        if not _index_exists("ForecastPrediction", "ForecastPrediction_marketId_createdAt_idx"):
            op.create_index("ForecastPrediction_marketId_createdAt_idx", "ForecastPrediction", ["marketId", "createdAt"])
        if not _index_exists("ForecastPrediction", "ForecastPrediction_liveAuthorizedAt_idx"):
            op.create_index("ForecastPrediction_liveAuthorizedAt_idx", "ForecastPrediction", ["liveAuthorizedAt"])

    if _table_exists("ForecastCitation"):
        if not _index_exists("ForecastCitation", "ForecastCitation_predictionId_idx"):
            op.create_index("ForecastCitation_predictionId_idx", "ForecastCitation", ["predictionId"])
        if not _index_exists("ForecastCitation", "ForecastCitation_sourceType_sourceId_idx"):
            op.create_index("ForecastCitation_sourceType_sourceId_idx", "ForecastCitation", ["sourceType", "sourceId"])

    if _table_exists("ForecastResolution"):
        if not _index_exists("ForecastResolution", "ForecastResolution_predictionId_key"):
            op.create_index("ForecastResolution_predictionId_key", "ForecastResolution", ["predictionId"], unique=True)
        if not _index_exists("ForecastResolution", "ForecastResolution_resolvedAt_idx"):
            op.create_index("ForecastResolution_resolvedAt_idx", "ForecastResolution", ["resolvedAt"])
        if not _index_exists("ForecastResolution", "ForecastResolution_calibrationBucket_idx"):
            op.create_index("ForecastResolution_calibrationBucket_idx", "ForecastResolution", ["calibrationBucket"])

    if _table_exists("ForecastBet"):
        if not _index_exists("ForecastBet", "ForecastBet_organizationId_mode_createdAt_idx"):
            op.create_index("ForecastBet_organizationId_mode_createdAt_idx", "ForecastBet", ["organizationId", "mode", "createdAt"])
        if not _index_exists("ForecastBet", "ForecastBet_predictionId_status_idx"):
            op.create_index("ForecastBet_predictionId_status_idx", "ForecastBet", ["predictionId", "status"])
        if not _index_exists("ForecastBet", "ForecastBet_externalOrderId_idx"):
            op.create_index("ForecastBet_externalOrderId_idx", "ForecastBet", ["externalOrderId"])
        if not _index_exists("ForecastBet", "ForecastBet_clientOrderId_idx"):
            op.create_index("ForecastBet_clientOrderId_idx", "ForecastBet", ["clientOrderId"])

    if _table_exists("ForecastPortfolioState") and not _index_exists("ForecastPortfolioState", "ForecastPortfolioState_organizationId_key"):
        op.create_index("ForecastPortfolioState_organizationId_key", "ForecastPortfolioState", ["organizationId"], unique=True)

    if _table_exists("ForecastFollowUpSession"):
        if not _index_exists("ForecastFollowUpSession", "ForecastFollowUpSession_predictionId_lastActivityAt_idx"):
            op.create_index("ForecastFollowUpSession_predictionId_lastActivityAt_idx", "ForecastFollowUpSession", ["predictionId", "lastActivityAt"])
        if not _index_exists("ForecastFollowUpSession", "ForecastFollowUpSession_clientFingerprint_createdAt_idx"):
            op.create_index("ForecastFollowUpSession_clientFingerprint_createdAt_idx", "ForecastFollowUpSession", ["clientFingerprint", "createdAt"])

    if _table_exists("ForecastFollowUpMessage") and not _index_exists("ForecastFollowUpMessage", "ForecastFollowUpMessage_sessionId_createdAt_idx"):
        op.create_index("ForecastFollowUpMessage_sessionId_createdAt_idx", "ForecastFollowUpMessage", ["sessionId", "createdAt"])


def _create_foreign_keys() -> None:
    if not _is_postgres():
        return

    if _table_exists("Organization") and _table_exists("ForecastMarket") and not _constraint_exists("ForecastMarket", "ForecastMarket_organizationId_fkey"):
        op.create_foreign_key("ForecastMarket_organizationId_fkey", "ForecastMarket", "Organization", ["organizationId"], ["id"], ondelete="RESTRICT", onupdate="CASCADE")
    if _table_exists("Organization") and _table_exists("ForecastPrediction") and not _constraint_exists("ForecastPrediction", "ForecastPrediction_organizationId_fkey"):
        op.create_foreign_key("ForecastPrediction_organizationId_fkey", "ForecastPrediction", "Organization", ["organizationId"], ["id"], ondelete="RESTRICT", onupdate="CASCADE")
    if _table_exists("ForecastMarket") and _table_exists("ForecastPrediction") and not _constraint_exists("ForecastPrediction", "ForecastPrediction_marketId_fkey"):
        op.create_foreign_key("ForecastPrediction_marketId_fkey", "ForecastPrediction", "ForecastMarket", ["marketId"], ["id"], ondelete="CASCADE", onupdate="CASCADE")
    if _table_exists("ForecastPrediction") and _table_exists("ForecastCitation") and not _constraint_exists("ForecastCitation", "ForecastCitation_predictionId_fkey"):
        op.create_foreign_key("ForecastCitation_predictionId_fkey", "ForecastCitation", "ForecastPrediction", ["predictionId"], ["id"], ondelete="CASCADE", onupdate="CASCADE")
    if _table_exists("ForecastPrediction") and _table_exists("ForecastResolution") and not _constraint_exists("ForecastResolution", "ForecastResolution_predictionId_fkey"):
        op.create_foreign_key("ForecastResolution_predictionId_fkey", "ForecastResolution", "ForecastPrediction", ["predictionId"], ["id"], ondelete="CASCADE", onupdate="CASCADE")
    if _table_exists("ForecastPrediction") and _table_exists("ForecastBet") and not _constraint_exists("ForecastBet", "ForecastBet_predictionId_fkey"):
        op.create_foreign_key("ForecastBet_predictionId_fkey", "ForecastBet", "ForecastPrediction", ["predictionId"], ["id"], onupdate="CASCADE")
    if _table_exists("Organization") and _table_exists("ForecastBet") and not _constraint_exists("ForecastBet", "ForecastBet_organizationId_fkey"):
        op.create_foreign_key("ForecastBet_organizationId_fkey", "ForecastBet", "Organization", ["organizationId"], ["id"], ondelete="RESTRICT", onupdate="CASCADE")
    if _table_exists("Organization") and _table_exists("ForecastPortfolioState") and not _constraint_exists("ForecastPortfolioState", "ForecastPortfolioState_organizationId_fkey"):
        op.create_foreign_key("ForecastPortfolioState_organizationId_fkey", "ForecastPortfolioState", "Organization", ["organizationId"], ["id"], ondelete="RESTRICT", onupdate="CASCADE")
    if _table_exists("ForecastPrediction") and _table_exists("ForecastFollowUpSession") and not _constraint_exists("ForecastFollowUpSession", "ForecastFollowUpSession_predictionId_fkey"):
        op.create_foreign_key("ForecastFollowUpSession_predictionId_fkey", "ForecastFollowUpSession", "ForecastPrediction", ["predictionId"], ["id"], ondelete="CASCADE", onupdate="CASCADE")
    if _table_exists("ForecastFollowUpSession") and _table_exists("ForecastFollowUpMessage") and not _constraint_exists("ForecastFollowUpMessage", "ForecastFollowUpMessage_sessionId_fkey"):
        op.create_foreign_key("ForecastFollowUpMessage_sessionId_fkey", "ForecastFollowUpMessage", "ForecastFollowUpSession", ["sessionId"], ["id"], ondelete="CASCADE", onupdate="CASCADE")


def _create_check_constraints() -> None:
    if not _is_postgres() or not _table_exists("ForecastBet"):
        return
    if not _constraint_exists("ForecastBet", "ForecastBet_live_requires_authorizedAt_check"):
        op.create_check_constraint(
            "ForecastBet_live_requires_authorizedAt_check",
            "ForecastBet",
            '"mode" != \'LIVE\' OR "liveAuthorizedAt" IS NOT NULL',
        )


def upgrade() -> None:
    _create_pg_enum("ForecastSource", FORECAST_SOURCE)
    _create_pg_enum("ForecastMarketStatus", FORECAST_MARKET_STATUS)
    _create_pg_enum("ForecastPredictionStatus", FORECAST_PREDICTION_STATUS)
    _create_pg_enum("ForecastSupportLabel", FORECAST_SUPPORT_LABEL)
    _create_pg_enum("ForecastOutcome", FORECAST_OUTCOME)
    _create_pg_enum("ForecastBetMode", FORECAST_BET_MODE)
    _create_pg_enum("ForecastExchange", FORECAST_EXCHANGE)
    _create_pg_enum("ForecastBetSide", FORECAST_BET_SIDE)
    _create_pg_enum("ForecastBetStatus", FORECAST_BET_STATUS)
    _create_pg_enum("ForecastFollowUpRole", FORECAST_FOLLOW_UP_ROLE)
    _create_tables()
    _create_indexes()
    _create_foreign_keys()
    _create_check_constraints()


def downgrade() -> None:
    for table in _TABLES:
        if _table_exists(table):
            op.drop_table(table)
    for enum_name in _ENUMS:
        _drop_pg_enum(enum_name)
