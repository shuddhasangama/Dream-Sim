"""Security events (sec-session).

Revision ID: 0004_security_event
Revises: 0003_provider_job
Create Date: 2026-11-25
"""
from alembic import op

revision = '0004_security_event'
down_revision = '0003_provider_job'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('''CREATE TABLE IF NOT EXISTS "SecurityEvent" (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT, created_at BIGINT NOT NULL
)''')
    op.execute('CREATE INDEX IF NOT EXISTS idx_security_event_user ON "SecurityEvent" (user_id, created_at)')


def downgrade() -> None:
    raise NotImplementedError('Forward-only: write a new migration instead.')
