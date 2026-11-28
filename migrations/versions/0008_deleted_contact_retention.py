"""Deleted-contact retention (client answer 7): after the purge, a keyed hash of the
member's phone (or email) and the exit type, kept for DHASHU_DELETED_RETENTION_DAYS.

Revision ID: 0008_deleted_contact_retention
Revises: 0007_account_deletion
Create Date: 2026-11-28
"""
from alembic import op

revision = '0008_deleted_contact_retention'
down_revision = '0007_account_deletion'
branch_labels = None
depends_on = None

TABLE = """CREATE TABLE IF NOT EXISTS "DeletedContactRetention" (
    id             TEXT PRIMARY KEY,
    contact_kind   TEXT NOT NULL CHECK (contact_kind IN ('phone', 'email')),
    contact_index  TEXT NOT NULL,
    index_key      TEXT NOT NULL,
    exit_type      TEXT NOT NULL CHECK (exit_type IN ('good_exit', 'bad_exit')),
    purged_at      BIGINT NOT NULL,
    delete_after   BIGINT NOT NULL
)"""


def upgrade() -> None:
    op.execute(TABLE)
    op.execute('CREATE INDEX IF NOT EXISTS idx_deleted_contact_index ON "DeletedContactRetention" (contact_index)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_deleted_contact_expiry ON "DeletedContactRetention" (delete_after)')


def downgrade() -> None:
    raise NotImplementedError('Forward-only: write a new migration instead.')
