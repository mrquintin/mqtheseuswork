"""Quantitative test-result table.

Revision ID: 011_quantitative_test_results
Revises: 010_equities_data_model
Create Date: 2026-05-15

Mirrors:
    theseus-codex/prisma/migrations/20260515140000_quantitative_test_results/migration.sql

One row per runner pass over an APPROVED ``QuantitativeFormalisation``.
The full Pydantic payload (``metric_values``, ``test_outputs``,
``decision_summary``, etc.) is held in ``payload_json``; the duplicated
indexed columns power the most-recent-per-formalisation read the
public surface and CLI ``status`` view depend on.

In noosphere-only sqlite dev deployments the table is created by
``SQLModel.metadata.create_all`` from
``noosphere.store.StoredQuantitativeTestResult``; this migration is
for shared-database (Postgres) deployments where Alembic is the
source of truth.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "011_quantitative_test_results"
down_revision = "010_equities_data_model"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade() -> None:
    if _table_exists("quantitative_test_result"):
        return
    op.create_table(
        "quantitative_test_result",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("formalisation_id", sa.String(), nullable=False),
        sa.Column("principle_id", sa.String(), nullable=False, server_default=""),
        sa.Column("run_stamp", sa.String(), nullable=False),
        sa.Column(
            "status", sa.String(), nullable=False, server_default="RAN"
        ),
        sa.Column("artifacts_path", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "payload_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "formalisation_id",
            "run_stamp",
            name="uq_quantitative_test_result_formalisation_run",
        ),
    )
    op.create_index(
        "ix_quantitative_test_result_formalisation_id",
        "quantitative_test_result",
        ["formalisation_id"],
    )
    op.create_index(
        "ix_quantitative_test_result_run_stamp",
        "quantitative_test_result",
        ["run_stamp"],
    )
    op.create_index(
        "ix_quantitative_test_result_principle_id",
        "quantitative_test_result",
        ["principle_id"],
    )


def downgrade() -> None:
    if not _table_exists("quantitative_test_result"):
        return
    op.drop_index(
        "ix_quantitative_test_result_principle_id",
        table_name="quantitative_test_result",
    )
    op.drop_index(
        "ix_quantitative_test_result_run_stamp",
        table_name="quantitative_test_result",
    )
    op.drop_index(
        "ix_quantitative_test_result_formalisation_id",
        table_name="quantitative_test_result",
    )
    op.drop_table("quantitative_test_result")
