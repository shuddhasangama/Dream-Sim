# Database migrations (Alembic)

PostgreSQL only. The app still creates its schema with `db.init_db()` (`schema_postgres.sql`, idempotent). Alembic is added so that, once adopted, every schema change goes through a reviewed, versioned migration instead of on-the-fly column reconciliation.

## What exists

| File | Purpose |
|---|---|
| `alembic.ini` | Config. No database URL is stored. |
| `migrations/env.py` | Reads `DATABASE_URL` (PostgreSQL only; psycopg 3). Offline mode (`--sql`) prints SQL without connecting. |
| `migrations/versions/0001_baseline.py` | Baseline revision. It applies **frozen copies** of the schema as of 2026-11-25 (`0001_baseline_app.sql`, `0001_baseline_admin.sql`) plus the unique contact indexes. Every statement is `IF NOT EXISTS`. |
| `migrations/script.py.mako` | Template for new revisions: hand-written SQL, forward-only. |

**Proved by tests** (`test_migrations.py`):
- A database built by `alembic upgrade head` has exactly the same columns, defaults and indexes as one built by `db.init_db()` + the admin schema.
- `alembic stamp` adopts an existing database without running DDL.
- Upgrading again is a no-op.
- The dry run creates nothing.

## Local use (dhashu_local only)

```powershell
.\dev-local.ps1 migrate          # DRY RUN: prints the SQL, changes nothing
.\dev-local.ps1 migrate -Apply   # applies to dhashu_local (guarded: localhost:5433/dhashu_local only)
```

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `DHASHU_SCHEMA_RECONCILE` | `1` | `init_db()` keeps adding missing columns from `schema_postgres.sql` (today's behaviour). Set it to `0` **after** Alembic is adopted, so the schema only changes through migrations. |
| `DHASHU_SCHEMA_INIT` | `once` | perf-init: schema DDL once per process (`startup` / `per_request` available). |
| `DHASHU_INIT_DB_ON_START` | `1` | Web role runs `init_db()` once before gunicorn starts. |

## Adoption in production (manual, after merge to master + deploy)

Do this once, in a maintenance window, with a fresh database backup:

1. Confirm the deployed code is the commit that contains `migrations/`.
2. Open the Railway service console for the **web** service (not a local machine) and run:
   ```bash
   cd /app && /app/.venv/bin/python -m alembic current      # expect: nothing (not adopted yet)
   cd /app && /app/.venv/bin/python -m alembic stamp 0001_baseline
   cd /app && /app/.venv/bin/python -m alembic current      # expect: 0001_baseline (head)
   ```
   `stamp` only records the version; it runs no DDL against the live tables.
3. In the Railway web service settings, set the **pre-deploy command** to:
   ```bash
   python -m alembic upgrade head
   ```
4. After one successful deploy with the pre-deploy command, set `DHASHU_SCHEMA_RECONCILE=0` on the web and worker services.

## Writing a migration (after adoption)

1. `.venv\Scripts\python.exe -m alembic revision -m "short description"`.
2. Write forward-only SQL in `upgrade()`, safe on the live database:
   - Add **nullable** columns, or columns with a constant default.
   - Use `CREATE INDEX CONCURRENTLY` in its own revision (`op.execute` outside a transaction block).
   - Never drop or rename in the same deploy that stops using the old shape.
3. Update `schema_postgres.sql` **and** `schema.sql` in the same commit (local SQLite and `init_db()` still use them).
4. Check it with `.\dev-local.ps1 migrate` (dry run) and `-Apply` on `dhashu_local`, then run the full test suite.

## Rollback

Migrations are forward-only. To undo a change, write a new migration that reverses it. Restore from backup only for data loss.
