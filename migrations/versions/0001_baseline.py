"""Baseline: the schema as of 2026-11-25 (schema_postgres.sql + admin_dashboard/schema.sql).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-25

Frozen copies of both schema files sit next to this file, so later edits to
the live schema files never change what the baseline creates. Every statement
is CREATE ... IF NOT EXISTS, so upgrading a fresh database builds the full
schema and running it on a database that already has the schema is harmless.

For the existing production database the adoption step is
`alembic stamp 0001_baseline` (records the baseline without running it); see
docs/MIGRATIONS.md. Unique contact indexes match db.enforce_unique_indexes().
"""
from pathlib import Path

from alembic import context, op

revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None

HERE = Path(__file__).resolve().parent
APP_SQL = HERE / '0001_baseline_app.sql'
ADMIN_SQL = HERE / '0001_baseline_admin.sql'
UNIQUE_INDEXES = (
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_account_email ON "Account" (email)',
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_account_phone ON "Account" (phone)',
)


def _run(sql: str) -> None:
    """Online: raw psycopg cursor, no parameters (exactly like db.init_db), so no
    SQL text is reinterpreted. Offline (--sql dry run): only printed."""
    if context.is_offline_mode():
        op.execute(sql)
        return
    with op.get_bind().connection.driver_connection.cursor() as cursor:
        cursor.execute(sql)


def upgrade() -> None:
    _run(APP_SQL.read_text(encoding='utf-8'))
    for statement in ADMIN_SQL.read_text(encoding='utf-8-sig').split(';'):
        if statement.strip():
            _run(statement)
    for statement in UNIQUE_INDEXES:
        _run(statement)


def downgrade() -> None:
    raise NotImplementedError('The baseline cannot be downgraded; it would drop every table.')
