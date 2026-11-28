"""Store reviewer account (client answer 9): Account.reviewer.

Revision ID: 0009_account_reviewer
Revises: 0008_deleted_contact_retention
Create Date: 2026-11-28
"""
from alembic import op

revision = '0009_account_reviewer'
down_revision = '0008_deleted_contact_retention'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE "Account" ADD COLUMN IF NOT EXISTS reviewer INTEGER NOT NULL DEFAULT 0')


def downgrade() -> None:
    raise NotImplementedError('Forward-only: write a new migration instead.')
