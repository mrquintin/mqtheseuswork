"""fixture branch A — both 002 and 003 (intentionally) point at 001_base

Revision ID: 002_branch_a
Revises: 001_base
Create Date: 2026-01-02
"""

revision = "002_branch_a"
down_revision = "001_base"
branch_labels = None
depends_on = None


def upgrade() -> None: ...


def downgrade() -> None: ...
