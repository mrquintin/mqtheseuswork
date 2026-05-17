"""Enforce the Postgres no-op guard on alembic migrations that touch
shared (Prisma-owned) tables.

Why this exists
---------------

The repo runs two ORMs against the same Postgres database:

* Prisma (theseus-codex) — owns the canonical schema for tables shared
  across the firm's surfaces (Currents, Forecasts, Equities, Deals, the
  bet_polymorphism pair). PascalCase table names, camelCase columns,
  proper Postgres enum types, foreign keys declared.
* Alembic (noosphere) — owns its own private snake_case tables (cascade,
  ledger, method, principle_cluster, …) and also carries SQLite-only
  *mirror* migrations for the shared tables so noosphere unit tests can
  bring up a fresh in-memory store.

The mirror migrations were never meant to run against production
Postgres — Prisma owns that schema. But there was no actual guard, and
when one of them ran first on Postgres it produced subtly wrong tables
(varchar columns instead of enums, no foreign keys). That drift cost
hours of operator time to diagnose and unblock during the May 16
incident (see ``docs/architecture/snapshots/20260516T*.pre-migrate.sql``
for the snapshot pair captured during recovery).

The fix is one line at the top of each shared-table migration's
``upgrade()`` and ``downgrade()``::

    if op.get_bind().dialect.name == "postgresql":
        return

This test makes that pattern non-optional. Any new migration that
touches a known shared table fails CI unless it includes the guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# Tables created with the SAME name by both Prisma and Alembic, as
# identified by the audit in tests/static/test_alembic_shared_table_guards
# (sister file in spirit). Update this set when a new shared-table
# mirror migration is added or when a table's ownership changes.
SHARED_TABLES: frozenset[str] = frozenset(
    {
        # Currents
        "CurrentEvent", "EventOpinion", "OpinionCitation",
        "FollowUpSession", "FollowUpMessage",
        # Forecasts
        "ForecastMarket", "ForecastPrediction", "ForecastCitation",
        "ForecastResolution", "ForecastBet", "ForecastPortfolioState",
        "ForecastFollowUpSession", "ForecastFollowUpMessage",
        # Equities
        "EquityInstrument", "EquityPriceTick", "EquitySignal",
        "EquitySignalCitation", "EquityPosition", "EquityPortfolioState",
        # Deals
        "Deal", "DealPrincipleAlignment", "DealNote",
        # Polymorphic bets (Prisma uses snake_case here via `@@map`)
        "bet_spec", "bet_resolution",

        # Phase-2 Prisma-owned tables (formerly parallel-pair snake_case
        # alembic tables that the noosphere ORM was writing to in
        # isolation). Now consolidated: the noosphere SQLModel classes
        # in noosphere/store.py declare __tablename__ as the PascalCase
        # version and map attributes to camelCase columns via sa_column.
        # The corresponding alembic CREATE-snake_case migrations were
        # guarded with the postgresql no-op pattern; their snake_case
        # target names are listed below so the meta-test catches any
        # future mutation that bypasses the guard.
        "LogicalAlgorithm", "AlgorithmInvocation",
        "AlgorithmInputObservation", "AlgorithmCalibrationSnapshot",
        "AlgorithmTriageRecommendation",
        "ContradictionDispute", "ContradictionLifecycle",
        "SynthesizerTask", "SynthesizerMemo",
        "InvestmentMemo", "PortfolioAgent", "MemoDispatch",
        "GraphSnapshot", "GraphEdgeReasoning",
        "DialecticSession", "DialecticUtterance",
        "DialecticContradictionFlag",
        # The legacy snake_case targets — these are the names the
        # alembic migrations historically used. They are now retired,
        # but listing them here ensures any future ALTER/CREATE that
        # references them by snake_case name is flagged.
        "logical_algorithm", "algorithm_invocation",
        "algorithm_input_observation", "algorithm_calibration_snapshot",
        "algorithm_triage_recommendation",
        "contradiction_dispute", "contradiction_lifecycle",
        "synthesizer_task", "synthesizer_memo",
        "investment_memo", "portfolio_agent", "memo_dispatch",
        "graph_snapshot", "graph_edge_reasoning",
        "dialectic_session", "dialectic_utterance",
        "dialectic_contradiction_flag",
    }
)

# Alembic op call patterns whose first string argument is a table name.
# Used to detect when a migration touches a shared table.
_TABLE_REFERENCING_OPS = (
    re.compile(r'op\.create_table\(\s*"([A-Za-z_]+)"'),
    re.compile(r'op\.drop_table\(\s*"([A-Za-z_]+)"'),
    re.compile(r'op\.add_column\(\s*"([A-Za-z_]+)"'),
    re.compile(r'op\.drop_column\(\s*"([A-Za-z_]+)"'),
    re.compile(r'op\.alter_column\(\s*"([A-Za-z_]+)"'),
    re.compile(r'op\.create_index\(\s*"[^"]+"\s*,\s*"([A-Za-z_]+)"'),
    re.compile(r'op\.create_foreign_key\(\s*"[^"]+"\s*,\s*"([A-Za-z_]+)"'),
    re.compile(r'op\.batch_alter_table\(\s*"([A-Za-z_]+)"'),
)

# The guard string we look for. We allow either the bare check (full
# migration is a Postgres no-op) or the same predicate wrapping a block
# (mixed-purpose migration like 021 where only some ops touch shared
# tables). Either form proves the author thought about it.
_DIALECT_GUARD_RE = re.compile(
    r'op\.get_bind\(\)\.dialect\.name\s*(==|!=)\s*"postgresql"'
)


def _migrations_dir() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2] / "noosphere" / "alembic" / "versions"


def _migration_files() -> list[Path]:
    return sorted(p for p in _migrations_dir().glob("*.py") if not p.name.startswith("_"))


def _tables_touched(text: str) -> set[str]:
    found: set[str] = set()
    for pat in _TABLE_REFERENCING_OPS:
        for m in pat.finditer(text):
            found.add(m.group(1))
    return found


@pytest.mark.parametrize("migration", _migration_files(), ids=lambda p: p.name)
def test_shared_table_migrations_have_postgres_guard(migration: Path) -> None:
    """Any alembic migration that touches a shared (Prisma-owned) table
    must include the dialect guard that makes it a Postgres no-op."""
    text = migration.read_text(encoding="utf-8")
    touched = _tables_touched(text)
    shared_touched = touched & SHARED_TABLES
    if not shared_touched:
        pytest.skip(f"{migration.name} does not touch any shared table")

    if not _DIALECT_GUARD_RE.search(text):
        sorted_shared = ", ".join(sorted(shared_touched))
        raise AssertionError(
            f"{migration.name} touches shared (Prisma-owned) table(s) "
            f"[{sorted_shared}] but is missing the Postgres dialect "
            f"guard. Add the following near the top of upgrade() (and "
            f"downgrade(), if it touches a shared table too):\n\n"
            f"    if op.get_bind().dialect.name == \"postgresql\":\n"
            f"        return\n\n"
            f"The repo's Prisma migrations own these tables on Postgres; "
            f"alembic's mirror exists for SQLite-based unit tests only. "
            f"See tests/static/test_alembic_shared_table_guards.py "
            f"docstring for the full rationale."
        )


def test_shared_tables_set_is_non_empty() -> None:
    """Guard against accidental SHARED_TABLES erasure breaking the
    parametrize above into a silent no-op."""
    assert len(SHARED_TABLES) >= 50, (
        f"SHARED_TABLES has only {len(SHARED_TABLES)} entries — likely "
        f"a regression. After Phase-2 consolidation the set covers 24 "
        f"original hard-overlap tables plus 17 PascalCase Prisma-owned "
        f"tables plus their 17 retired snake_case names = 58 entries. "
        f"A single removal is usually a bug unless paired with a Prisma "
        f"schema change in the same commit."
    )
