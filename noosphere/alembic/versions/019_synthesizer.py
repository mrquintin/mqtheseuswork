"""Prompt 10 — synthesizer task queue + memo persistence.

Revision ID: 019_synthesizer
Revises: 018_provenance_kind
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516240000_synthesizer/migration.sql

Adds two new tables on the noosphere side:

* ``synthesizer_task`` — the queue the scheduler's ``synthesizer_tick``
  drains. Operator queries typically bypass the queue; algorithm- and
  currents-triggered requests enqueue here so the producing tick is
  not blocked by the synthesizer's LLM round-trip.
* ``synthesizer_memo`` — the persisted audit-shaped conclusion the
  portfolio agent reads. Carries a ``synthesizer_version`` column so
  later format rolls can group by version.

Also adds the ``triggers_synthesis`` column on ``logical_algorithm``
so the runtime knows which invocations should enqueue a synthesis
task.

Additive only — no rename or drop. Safe to run twice (the column /
table guards check ``information_schema`` / ``PRAGMA``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "019_synthesizer"
down_revision = "018_provenance_kind"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def _column_exists(table: str, column: str) -> bool:
    try:
        cols = {c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)}
    except Exception:
        return False
    return column in cols


def _index_exists(table: str, index_name: str) -> bool:
    try:
        idxs = {i["name"] for i in sa_inspect(op.get_bind()).get_indexes(table)}
    except Exception:
        return False
    return index_name in idxs


def upgrade() -> None:
    if not _table_exists("synthesizer_task"):
        op.create_table(
            "synthesizer_task",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column(
                "trigger",
                sa.String(),
                nullable=False,
                server_default="OPERATOR",
            ),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column(
                "enqueued_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("invocation_id", sa.String(), nullable=True),
            sa.Column("current_event_id", sa.String(), nullable=True),
            sa.Column("memo_id", sa.String(), nullable=True),
            sa.Column("outcome", sa.String(), nullable=True),
            sa.Column(
                "payload_json", sa.Text(), nullable=False, server_default="{}"
            ),
        )
    if _table_exists("synthesizer_task"):
        if not _index_exists(
            "synthesizer_task", "synthesizer_task_status_enqueued_idx"
        ):
            op.create_index(
                "synthesizer_task_status_enqueued_idx",
                "synthesizer_task",
                ["status", "enqueued_at"],
            )
        if not _index_exists(
            "synthesizer_task", "synthesizer_task_org_status_idx"
        ):
            op.create_index(
                "synthesizer_task_org_status_idx",
                "synthesizer_task",
                ["organization_id", "status"],
            )

    if not _table_exists("synthesizer_memo"):
        op.create_table(
            "synthesizer_memo",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "synthesizer_version",
                sa.String(),
                nullable=False,
                server_default="synthesizer/v1",
            ),
            sa.Column(
                "question", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column(
                "payload_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
        )
    if _table_exists("synthesizer_memo"):
        if not _index_exists(
            "synthesizer_memo", "synthesizer_memo_org_created_idx"
        ):
            op.create_index(
                "synthesizer_memo_org_created_idx",
                "synthesizer_memo",
                ["organization_id", "created_at"],
            )

    # Wire the algorithm row to the synthesizer trigger flag.
    if _table_exists("logical_algorithm") and not _column_exists(
        "logical_algorithm", "triggers_synthesis"
    ):
        op.add_column(
            "logical_algorithm",
            sa.Column(
                "triggers_synthesis",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    if _table_exists("logical_algorithm") and _column_exists(
        "logical_algorithm", "triggers_synthesis"
    ):
        with op.batch_alter_table("logical_algorithm") as batch:
            batch.drop_column("triggers_synthesis")
    for index_name, table in (
        ("synthesizer_memo_org_created_idx", "synthesizer_memo"),
        ("synthesizer_task_status_enqueued_idx", "synthesizer_task"),
        ("synthesizer_task_org_status_idx", "synthesizer_task"),
    ):
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)
    if _table_exists("synthesizer_memo"):
        op.drop_table("synthesizer_memo")
    if _table_exists("synthesizer_task"):
        op.drop_table("synthesizer_task")
