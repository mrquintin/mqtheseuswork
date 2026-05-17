"""Prompt 14 — Dialectic live recording mode.

Revision ID: 023_dialectic_live
Revises: 022_knowledge_graph
Create Date: 2026-05-16

Mirrors:
    theseus-codex/prisma/migrations/20260516300000_dialectic_live/migration.sql

Adds three tables: ``dialectic_session`` (the recorded conversation),
``dialectic_utterance`` (one speaker-turn), and
``dialectic_contradiction_flag`` (a contradiction event fired during
the recording). Additive only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision = "023_dialectic_live"
down_revision = "022_knowledge_graph"
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
    # Phase-2 consolidation: the noosphere ORM now writes to the
    # corresponding Prisma-owned PascalCase tables instead of the
    # snake_case mirrors this migration creates. Skipped on Postgres;
    # preserved for SQLite-based noosphere unit tests.
    if op.get_bind().dialect.name == "postgresql":
        return
    if not _table_exists("dialectic_session"):
        op.create_table(
            "dialectic_session",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("organization_id", sa.String(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "started_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column(
                "participants_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("audio_path", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "transcript_path", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="RECORDING",
            ),
            sa.Column(
                "visibility",
                sa.String(),
                nullable=False,
                server_default="PRIVATE",
            ),
            sa.Column(
                "live_contradictions_detected",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "principles_extracted",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("summary_memo_id", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    if _table_exists("dialectic_session") and not _index_exists(
        "dialectic_session", "dialectic_session_org_status_idx"
    ):
        op.create_index(
            "dialectic_session_org_status_idx",
            "dialectic_session",
            ["organization_id", "status"],
        )
    if _table_exists("dialectic_session") and not _index_exists(
        "dialectic_session", "dialectic_session_started_idx"
    ):
        op.create_index(
            "dialectic_session_started_idx",
            "dialectic_session",
            ["started_at"],
        )

    if not _table_exists("dialectic_utterance"):
        op.create_table(
            "dialectic_utterance",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("speaker_id", sa.String(), nullable=False),
            sa.Column(
                "start_time", sa.Float(), nullable=False, server_default="0"
            ),
            sa.Column(
                "end_time", sa.Float(), nullable=False, server_default="0"
            ),
            sa.Column("text", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "extracted_claim_ids_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "derived_principle_ids_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "live_contradiction_flags_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    if _table_exists("dialectic_utterance") and not _index_exists(
        "dialectic_utterance", "dialectic_utterance_session_start_idx"
    ):
        op.create_index(
            "dialectic_utterance_session_start_idx",
            "dialectic_utterance",
            ["session_id", "start_time"],
        )
    if _table_exists("dialectic_utterance") and not _index_exists(
        "dialectic_utterance", "dialectic_utterance_speaker_idx"
    ):
        op.create_index(
            "dialectic_utterance_speaker_idx",
            "dialectic_utterance",
            ["speaker_id"],
        )

    if not _table_exists("dialectic_contradiction_flag"):
        op.create_table(
            "dialectic_contradiction_flag",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("utterance_id", sa.String(), nullable=False),
            sa.Column(
                "flag_kind",
                sa.String(),
                nullable=False,
                server_default="INTRA_SESSION",
            ),
            sa.Column("prior_utterance_id", sa.String(), nullable=True),
            sa.Column("prior_principle_id", sa.String(), nullable=True),
            sa.Column("prior_speaker_id", sa.String(), nullable=True),
            sa.Column(
                "contradiction_score",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("axis", sa.String(), nullable=True),
            sa.Column("human_explanation", sa.Text(), nullable=True),
            sa.Column(
                "detection_method",
                sa.String(),
                nullable=False,
                server_default="",
            ),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("acknowledged_by", sa.String(), nullable=True),
            sa.Column("acknowledgment_note", sa.Text(), nullable=True),
            sa.Column(
                "detected_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    if _table_exists("dialectic_contradiction_flag") and not _index_exists(
        "dialectic_contradiction_flag",
        "dialectic_contradiction_flag_utterance_idx",
    ):
        op.create_index(
            "dialectic_contradiction_flag_utterance_idx",
            "dialectic_contradiction_flag",
            ["utterance_id"],
        )
    if _table_exists("dialectic_contradiction_flag") and not _index_exists(
        "dialectic_contradiction_flag",
        "dialectic_contradiction_flag_kind_idx",
    ):
        op.create_index(
            "dialectic_contradiction_flag_kind_idx",
            "dialectic_contradiction_flag",
            ["flag_kind"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        return
    for index_name in (
        "dialectic_contradiction_flag_kind_idx",
        "dialectic_contradiction_flag_utterance_idx",
        "dialectic_utterance_speaker_idx",
        "dialectic_utterance_session_start_idx",
        "dialectic_session_started_idx",
        "dialectic_session_org_status_idx",
    ):
        try:
            op.drop_index(index_name)
        except Exception:
            pass
    for table in (
        "dialectic_contradiction_flag",
        "dialectic_utterance",
        "dialectic_session",
    ):
        if _table_exists(table):
            try:
                op.drop_table(table)
            except Exception:
                pass
