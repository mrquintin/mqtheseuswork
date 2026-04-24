"""Currents (Wave 1): current_event, event_opinion, opinion_citation,
followup_session, followup_message tables.

Revision ID: 003_current_events
Revises: 002_round3_foundations
Create Date: 2026-04-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "003_current_events"
down_revision = "002_round3_foundations"
branch_labels = None
depends_on = None


_NEW_TABLES = [
    "current_event",
    "event_opinion",
    "opinion_citation",
    "followup_session",
    "followup_message",
]


def _table_exists(name: str) -> bool:
    return name in set(sa_inspect(op.get_bind()).get_table_names())


def _index_exists(table: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in sa_inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if not _table_exists("current_event"):
        op.create_table(
            "current_event",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("source", sa.String, nullable=False, server_default=""),
            sa.Column("source_captured_at", sa.DateTime, nullable=False),
            sa.Column("ingested_at", sa.DateTime, nullable=False),
            sa.Column("dedupe_hash", sa.String, nullable=False, server_default=""),
            sa.Column("status", sa.String, nullable=False, server_default="observed"),
            sa.Column("topic_hint", sa.String, nullable=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("current_event", "ix_current_event_status_source_captured_at"):
        op.create_index(
            "ix_current_event_status_source_captured_at",
            "current_event",
            ["status", "source_captured_at"],
        )
    if not _index_exists("current_event", "ix_current_event_dedupe_hash"):
        op.create_index(
            "ix_current_event_dedupe_hash",
            "current_event",
            ["dedupe_hash"],
            unique=True,
        )

    if not _table_exists("event_opinion"):
        op.create_table(
            "event_opinion",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("event_id", sa.String, nullable=False, server_default=""),
            sa.Column("generated_at", sa.DateTime, nullable=False),
            sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("event_opinion", "ix_event_opinion_event_id"):
        op.create_index("ix_event_opinion_event_id", "event_opinion", ["event_id"])
    if not _index_exists("event_opinion", "ix_event_opinion_generated_at"):
        # Plain index; ORDER BY generated_at DESC will still scan it efficiently
        # on both SQLite and Postgres.
        op.create_index(
            "ix_event_opinion_generated_at",
            "event_opinion",
            ["generated_at"],
        )

    if not _table_exists("opinion_citation"):
        op.create_table(
            "opinion_citation",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("opinion_id", sa.String, nullable=False, server_default=""),
            sa.Column("conclusion_id", sa.String, nullable=True),
            sa.Column("claim_id", sa.String, nullable=True),
            sa.Column("ordinal", sa.Integer, nullable=False, server_default="0"),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("opinion_citation", "ix_opinion_citation_opinion_id"):
        op.create_index(
            "ix_opinion_citation_opinion_id", "opinion_citation", ["opinion_id"]
        )
    if not _index_exists("opinion_citation", "ix_opinion_citation_conclusion_id"):
        op.create_index(
            "ix_opinion_citation_conclusion_id", "opinion_citation", ["conclusion_id"]
        )
    if not _index_exists("opinion_citation", "ix_opinion_citation_claim_id"):
        op.create_index(
            "ix_opinion_citation_claim_id", "opinion_citation", ["claim_id"]
        )

    if not _table_exists("followup_session"):
        op.create_table(
            "followup_session",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("opinion_id", sa.String, nullable=False, server_default=""),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("client_fingerprint", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("followup_session", "ix_followup_session_expires_at"):
        op.create_index(
            "ix_followup_session_expires_at", "followup_session", ["expires_at"]
        )
    if not _index_exists("followup_session", "ix_followup_session_client_fingerprint"):
        op.create_index(
            "ix_followup_session_client_fingerprint",
            "followup_session",
            ["client_fingerprint"],
        )

    if not _table_exists("followup_message"):
        op.create_table(
            "followup_message",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("session_id", sa.String, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("followup_message", "ix_followup_message_session_id_created_at"):
        op.create_index(
            "ix_followup_message_session_id_created_at",
            "followup_message",
            ["session_id", "created_at"],
        )


def downgrade() -> None:
    # Reverse dependency order: followup_message -> followup_session ->
    # opinion_citation -> event_opinion -> current_event. No cascade.
    for table in (
        "followup_message",
        "followup_session",
        "opinion_citation",
        "event_opinion",
        "current_event",
    ):
        if _table_exists(table):
            op.drop_table(table)
