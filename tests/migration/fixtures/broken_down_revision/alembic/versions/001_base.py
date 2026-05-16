"""fixture base revision

Revision ID: 001_base
Revises:
Create Date: 2026-01-01
"""

revision = "001_base"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None: ...


def downgrade() -> None: ...
