"""Account.phone_index blind index (sec-enc).

Revision ID: 0005_account_phone_index
Revises: 0004_security_event
Create Date: 2026-11-25
"""
from alembic import op

revision = '0005_account_phone_index'
down_revision = '0004_security_event'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE "Account" ADD COLUMN IF NOT EXISTS phone_index TEXT')
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_account_phone_index ON "Account" (phone_index)')


def downgrade() -> None:
    raise NotImplementedError('Forward-only: write a new migration instead.')
