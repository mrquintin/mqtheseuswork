"""fixture branch B — also points at 001_base, creating a fork.

Revision ID: 003_branch_b
Revises: 001_base
Create Date: 2026-01-03
"""

revision = "003_branch_b"
down_revision = "001_base"
branch_labels = None
depends_on = None


def upgrade() -> None: ...


def downgrade() -> None: ...
