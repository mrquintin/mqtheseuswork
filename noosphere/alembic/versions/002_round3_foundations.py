"""Round 3 foundations: methods, ledger, cascade, evaluation, battery,
review, decay, rigor, MIP tables.

Revision ID: 002_round3_foundations
Revises: 001_initial
Create Date: 2026-04-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "002_round3_foundations"
down_revision = "001_initial"
branch_labels = None
depends_on = None

_NEW_TABLES = [
    "method",
    "method_invocation",
    "ledger_entry",
    "cascade_node",
    "cascade_edge",
    "temporal_cut",
    "outcome",
    "cut_outcome",
    "counterfactual_eval_run",
    "external_bundle",
    "battery_run",
    "transfer_study",
    "review_report",
    "rebuttal",
    "decay_policy",
    "object_policy_binding",
    "revalidation",
    "rigor_submission",
    "rigor_verdict",
    "founder_override",
    "mip_manifest",
]


def _table_exists(name: str) -> bool:
    return name in set(sa_inspect(op.get_bind()).get_table_names())


def _index_exists(table: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in sa_inspect(op.get_bind()).get_indexes(table)}


def _col_exists(table: str, col: str) -> bool:
    return col in {c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _table_exists("method"):
        op.create_table(
            "method",
            sa.Column("method_id", sa.String, primary_key=True),
            sa.Column("status", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("method", "ix_method_status"):
        op.create_index("ix_method_status", "method", ["status"])

    if not _table_exists("method_invocation"):
        op.create_table(
            "method_invocation",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("method_id", sa.String, nullable=False, server_default=""),
            sa.Column("correlation_id", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("method_invocation", "ix_method_invocation_method_id"):
        op.create_index("ix_method_invocation_method_id", "method_invocation", ["method_id"])
    if not _index_exists("method_invocation", "ix_method_invocation_correlation_id"):
        op.create_index("ix_method_invocation_correlation_id", "method_invocation", ["correlation_id"])

    if not _table_exists("ledger_entry"):
        op.create_table(
            "ledger_entry",
            sa.Column("entry_id", sa.String, primary_key=True),
            sa.Column("prev_hash", sa.String, nullable=False, server_default=""),
            sa.Column("method_id", sa.String, nullable=True),
            sa.Column("timestamp", sa.DateTime, nullable=False),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("ledger_entry", "ix_ledger_entry_prev_hash"):
        op.create_index("ix_ledger_entry_prev_hash", "ledger_entry", ["prev_hash"])
    if not _index_exists("ledger_entry", "ix_ledger_entry_method_id"):
        op.create_index("ix_ledger_entry_method_id", "ledger_entry", ["method_id"])
    if not _index_exists("ledger_entry", "ix_ledger_entry_timestamp"):
        op.create_index("ix_ledger_entry_timestamp", "ledger_entry", ["timestamp"])

    if not _table_exists("cascade_node"):
        op.create_table(
            "cascade_node",
            sa.Column("node_id", sa.String, primary_key=True),
            sa.Column("kind", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("cascade_node", "ix_cascade_node_kind"):
        op.create_index("ix_cascade_node_kind", "cascade_node", ["kind"])

    if not _table_exists("cascade_edge"):
        op.create_table(
            "cascade_edge",
            sa.Column("edge_id", sa.String, primary_key=True),
            sa.Column("src", sa.String, nullable=False, server_default=""),
            sa.Column("dst", sa.String, nullable=False, server_default=""),
            sa.Column("relation", sa.String, nullable=False, server_default=""),
            sa.Column("method_invocation_id", sa.String, nullable=False, server_default=""),
            sa.Column("retracted_at", sa.DateTime, nullable=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("cascade_edge", "ix_cascade_edge_src"):
        op.create_index("ix_cascade_edge_src", "cascade_edge", ["src"])
    if not _index_exists("cascade_edge", "ix_cascade_edge_dst"):
        op.create_index("ix_cascade_edge_dst", "cascade_edge", ["dst"])
    if not _index_exists("cascade_edge", "ix_cascade_edge_relation"):
        op.create_index("ix_cascade_edge_relation", "cascade_edge", ["relation"])
    if not _index_exists("cascade_edge", "ix_cascade_edge_retracted_at"):
        op.create_index("ix_cascade_edge_retracted_at", "cascade_edge", ["retracted_at"])

    if not _table_exists("temporal_cut"):
        op.create_table(
            "temporal_cut",
            sa.Column("cut_id", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    if not _table_exists("outcome"):
        op.create_table(
            "outcome",
            sa.Column("outcome_id", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    if not _table_exists("cut_outcome"):
        op.create_table(
            "cut_outcome",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("cut_id", sa.String, nullable=False, server_default=""),
            sa.Column("outcome_id", sa.String, nullable=False, server_default=""),
        )
    if not _index_exists("cut_outcome", "ix_cut_outcome_cut_id"):
        op.create_index("ix_cut_outcome_cut_id", "cut_outcome", ["cut_id"])
    if not _index_exists("cut_outcome", "ix_cut_outcome_outcome_id"):
        op.create_index("ix_cut_outcome_outcome_id", "cut_outcome", ["outcome_id"])

    if not _table_exists("counterfactual_eval_run"):
        op.create_table(
            "counterfactual_eval_run",
            sa.Column("run_id", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    if not _table_exists("external_bundle"):
        op.create_table(
            "external_bundle",
            sa.Column("content_hash", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    if not _table_exists("battery_run"):
        op.create_table(
            "battery_run",
            sa.Column("run_id", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    if not _table_exists("transfer_study"):
        op.create_table(
            "transfer_study",
            sa.Column("study_id", sa.String, primary_key=True),
            sa.Column("method_ref_name", sa.String, nullable=False, server_default=""),
            sa.Column("method_ref_version", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("transfer_study", "ix_transfer_study_method_ref_name"):
        op.create_index("ix_transfer_study_method_ref_name", "transfer_study", ["method_ref_name"])
    if not _index_exists("transfer_study", "ix_transfer_study_method_ref_version"):
        op.create_index("ix_transfer_study_method_ref_version", "transfer_study", ["method_ref_version"])

    if not _table_exists("review_report"):
        op.create_table(
            "review_report",
            sa.Column("report_id", sa.String, primary_key=True),
            sa.Column("conclusion_id", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("review_report", "ix_review_report_conclusion_id"):
        op.create_index("ix_review_report_conclusion_id", "review_report", ["conclusion_id"])

    if not _table_exists("rebuttal"):
        op.create_table(
            "rebuttal",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("report_id", sa.String, nullable=False, server_default=""),
            sa.Column("finding_id", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("rebuttal", "ix_rebuttal_report_id"):
        op.create_index("ix_rebuttal_report_id", "rebuttal", ["report_id"])
    if not _index_exists("rebuttal", "ix_rebuttal_finding_id"):
        op.create_index("ix_rebuttal_finding_id", "rebuttal", ["finding_id"])

    if not _table_exists("decay_policy"):
        op.create_table(
            "decay_policy",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    if not _table_exists("object_policy_binding"):
        op.create_table(
            "object_policy_binding",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("object_id", sa.String, nullable=False, server_default=""),
            sa.Column("policy_id", sa.String, nullable=False, server_default=""),
        )
    if not _index_exists("object_policy_binding", "ix_object_policy_binding_object_id"):
        op.create_index("ix_object_policy_binding_object_id", "object_policy_binding", ["object_id"])
    if not _index_exists("object_policy_binding", "ix_object_policy_binding_policy_id"):
        op.create_index("ix_object_policy_binding_policy_id", "object_policy_binding", ["policy_id"])

    if not _table_exists("revalidation"):
        op.create_table(
            "revalidation",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("object_id", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("revalidation", "ix_revalidation_object_id"):
        op.create_index("ix_revalidation_object_id", "revalidation", ["object_id"])

    if not _table_exists("rigor_submission"):
        op.create_table(
            "rigor_submission",
            sa.Column("submission_id", sa.String, primary_key=True),
            sa.Column("author_id", sa.String, nullable=False, server_default=""),
            sa.Column("intended_venue", sa.String, nullable=False, server_default=""),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )
    if not _index_exists("rigor_submission", "ix_rigor_submission_author_id"):
        op.create_index("ix_rigor_submission_author_id", "rigor_submission", ["author_id"])
    if not _index_exists("rigor_submission", "ix_rigor_submission_intended_venue"):
        op.create_index("ix_rigor_submission_intended_venue", "rigor_submission", ["intended_venue"])

    if not _table_exists("rigor_verdict"):
        op.create_table(
            "rigor_verdict",
            sa.Column("ledger_entry_id", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    if not _table_exists("founder_override"):
        op.create_table(
            "founder_override",
            sa.Column("override_id", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    if not _table_exists("mip_manifest"):
        op.create_table(
            "mip_manifest",
            sa.Column("content_hash", sa.String, primary_key=True),
            sa.Column("payload_json", sa.Text, nullable=False, server_default=""),
        )

    for table in ("conclusion", "claim", "topic_cluster"):
        if not _col_exists(table, "freshness"):
            op.add_column(table, sa.Column("freshness", sa.String, server_default="fresh"))
        if not _col_exists(table, "last_validated_at"):
            op.add_column(table, sa.Column("last_validated_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    for table in ("conclusion", "claim", "topic_cluster"):
        if _col_exists(table, "last_validated_at"):
            op.drop_column(table, "last_validated_at")
        if _col_exists(table, "freshness"):
            op.drop_column(table, "freshness")

    for table in reversed(_NEW_TABLES):
        if _table_exists(table):
            op.drop_table(table)
