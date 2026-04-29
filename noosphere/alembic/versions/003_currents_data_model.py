"""Currents data model.

Revision ID: 003_currents_data_model
Revises: 002_round3_foundations
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects import postgresql

revision = "003_currents_data_model"
down_revision = "002_round3_foundations"
branch_labels = None
depends_on = None

CURRENT_EVENT_STATUS = ("OBSERVED", "ENRICHED", "OPINED", "ABSTAINED", "REVOKED")
CURRENT_EVENT_SOURCE = ("X_TWITTER", "RSS", "MANUAL")
OPINION_STANCE = ("AGREES", "DISAGREES", "COMPLICATES", "ABSTAINED")
ABSTENTION_REASON = (
    "INSUFFICIENT_SOURCES",
    "NEAR_DUPLICATE",
    "BUDGET",
    "CITATION_FABRICATION",
    "REVOKED_SOURCES",
)
FOLLOW_UP_ROLE = ("USER", "ASSISTANT")

_TABLES = (
    "FollowUpMessage",
    "FollowUpSession",
    "OpinionCitation",
    "EventOpinion",
    "CurrentEvent",
)
_ENUMS = (
    "FollowUpRole",
    "AbstentionReason",
    "OpinionStance",
    "CurrentEventSource",
    "CurrentEventStatus",
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
    return constraint_name in {fk["name"] for fk in foreign_keys} | {
        uq["name"] for uq in unique_constraints
    }


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


def _bytes_type() -> sa.types.TypeEngine:
    if _is_postgres():
        return postgresql.BYTEA()
    return sa.LargeBinary()


def _text_array_type() -> sa.types.TypeEngine:
    if _is_postgres():
        return postgresql.ARRAY(sa.Text())
    return sa.JSON()


def _create_tables() -> None:
    if not _table_exists("CurrentEvent"):
        op.create_table(
            "CurrentEvent",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column("source", _enum_type("CurrentEventSource", CURRENT_EVENT_SOURCE), nullable=False),
            sa.Column("externalId", sa.Text(), nullable=False),
            sa.Column("authorHandle", sa.Text(), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("capturedAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("observedAt", sa.DateTime(timezone=False), nullable=False),
            sa.Column("topicHint", sa.Text(), nullable=True),
            sa.Column("isNearDuplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("embedding", _bytes_type(), nullable=True),
            sa.Column("status", _enum_type("CurrentEventStatus", CURRENT_EVENT_STATUS), nullable=False, server_default="OBSERVED"),
            sa.Column("dedupeHash", sa.Text(), nullable=False),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("updatedAt", sa.DateTime(timezone=False), nullable=False),
        )

    if not _table_exists("EventOpinion"):
        op.create_table(
            "EventOpinion",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("organizationId", sa.Text(), nullable=False),
            sa.Column("eventId", sa.Text(), nullable=False),
            sa.Column("stance", _enum_type("OpinionStance", OPINION_STANCE), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("headline", sa.String(length=140), nullable=False),
            sa.Column("bodyMarkdown", sa.Text(), nullable=False),
            sa.Column("uncertaintyNotes", _text_array_type(), nullable=True),
            sa.Column("topicHint", sa.Text(), nullable=True),
            sa.Column("modelName", sa.Text(), nullable=False),
            sa.Column("promptTokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completionTokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("abstentionReason", _enum_type("AbstentionReason", ABSTENTION_REASON), nullable=True),
            sa.Column("generatedAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("revokedAt", sa.DateTime(timezone=False), nullable=True),
            sa.Column("revokedReason", sa.Text(), nullable=True),
        )

    if not _table_exists("OpinionCitation"):
        op.create_table(
            "OpinionCitation",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("opinionId", sa.Text(), nullable=False),
            sa.Column("sourceKind", sa.Text(), nullable=False),
            sa.Column("conclusionId", sa.Text(), nullable=True),
            sa.Column("claimId", sa.Text(), nullable=True),
            sa.Column("quotedSpan", sa.Text(), nullable=False),
            sa.Column("retrievalScore", sa.Float(), nullable=False),
            sa.Column("isRevoked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("revokedReason", sa.Text(), nullable=True),
        )

    if not _table_exists("FollowUpSession"):
        op.create_table(
            "FollowUpSession",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("opinionId", sa.Text(), nullable=False),
            sa.Column("clientFingerprint", sa.Text(), nullable=False),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
            sa.Column("lastActivityAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        )

    if not _table_exists("FollowUpMessage"):
        op.create_table(
            "FollowUpMessage",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("sessionId", sa.Text(), nullable=False),
            sa.Column("role", _enum_type("FollowUpRole", FOLLOW_UP_ROLE), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("citations", _json_type(), nullable=True),
            sa.Column("createdAt", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        )


def _create_indexes() -> None:
    if _table_exists("CurrentEvent"):
        if not _index_exists("CurrentEvent", "CurrentEvent_dedupeHash_key"):
            op.create_index("CurrentEvent_dedupeHash_key", "CurrentEvent", ["dedupeHash"], unique=True)
        if not _index_exists("CurrentEvent", "CurrentEvent_organizationId_observedAt_idx"):
            op.create_index("CurrentEvent_organizationId_observedAt_idx", "CurrentEvent", ["organizationId", "observedAt"])
        if not _index_exists("CurrentEvent", "CurrentEvent_organizationId_status_idx"):
            op.create_index("CurrentEvent_organizationId_status_idx", "CurrentEvent", ["organizationId", "status"])

    if _table_exists("EventOpinion"):
        if not _index_exists("EventOpinion", "EventOpinion_organizationId_generatedAt_idx"):
            op.create_index("EventOpinion_organizationId_generatedAt_idx", "EventOpinion", ["organizationId", "generatedAt"])
        if not _index_exists("EventOpinion", "EventOpinion_eventId_idx"):
            op.create_index("EventOpinion_eventId_idx", "EventOpinion", ["eventId"])

    if _table_exists("OpinionCitation"):
        if not _index_exists("OpinionCitation", "OpinionCitation_opinionId_idx"):
            op.create_index("OpinionCitation_opinionId_idx", "OpinionCitation", ["opinionId"])
        if not _index_exists("OpinionCitation", "OpinionCitation_conclusionId_idx"):
            op.create_index("OpinionCitation_conclusionId_idx", "OpinionCitation", ["conclusionId"])
        if not _index_exists("OpinionCitation", "OpinionCitation_claimId_idx"):
            op.create_index("OpinionCitation_claimId_idx", "OpinionCitation", ["claimId"])

    if _table_exists("FollowUpSession"):
        if not _index_exists("FollowUpSession", "FollowUpSession_opinionId_lastActivityAt_idx"):
            op.create_index("FollowUpSession_opinionId_lastActivityAt_idx", "FollowUpSession", ["opinionId", "lastActivityAt"])
        if not _index_exists("FollowUpSession", "FollowUpSession_clientFingerprint_createdAt_idx"):
            op.create_index("FollowUpSession_clientFingerprint_createdAt_idx", "FollowUpSession", ["clientFingerprint", "createdAt"])

    if _table_exists("FollowUpMessage") and not _index_exists("FollowUpMessage", "FollowUpMessage_sessionId_createdAt_idx"):
        op.create_index("FollowUpMessage_sessionId_createdAt_idx", "FollowUpMessage", ["sessionId", "createdAt"])


def _create_foreign_keys() -> None:
    if not _is_postgres():
        return

    if _table_exists("Organization") and _table_exists("CurrentEvent") and not _constraint_exists("CurrentEvent", "CurrentEvent_organizationId_fkey"):
        op.create_foreign_key(
            "CurrentEvent_organizationId_fkey",
            "CurrentEvent",
            "Organization",
            ["organizationId"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        )
    if _table_exists("Organization") and _table_exists("EventOpinion") and not _constraint_exists("EventOpinion", "EventOpinion_organizationId_fkey"):
        op.create_foreign_key(
            "EventOpinion_organizationId_fkey",
            "EventOpinion",
            "Organization",
            ["organizationId"],
            ["id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        )
    if _table_exists("CurrentEvent") and _table_exists("EventOpinion") and not _constraint_exists("EventOpinion", "EventOpinion_eventId_fkey"):
        op.create_foreign_key(
            "EventOpinion_eventId_fkey",
            "EventOpinion",
            "CurrentEvent",
            ["eventId"],
            ["id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        )
    if _table_exists("EventOpinion") and _table_exists("OpinionCitation") and not _constraint_exists("OpinionCitation", "OpinionCitation_opinionId_fkey"):
        op.create_foreign_key(
            "OpinionCitation_opinionId_fkey",
            "OpinionCitation",
            "EventOpinion",
            ["opinionId"],
            ["id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        )
    if _table_exists("EventOpinion") and _table_exists("FollowUpSession") and not _constraint_exists("FollowUpSession", "FollowUpSession_opinionId_fkey"):
        op.create_foreign_key(
            "FollowUpSession_opinionId_fkey",
            "FollowUpSession",
            "EventOpinion",
            ["opinionId"],
            ["id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        )
    if _table_exists("FollowUpSession") and _table_exists("FollowUpMessage") and not _constraint_exists("FollowUpMessage", "FollowUpMessage_sessionId_fkey"):
        op.create_foreign_key(
            "FollowUpMessage_sessionId_fkey",
            "FollowUpMessage",
            "FollowUpSession",
            ["sessionId"],
            ["id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
        )


def upgrade() -> None:
    _create_pg_enum("CurrentEventStatus", CURRENT_EVENT_STATUS)
    _create_pg_enum("CurrentEventSource", CURRENT_EVENT_SOURCE)
    _create_pg_enum("OpinionStance", OPINION_STANCE)
    _create_pg_enum("AbstentionReason", ABSTENTION_REASON)
    _create_pg_enum("FollowUpRole", FOLLOW_UP_ROLE)
    _create_tables()
    _create_indexes()
    _create_foreign_keys()


def downgrade() -> None:
    for table in _TABLES:
        if _table_exists(table):
            op.drop_table(table)
    for enum_name in _ENUMS:
        _drop_pg_enum(enum_name)
