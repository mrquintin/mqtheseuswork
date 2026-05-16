"""Round 19 — Cluster index + contradiction test queue (prompt 07).

Revision ID: 016_cluster_index
Revises: 015_contradiction_engine
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516200000_cluster_index/migration.sql

Adds the noosphere-side tables for the cluster-based pre-filter that
sits between the principle add event and the canonical contradiction
engine (prompt 06). The engine remains authoritative for verdicts;
these tables decide WHICH pairs the engine looks at.

Tables created (additive):
* ``principle_cluster`` — one row per principle. Versioned by
  ``assignment_method`` so a replay ("which cluster was P in on Y?") is
  a range scan.
* ``principle_cluster_centroid`` — per-cluster centroid (float32 packed).
* ``contradiction_test_task`` — work queue. ``pair_key`` is the
  deterministic ``stable_pair_id(a,b)`` so (A,B)/(B,A) collide on dedupe.
* ``cluster_reindex_proposal`` — operator-visible drift proposals from
  the nightly resweep.

Nothing existing is renamed or dropped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "016_cluster_index"
down_revision = "015_contradiction_engine"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def upgrade() -> None:
    if not _table_exists("principle_cluster"):
        op.create_table(
            "principle_cluster",
            sa.Column("principle_id", sa.String(), primary_key=True),
            sa.Column("cluster_id", sa.String(), nullable=False),
            sa.Column(
                "assigned_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "assignment_method",
                sa.String(),
                nullable=False,
                server_default="incremental/v1",
            ),
        )
        op.create_index(
            "principle_cluster_cluster_idx",
            "principle_cluster",
            ["cluster_id", "assigned_at"],
        )

    if not _table_exists("principle_cluster_centroid"):
        op.create_table(
            "principle_cluster_centroid",
            sa.Column("cluster_id", sa.String(), primary_key=True),
            sa.Column(
                "centroid_vec",
                sa.LargeBinary(),
                nullable=False,
                server_default=sa.text("''"),
            ),
            sa.Column(
                "dim", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "member_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "assignment_method",
                sa.String(),
                nullable=False,
                server_default="incremental/v1",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

    if not _table_exists("contradiction_test_task"):
        op.create_table(
            "contradiction_test_task",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("principle_a_id", sa.String(), nullable=False),
            sa.Column("principle_b_id", sa.String(), nullable=False),
            sa.Column(
                "pair_key",
                sa.String(),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "priority",
                sa.String(),
                nullable=False,
                server_default="NORMAL",
            ),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column(
                "enqueued_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("result_id", sa.String()),
            sa.Column("last_error", sa.Text()),
        )
        op.create_index(
            "contradiction_test_task_status_priority_idx",
            "contradiction_test_task",
            ["status", "priority", "enqueued_at"],
        )
        op.create_index(
            "contradiction_test_task_pair_idx",
            "contradiction_test_task",
            ["pair_key", "enqueued_at"],
        )

    if not _table_exists("cluster_reindex_proposal"):
        op.create_table(
            "cluster_reindex_proposal",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "proposed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "drift",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0.0"),
            ),
            sa.Column(
                "cluster_count_before",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "cluster_count_after",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "summary_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column("resolved_by", sa.String()),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
        )
        op.create_index(
            "cluster_reindex_proposal_status_idx",
            "cluster_reindex_proposal",
            ["status"],
        )


def downgrade() -> None:
    for tbl in (
        "cluster_reindex_proposal",
        "contradiction_test_task",
        "principle_cluster_centroid",
        "principle_cluster",
    ):
        if _table_exists(tbl):
            op.drop_table(tbl)
