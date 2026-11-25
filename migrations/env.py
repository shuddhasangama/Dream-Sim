"""Alembic environment: PostgreSQL via psycopg 3, URL from DATABASE_URL only.

No model metadata (the app uses plain SQL), so revisions are hand-written SQL.
Offline mode (`alembic upgrade head --sql`) prints the SQL without connecting:
that is the dry run used by `dev-local.ps1 migrate`.
"""
import os

from alembic import context
from sqlalchemy import create_engine, pool


def database_url() -> str:
    raw = os.environ.get('DATABASE_URL', '')
    if not raw.startswith(('postgres://', 'postgresql://')):
        raise RuntimeError('Alembic migrations need a PostgreSQL DATABASE_URL.')
    return 'postgresql+psycopg://' + raw.split('://', 1)[1]


def run_offline() -> None:
    context.configure(url=database_url(), literal_binds=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, transaction_per_migration=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
