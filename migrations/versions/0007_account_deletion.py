"""Account deletion (feat-delete): Account.deletion_requested_at / deletion_due_at + DeletionRecord.

Revision ID: 0007_account_deletion
Revises: 0006_member_lock
Create Date: 2026-11-25
"""
from alembic import op

revision = '0007_account_deletion'
down_revision = '0006_member_lock'
branch_labels = None
depends_on = None

RECORD = """CREATE TABLE IF NOT EXISTS "DeletionRecord" (
    id               TEXT PRIMARY KEY,
    purged_at        BIGINT NOT NULL,
    rows_deleted     INTEGER NOT NULL,
    rows_anonymised  INTEGER NOT NULL
)"""


def upgrade() -> None:
    op.execute('ALTER TABLE "Account" ADD COLUMN IF NOT EXISTS deletion_requested_at BIGINT')
    op.execute('ALTER TABLE "Account" ADD COLUMN IF NOT EXISTS deletion_due_at BIGINT')
    op.execute(RECORD)


def downgrade() -> None:
    raise NotImplementedError('Forward-only: write a new migration instead.')
