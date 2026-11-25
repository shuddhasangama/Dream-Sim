"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Hand-written SQL only. Every migration must be safe to run on the live
database: additive first (nullable columns, new tables, CREATE INDEX
CONCURRENTLY in its own revision), destructive changes only after the code
that stopped using the old shape is deployed. Update schema_postgres.sql and
schema.sql in the same commit.
"""
from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "raise NotImplementedError('Write a forward fix instead of downgrading production.')"}
