"""One active lock-in per member per position (perf-rowlock).

Revision ID: 0002_lockin_active_unique
Revises: 0001_baseline
Create Date: 2026-11-25

Matches db.PARTIAL_UNIQUE_INDEXES (init_db applies the same indexes). If the
live table already holds two active lock-ins for one member this fails and must
be resolved by a person first (db.enforce_unique_indexes reports it instead).
"""
from alembic import op

revision = '0002_lockin_active_unique'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_lockin_active_user_a ON "LockIn" (user_a) WHERE status = \'active\'')
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_lockin_active_user_b ON "LockIn" (user_b) WHERE status = \'active\'')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS uq_lockin_active_user_a')
    op.execute('DROP INDEX IF EXISTS uq_lockin_active_user_b')
