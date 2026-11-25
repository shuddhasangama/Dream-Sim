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

## Targets and expected peak (c-scale-budget)

| Target | Value |
|---|---|
| p95 latency, normal API calls | < 500 ms |
| Error rate (5xx) | < 0.5% |
| Members | 1,500 |
| Expected peak concurrently active | ~15% of members = **225** in the evening peak |
| Expected peak load | 225 active × ~1 request / 4 s (app polling + navigation) ≈ **55–60 requests/s** |
| Budget per replica (recommended 2 × 2 workers × 4 threads) | ≥ 30 requests/s each, p95 < 500 ms |

## Local smoke load (2026-11-25)

**Setup:**
- Laptop (Windows, 12 GB RAM).
- One waitress process with 8 threads (stands in for one gunicorn worker), against `dhashu_load` on localhost:5433 with 1,600 synthetic members.
- Pool max 10, `DHASHU_GZIP=1`.
- Locust: 60 members, 2 minutes, weighted journeys (`tools/load_test/locustfile.py`).

| Endpoint | Requests | p50 | p95 | p99 |
|---|---|---|---|---|
| home: profile | 896 | 9 ms | 330 ms | 770 ms |
| home: journey/status | 896 | 130 ms | 590 ms | 1,400 ms |
| profile/stats | 299 | 130 ms | 580 ms | 1,400 ms |
| week | 529 | 150 ms | 670 ms | 1,400 ms |
| guru | 155 | 110 ms | 660 ms | 1,300 ms |
| session refresh | 150 | 120 ms | 690 ms | 1,500 ms |
| **reach** | 480 | **480 ms** | **1,200 ms** | 2,000 ms |
| **all** | 3,465 | 120 ms | 790 ms | 1,400 ms |

Throughput was **29 requests/s**, with **0 server errors**. The 201 `week` 403s are expected "not eligible this week" answers for some synthetic members, not errors.

**Reading:**
- **Where the time goes.** No endpoint has an N+1 query problem: query counts per request are constant as members grow. The time is CPU in one Python process (the GIL). REACH and journey status rebuild the full matching pool from all members on every request.
- **How the production layout helps.** The recommended layout (2 replicas × 2 workers × 4 threads) gives roughly 4× the parallel CPU of this single process.
- **REACH still needs a cache.** It will exceed 500 ms at p95 until its pool computation is cached. That is the `perf-pagecache` task, recorded for its owners with these numbers.

## Staging run plan (1,500 members), manual

Never against production.

1. **Staging environment.** Create a separate Railway environment named `staging`, with its own Postgres. Copy no production data.
2. **Deploy.** Deploy `dev/saravanan` there, with `WEB_CONCURRENCY=2`, `GUNICORN_THREADS=4`, pool max 8, 2 replicas, and providers disabled or sandboxed exactly as locally.
3. **Seed.** Run `tools/load_test/seed_load_db.py` from a staging console. It only accepts `_load` database names on localhost, so first adapt it with a staging-only `--target` guard (a reviewed follow-up), or seed through an admin import.
4. **Sign-in for load users.** Staging needs a staging-only sign-in for synthetic users. The local harness refuses to start on Railway by design, so add a staging-only variant behind its own setting that can't be set in production, or pre-issue tokens through an admin script.
5. **Run Locust** from a separate machine: `-u 225 -r 15 -t 20m --host https://<staging-host>`, then a 2× spike (`-u 450`) for 5 minutes.
6. **Pass criteria:** p95 < 500 ms for every endpoint except REACH until it's cached; 5xx < 0.5%; no pool timeouts; Postgres connections within the budget; CPU < 75%.
7. **Record:** the Locust CSVs, Railway metrics (CPU, memory, connections) and the slowest queries (`pg_stat_statements` is available on staging Postgres).

## Guru AI replies on the worker (perf-worker, `DHASHU_ASYNC_GURU`)

Default `0`: the web request calls OpenAI itself (unchanged). With `DHASHU_ASYNC_GURU=1`:
- `POST /api/v1/guru/private {action:'message'}` reserves the reply and enqueues one
  `guru_reply` job (idempotent per request id) and returns `pending_job`.
- The worker (`bgv_worker`) calls OpenAI through the `openai` circuit breaker, with no
  database transaction held, and writes the answer only if the reply is still pending.
- The app shows "Guru is thinking…", polls the owner-only `GET /api/v1/jobs/<id>`, and
  after 25 s asks `settle_pending`, which answers in guided mode; a late job then does
  nothing. A dead job (2 attempts) also answers in guided mode.
- Job rows hold only an opaque token: the message stays in the encrypted Guru store.
Turn it on only when the worker service is running with the same OpenAI settings.
