# Scaling: processes, threads and the database connection budget

Targets: p95 < 500 ms for normal API calls, error rate < 0.5%, 1,500 members.

## Web server (perf-threads)

`service_entrypoint.py` builds the gunicorn command for the web role from settings. **With no settings it starts exactly as before** (`gunicorn app:app`, which means gunicorn's own defaults). A Linux CI test compares these values with gunicorn's built-in defaults.

| Setting | Default (= today) | Recommended for launch | Meaning |
|---|---|---|---|
| `WEB_CONCURRENCY` | 1 | 2 | Worker processes per replica |
| `GUNICORN_THREADS` | 1 (sync worker) | 4 (gthread) | Threads per process. Above 1, the worker class becomes `gthread`. |
| `GUNICORN_TIMEOUT` | 30 | 30 | A request taking longer kills its worker. No normal API call should come near this; slow provider work moves to the BGV worker (perf-worker). |
| `GUNICORN_GRACEFUL_TIMEOUT` | 30 | 30 | Time in-flight requests get to finish on restart or deploy |
| `GUNICORN_KEEPALIVE` | 2 | 5 | Seconds an idle keep-alive connection stays open (behind Railway's proxy) |
| `GUNICORN_MAX_REQUESTS` | 0 (off) | 2000 | Recycle a worker after N requests (guards against slow memory growth) |
| `GUNICORN_MAX_REQUESTS_JITTER` | 10% of max | 200 | Spreads recycling so workers don't restart together |

Concurrency per replica = `WEB_CONCURRENCY × GUNICORN_THREADS` (recommended: 2 × 4 = 8 requests in flight).

## Database connections (perf-pool)

Each process keeps its own pool (`db.acquire()`/`db.release()`):

| Setting | Default | Meaning |
|---|---|---|
| `DHASHU_DB_POOL` | 1 | Pool PostgreSQL connections (`0` = one connection per request, the old behaviour) |
| `DHASHU_DB_POOL_MIN` | 1 | Connections kept open per process |
| `DHASHU_DB_POOL_MAX` | 10 | Hard cap per process. It must be at least `GUNICORN_THREADS` + 2, for the background activity writes and error recording. |
| `DHASHU_DB_POOL_TIMEOUT` | 5 s | Wait for a free connection, then fail fast (a clear error, never a hang) |

## The connection budget

PostgreSQL refuses connections above `max_connections`, which is 100 on a default Railway Postgres. Every process can open up to its pool max, so:

```
web:    replicas × WEB_CONCURRENCY × DHASHU_DB_POOL_MAX
worker: worker replicas × (DHASHU_DB_POOL_MAX of the worker service)
admin:  admin gunicorn workers (2) × 1 (no pool; one connection per request)
spare:  10 (console, migrations, backups, monitoring)

total must stay below max_connections (100), with at least 20% headroom
```

**Recommended launch configuration (1,500 members):**

| Service | Replicas | Workers | Threads | Pool max | Connections |
|---|---|---|---|---|---|
| web | 2 | 2 | 4 | 8 | 2 × 2 × 8 = **32** |
| bgv-worker | 1 | 1 | (2 loops) | 4 | **4** |
| admin | 1 | 2 | 1 | — | **2** |
| spare | | | | | **10** |
| **total** | | | | | **48 of 100** (52% headroom) |

Change one number at a time and re-check the total. Doubling web replicas to 4 gives 64 + 16 = 80, which is still under 100 but with little headroom. Beyond that, put a connection pooler in front of Postgres (PgBouncer, transaction mode) before adding replicas.

## Manual steps (Railway; after merge to master + deploy)

Apply after the staging load run (see c-scale-budget) confirms the numbers:

1. Railway → project → **web** service → Variables: `WEB_CONCURRENCY=2`, `GUNICORN_THREADS=4`, `GUNICORN_KEEPALIVE=5`, `GUNICORN_MAX_REQUESTS=2000`, `GUNICORN_MAX_REQUESTS_JITTER=200`, `DHASHU_DB_POOL_MAX=8`.
2. **bgv-worker** service → Variables: `DHASHU_DB_POOL_MAX=4`.
3. web service → Settings → Scaling → **Replicas = 2**.
4. Postgres service → check `SHOW max_connections;` in its console matches the budget above.
