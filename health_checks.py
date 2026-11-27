"""Readiness checks (mon-health). Liveness stays /api/v1/health (no database)."""
import logging
import os

log = logging.getLogger('dhashu.health')


def database_ready(timeout_ms=None):
    """True when the database answers SELECT 1 within the timeout (default 2 s,
    DHASHU_READY_TIMEOUT_MS). Never raises; never exposes error details."""
    import db
    timeout_ms = int(timeout_ms or os.environ.get('DHASHU_READY_TIMEOUT_MS', '2000'))
    conn = None
    try:
        conn = db.acquire()
        if db._is_postgres_connection(conn):
            with conn.cursor() as cur:
                # SET cannot take a bind parameter (psycopg 3 binds server-side); set_config
                # with is_local=true is the parameterised, transaction-local equivalent.
                cur.execute("SELECT set_config('statement_timeout', %s, true)", (str(timeout_ms),))
                cur.execute('SELECT 1')
                cur.fetchone()
            conn.rollback()
        else:
            conn.execute('SELECT 1').fetchone()
        return True
    except Exception as exc:   # noqa: BLE001 — readiness must answer, not crash
        log.warning('Readiness check failed: %s', type(exc).__name__)
        return False
    finally:
        db.release(conn)
