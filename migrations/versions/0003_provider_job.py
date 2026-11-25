"""Background provider jobs (perf-worker).

Revision ID: 0003_provider_job
Revises: 0002_lockin_active_unique
Create Date: 2026-11-25

Same DDL as schema_postgres.sql (init_db creates it too). Additive only.
"""
from alembic import op

revision = '0003_provider_job'
down_revision = '0002_lockin_active_unique'
branch_labels = None
depends_on = None

DDL = (
    '''CREATE TABLE IF NOT EXISTS "ProviderJob" (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, user_id TEXT NOT NULL, ref TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','running','succeeded','failed','dead')),
 attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
 run_after BIGINT NOT NULL, lease_until BIGINT, last_error TEXT,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
)''',
    'CREATE INDEX IF NOT EXISTS idx_provider_job_claim ON "ProviderJob" (state, run_after)',
)


def upgrade() -> None:
    for statement in DDL:
        op.execute(statement)


def downgrade() -> None:
    raise NotImplementedError('Forward-only: write a new migration instead.')
