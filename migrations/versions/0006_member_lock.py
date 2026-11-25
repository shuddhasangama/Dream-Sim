"""Member lock (feat-lock): Account.locked_at / lock_reason + MemberLockEvent.

Revision ID: 0006_member_lock
Revises: 0005_account_phone_index
Create Date: 2026-11-25
"""
from alembic import op

revision = '0006_member_lock'
down_revision = '0005_account_phone_index'
branch_labels = None
depends_on = None

EVENT_TABLE = """CREATE TABLE IF NOT EXISTS "MemberLockEvent" (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('lock', 'unlock')),
    reason      TEXT NOT NULL,
    admin_id    TEXT NOT NULL,
    created_at  BIGINT NOT NULL
)"""


def upgrade() -> None:
    op.execute('ALTER TABLE "Account" ADD COLUMN IF NOT EXISTS locked_at BIGINT')
    op.execute('ALTER TABLE "Account" ADD COLUMN IF NOT EXISTS lock_reason TEXT')
    op.execute(EVENT_TABLE)
    op.execute('CREATE INDEX IF NOT EXISTS idx_member_lock_event_user ON "MemberLockEvent" (user_id, created_at)')


def downgrade() -> None:
    raise NotImplementedError('Forward-only: write a new migration instead.')
