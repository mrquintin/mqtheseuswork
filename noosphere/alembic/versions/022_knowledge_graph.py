"""Prompt 13 — knowledge-graph snapshots + cached edge reasoning.

Revision ID: 022_knowledge_graph
Revises: 021_portfolio_agent
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516280000_knowledge_graph/migration.sql

Adds the ``graph_snapshot`` table (append-only history) and the
``graph_edge_reasoning`` table (cached agent reasoning per edge).
Additive only — does not touch existing tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision = "022_knowledge_graph"
down_revision = "021_portfolio_agent"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    try:
        return name in set(sa_inspect(op.get_bind()).get_table_names())
    except Exception:
        return False


def _index_exists(table: str, index_name: str) -> bool:
    try:
        idxs = {i["name"] for i in sa_inspect(op.get_bind()).get_indexes(table)}
    except Exception:
        return False
    return index_name in idxs


def upgrade() -> None:
    if not _table_exists("graph_snapshot"):
        op.create_table(
            "graph_snapshot",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column(
                "snapshot_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "version",
                sa.String(),
                nullable=False,
                server_default="kg/v1",
            ),
            sa.Column(
                "nodes_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "edges_json", sa.Text(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "node_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "edge_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        )
    if _table_exists("graph_snapshot") and not _index_exists(
        "graph_snapshot", "graph_snapshot_org_snapat_idx"
    ):
        op.create_index(
            "graph_snapshot_org_snapat_idx",
            "graph_snapshot",
            ["organization_id", "snapshot_at"],
        )

    if not _table_exists("graph_edge_reasoning"):
        op.create_table(
            "graph_edge_reasoning",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("src", sa.String(), nullable=False),
            sa.Column("dst", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column(
                "payload_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "generated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    if _table_exists("graph_edge_reasoning") and not _index_exists(
        "graph_edge_reasoning", "graph_edge_reasoning_triple_idx"
    ):
        op.create_index(
            "graph_edge_reasoning_triple_idx",
            "graph_edge_reasoning",
            ["organization_id", "src", "dst", "kind"],
        )


def downgrade() -> None:
    for index_name in (
        "graph_edge_reasoning_triple_idx",
        "graph_snapshot_org_snapat_idx",
    ):
        try:
            op.drop_index(index_name)
        except Exception:
            pass
    for table in ("graph_edge_reasoning", "graph_snapshot"):
        if _table_exists(table):
            try:
                op.drop_table(table)
            except Exception:
                pass
