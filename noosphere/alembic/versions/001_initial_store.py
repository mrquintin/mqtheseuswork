"""initial store tables

Revision ID: 001_initial
Revises:
Create Date: 2026-04-14
"""

from alembic import op
from sqlmodel import SQLModel

import noosphere.store  # noqa: F401

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind=bind)
