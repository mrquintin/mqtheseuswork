"""Equities data model.

Revision ID: 010_equities_data_model
Revises: 009_quantitative_formalisation
Create Date: 2026-05-15

Mirrors:
    theseus-codex/prisma/migrations/20260515130000_equities_data_model/migration.sql

Adds the EquityInstrument / EquityPriceTick / EquitySignal /
EquitySignalCitation / EquityPosition / EquityPortfolioState tables
alongside the existing prediction-market Forecast* tables. No Forecast*
table is renamed or altered. Equity safety reuses
``noosphere.forecasts.safety``; the migration is data-only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql

revision = "010_equities_data_model"
down_revision = "009_quantitative_formalisation"
branch_labels = None
depends_on = None

EQUITY_ASSET_CLASS = ("STOCK", "ETF", "ADR")
EQUITY_PRICE_SOURCE = ("ALPACA", "ROBINHOOD", "YFINANCE", "MANUAL")
EQUITY_SIGNAL_DIRECTION = ("BULLISH", "BEARISH", "NEUTRAL", "ABSTAINED")
EQUITY_SIGNAL_STATUS = ("PUBLISHED", "ABSTAINED", "REVOKED")
EQUITY_POSITION_MODE = ("PAPER", "LIVE")
EQUITY_POSITION_SIDE = ("LONG", "SHORT", "CASH_RESERVE")
EQUITY_POSITION_STATUS = ("PENDING", "OPEN", "CLOSED", "CANCELLED", "FAILED")
FORECAST_SUPPORT_LABEL = ("DIRECT", "INDIRECT", "CONTRARY")

_TABLES = (
    "EquityPortfolioState",
    "EquityPosition",
    "EquitySignalCitation",
    "EquitySignal",
    "EquityPriceTick",
    "EquityInstrument",
)
_ENUMS = (
    "EquityPositionStatus",
    "EquityPositionSide",
    "EquityPositionMode",
    "EquitySignalStatus",
    "EquitySignalDirection",
    "EquityPriceSource",
    "EquityAssetClass",
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
    return constraint_name in (
        {fk["name"] for fk in foreign_keys}
        | {uq["name"] for uq in unique_constraints}
        | {ck["name"] for ck in checks}
    )


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


def _create_tables() -> None:
    if not _table_exists("EquityInstrument"):
        op.create_table(
            "EquityInstrument",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("symbol", sa.String(length=16), nullable=False),
            sa.Column("exchange", sa.String(length=16), nullable=False),
            sa.Column(
                "assetClass",
                _enum_type("EquityAssetClass", EQUITY_ASSET_CLASS),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=280), nullable=False),
            sa.Column("cusip", sa.String(length=16), nullable=True),
            sa.Column("figi", sa.String(length=16), nullable=True),
            sa.Column(
                "isTradable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("lastPrice", sa.Numeric(18, 6), nullable=True),
            sa.Column("lastPriceAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "currency",
                sa.String(length=8),
                nullable=False,
                server_default="USD",
            ),
            sa.Column(
                "createdAt",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updatedAt", sa.DateTime(timezone=False), nullable=False),
        )

    if not _table_exists("EquityPriceTick"):
        op.create_table(
            "EquityPriceTick",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("instrumentId", sa.Text(), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=False), nullable=False),
            sa.Column("open", sa.Numeric(18, 6), nullable=False),
            sa.Column("high", sa.Numeric(18, 6), nullable=False),
            sa.Column("low", sa.Numeric(18, 6), nullable=False),
            sa.Column("close", sa.Numeric(18, 6), nullable=False),
            sa.Column("volume", sa.Numeric(20, 4), nullable=False),
            sa.Column(
                "source",
                _enum_type("EquityPriceSource", EQUITY_PRICE_SOURCE),
                nullable=False,
            ),
            sa.Column(
                "createdAt",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _table_exists("EquitySignal"):
        op.create_table(
            "EquitySignal",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("instrumentId", sa.Text(), nullable=False),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column(
                "direction",
                _enum_type("EquitySignalDirection", EQUITY_SIGNAL_DIRECTION),
                nullable=False,
            ),
            sa.Column("confidenceLow", sa.Numeric(8, 6), nullable=False),
            sa.Column("confidenceHigh", sa.Numeric(8, 6), nullable=False),
            sa.Column("targetPriceLow", sa.Numeric(18, 6), nullable=True),
            sa.Column("targetPriceHigh", sa.Numeric(18, 6), nullable=True),
            sa.Column("horizonDays", sa.Integer(), nullable=False),
            sa.Column("headline", sa.String(length=140), nullable=False),
            sa.Column("reasoning", sa.Text(), nullable=False),
            sa.Column("modelName", sa.Text(), nullable=False),
            sa.Column(
                "promptTokens", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "completionTokens", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "status",
                _enum_type("EquitySignalStatus", EQUITY_SIGNAL_STATUS),
                nullable=False,
            ),
            sa.Column("abstentionReason", sa.Text(), nullable=True),
            sa.Column("liveAuthorizedAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column("liveAuthorizedBy", sa.Text(), nullable=True),
            sa.Column(
                "createdAt",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updatedAt", sa.DateTime(timezone=False), nullable=False),
        )

    if not _table_exists("EquitySignalCitation"):
        op.create_table(
            "EquitySignalCitation",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("signalId", sa.Text(), nullable=False),
            sa.Column("sourceType", sa.Text(), nullable=False),
            sa.Column("sourceId", sa.Text(), nullable=False),
            sa.Column("quotedSpan", sa.Text(), nullable=False),
            sa.Column(
                "supportLabel",
                _enum_type("ForecastSupportLabel", FORECAST_SUPPORT_LABEL),
                nullable=False,
            ),
            sa.Column(
                "createdAt",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _table_exists("EquityPosition"):
        op.create_table(
            "EquityPosition",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("signalId", sa.Text(), nullable=False),
            sa.Column("instrumentId", sa.Text(), nullable=False),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column(
                "mode",
                _enum_type("EquityPositionMode", EQUITY_POSITION_MODE),
                nullable=False,
                server_default="PAPER",
            ),
            sa.Column(
                "side",
                _enum_type("EquityPositionSide", EQUITY_POSITION_SIDE),
                nullable=False,
            ),
            sa.Column("qty", sa.Numeric(20, 6), nullable=False),
            sa.Column("entryPrice", sa.Numeric(18, 6), nullable=False),
            sa.Column("entryAt", sa.DateTime(timezone=False), nullable=False),
            sa.Column("exitPrice", sa.Numeric(18, 6), nullable=True),
            sa.Column("exitAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "status",
                _enum_type("EquityPositionStatus", EQUITY_POSITION_STATUS),
                nullable=False,
            ),
            sa.Column("externalOrderId", sa.Text(), nullable=True),
            sa.Column("realizedPnlUsd", sa.Numeric(14, 4), nullable=True),
            sa.Column("unrealizedPnlUsd", sa.Numeric(14, 4), nullable=True),
            sa.Column("liveAuthorizedAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "createdAt",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updatedAt", sa.DateTime(timezone=False), nullable=False),
            sa.CheckConstraint(
                '"mode" != \'LIVE\' OR "liveAuthorizedAt" IS NOT NULL',
                name="EquityPosition_live_requires_authorizedAt_check",
            ),
        )

    if not _table_exists("EquityPortfolioState"):
        op.create_table(
            "EquityPortfolioState",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column("paperBalanceUsd", sa.Numeric(14, 2), nullable=False),
            sa.Column("liveBalanceUsd", sa.Numeric(14, 2), nullable=True),
            sa.Column(
                "dailyLossUsd",
                sa.Numeric(14, 2),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "dailyLossWindowResetAt",
                sa.DateTime(timezone=False),
                nullable=False,
            ),
            sa.Column(
                "killSwitchEngaged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("killSwitchReason", sa.Text(), nullable=True),
            sa.Column("updatedAt", sa.DateTime(timezone=False), nullable=False),
        )


def _create_indexes() -> None:
    if _table_exists("EquityInstrument"):
        if not _index_exists("EquityInstrument", "EquityInstrument_symbol_exchange_key"):
            op.create_index(
                "EquityInstrument_symbol_exchange_key",
                "EquityInstrument",
                ["symbol", "exchange"],
                unique=True,
            )
        if not _index_exists("EquityInstrument", "EquityInstrument_assetClass_idx"):
            op.create_index(
                "EquityInstrument_assetClass_idx",
                "EquityInstrument",
                ["assetClass"],
            )
        if not _index_exists("EquityInstrument", "EquityInstrument_updatedAt_idx"):
            op.create_index(
                "EquityInstrument_updatedAt_idx",
                "EquityInstrument",
                ["updatedAt"],
            )

    if _table_exists("EquityPriceTick"):
        if not _index_exists("EquityPriceTick", "EquityPriceTick_instrumentId_ts_idx"):
            op.create_index(
                "EquityPriceTick_instrumentId_ts_idx",
                "EquityPriceTick",
                ["instrumentId", sa.text("ts DESC")] if _is_postgres() else [
                    "instrumentId",
                    "ts",
                ],
            )
        if not _index_exists("EquityPriceTick", "EquityPriceTick_source_idx"):
            op.create_index(
                "EquityPriceTick_source_idx", "EquityPriceTick", ["source"]
            )

    if _table_exists("EquitySignal"):
        if not _index_exists(
            "EquitySignal", "EquitySignal_organizationId_status_createdAt_idx"
        ):
            op.create_index(
                "EquitySignal_organizationId_status_createdAt_idx",
                "EquitySignal",
                ["organizationId", "status", "createdAt"],
            )
        if not _index_exists(
            "EquitySignal", "EquitySignal_instrumentId_createdAt_idx"
        ):
            op.create_index(
                "EquitySignal_instrumentId_createdAt_idx",
                "EquitySignal",
                ["instrumentId", "createdAt"],
            )
        if not _index_exists("EquitySignal", "EquitySignal_liveAuthorizedAt_idx"):
            op.create_index(
                "EquitySignal_liveAuthorizedAt_idx",
                "EquitySignal",
                ["liveAuthorizedAt"],
            )

    if _table_exists("EquitySignalCitation"):
        if not _index_exists(
            "EquitySignalCitation", "EquitySignalCitation_signalId_idx"
        ):
            op.create_index(
                "EquitySignalCitation_signalId_idx",
                "EquitySignalCitation",
                ["signalId"],
            )
        if not _index_exists(
            "EquitySignalCitation",
            "EquitySignalCitation_sourceType_sourceId_idx",
        ):
            op.create_index(
                "EquitySignalCitation_sourceType_sourceId_idx",
                "EquitySignalCitation",
                ["sourceType", "sourceId"],
            )

    if _table_exists("EquityPosition"):
        if not _index_exists("EquityPosition", "EquityPosition_signalId_idx"):
            op.create_index(
                "EquityPosition_signalId_idx", "EquityPosition", ["signalId"]
            )
        if not _index_exists(
            "EquityPosition", "EquityPosition_instrumentId_status_idx"
        ):
            op.create_index(
                "EquityPosition_instrumentId_status_idx",
                "EquityPosition",
                ["instrumentId", "status"],
            )
        if not _index_exists(
            "EquityPosition", "EquityPosition_externalOrderId_idx"
        ):
            op.create_index(
                "EquityPosition_externalOrderId_idx",
                "EquityPosition",
                ["externalOrderId"],
            )

    if _table_exists("EquityPortfolioState") and not _index_exists(
        "EquityPortfolioState", "EquityPortfolioState_organizationId_key"
    ):
        op.create_index(
            "EquityPortfolioState_organizationId_key",
            "EquityPortfolioState",
            ["organizationId"],
            unique=True,
        )


def _create_foreign_keys() -> None:
    if not _is_postgres():
        return

    if (
        _table_exists("EquityInstrument")
        and _table_exists("EquityPriceTick")
        and not _constraint_exists(
            "EquityPriceTick", "EquityPriceTick_instrumentId_fkey"
        )
    ):
        op.create_foreign_key(
            "EquityPriceTick_instrumentId_fkey",
            "EquityPriceTick",
            "EquityInstrument",
            ["instrumentId"],
            ["id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        )

    if (
        _table_exists("EquityInstrument")
        and _table_exists("EquitySignal")
        and not _constraint_exists("EquitySignal", "EquitySignal_instrumentId_fkey")
    ):
        op.create_foreign_key(
            "EquitySignal_instrumentId_fkey",
            "EquitySignal",
            "EquityInstrument",
            ["instrumentId"],
            ["id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        )

    if (
        _table_exists("Organization")
        and _table_exists("EquitySignal")
        and not _constraint_exists("EquitySignal", "EquitySignal_organizationId_fkey")
    ):
        op.create_foreign_key(
            "EquitySignal_organizationId_fkey",
            "EquitySignal",
            "Organization",
            ["organizationId"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        )

    if (
        _table_exists("EquitySignal")
        and _table_exists("EquitySignalCitation")
        and not _constraint_exists(
            "EquitySignalCitation", "EquitySignalCitation_signalId_fkey"
        )
    ):
        op.create_foreign_key(
            "EquitySignalCitation_signalId_fkey",
            "EquitySignalCitation",
            "EquitySignal",
            ["signalId"],
            ["id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        )

    if (
        _table_exists("EquitySignal")
        and _table_exists("EquityPosition")
        and not _constraint_exists("EquityPosition", "EquityPosition_signalId_fkey")
    ):
        op.create_foreign_key(
            "EquityPosition_signalId_fkey",
            "EquityPosition",
            "EquitySignal",
            ["signalId"],
            ["id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        )

    if (
        _table_exists("EquityInstrument")
        and _table_exists("EquityPosition")
        and not _constraint_exists(
            "EquityPosition", "EquityPosition_instrumentId_fkey"
        )
    ):
        op.create_foreign_key(
            "EquityPosition_instrumentId_fkey",
            "EquityPosition",
            "EquityInstrument",
            ["instrumentId"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        )

    if (
        _table_exists("Organization")
        and _table_exists("EquityPosition")
        and not _constraint_exists(
            "EquityPosition", "EquityPosition_organizationId_fkey"
        )
    ):
        op.create_foreign_key(
            "EquityPosition_organizationId_fkey",
            "EquityPosition",
            "Organization",
            ["organizationId"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        )

    if (
        _table_exists("Organization")
        and _table_exists("EquityPortfolioState")
        and not _constraint_exists(
            "EquityPortfolioState", "EquityPortfolioState_organizationId_fkey"
        )
    ):
        op.create_foreign_key(
            "EquityPortfolioState_organizationId_fkey",
            "EquityPortfolioState",
            "Organization",
            ["organizationId"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        )


def _create_check_constraints() -> None:
    if not _is_postgres() or not _table_exists("EquityPosition"):
        return
    if not _constraint_exists(
        "EquityPosition", "EquityPosition_live_requires_authorizedAt_check"
    ):
        op.create_check_constraint(
            "EquityPosition_live_requires_authorizedAt_check",
            "EquityPosition",
            '"mode" != \'LIVE\' OR "liveAuthorizedAt" IS NOT NULL',
        )


def upgrade() -> None:
    _create_pg_enum("EquityAssetClass", EQUITY_ASSET_CLASS)
    _create_pg_enum("EquityPriceSource", EQUITY_PRICE_SOURCE)
    _create_pg_enum("EquitySignalDirection", EQUITY_SIGNAL_DIRECTION)
    _create_pg_enum("EquitySignalStatus", EQUITY_SIGNAL_STATUS)
    _create_pg_enum("EquityPositionMode", EQUITY_POSITION_MODE)
    _create_pg_enum("EquityPositionSide", EQUITY_POSITION_SIDE)
    _create_pg_enum("EquityPositionStatus", EQUITY_POSITION_STATUS)
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
