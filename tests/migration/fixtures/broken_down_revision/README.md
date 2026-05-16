Synthetic Alembic versions directory containing a branch: two revisions
both name `001_base` as their `down_revision`. `check_alembic_linearity`
should report a `BRANCH` violation.
