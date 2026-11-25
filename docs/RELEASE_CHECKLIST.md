# Release checklist

Use this for every release of the backend (Railway) and of the mobile app (stores). Tick each line in the release ticket. Anything marked **owner** needs Saravanan's sign-off. Nothing in this repository deploys by itself; CI never deploys.

## 1. Before merging to master

- [ ] The feature branch is merged into `dev/saravanan` (or the release branch), and **CI is green** on that merge commit. All jobs must pass:
  - Python (SQLite + PostgreSQL 16)
  - Mobile unit tests
  - Playwright preview
  - Playwright backend journey
  - Security scans: pip-audit, npm audit, bandit, semgrep, gitleaks, OpenAPI `--check`
- [ ] Local full run on the release candidate: `.\dev-local.ps1 test` gives 0 failed, and `npm test` in `mobile/` gives 0 failed.
- [ ] `python tools/gen_openapi_schemas.py --check` and `python tools/route_inventory.py --check` are both up to date.
- [ ] Every new route appears in `docs/ROUTE_INVENTORY.md` with the right access class. A new **public** route needs an owner review.
- [ ] `docs/RESPONSE_PERSONAL_FIELDS.json` only changed with an owner review.
- [ ] Migrations:
  - New Alembic revisions are forward-only.
  - `alembic upgrade head --sql` was reviewed.
  - A dry run against a copy of production data was done (`docs/MIGRATIONS.md`).
- [ ] No secrets in the diff (gitleaks green). No `.env*`, keys or certificates.
- [ ] The release notes list every new setting, with its default, and say what changes at deploy versus later when a flag is flipped.
- [ ] **owner:** the PR to master is approved by someone other than its author (branch protection).

## 2. Backend deploy (Railway)

- [ ] A database backup has been taken and the restore has been tested in the last 30 days (perf-backup).
- [ ] New settings are set on the right services (web, worker, admin) **before** the code that reads them is deployed:
  - Encryption keys go in sealed variables (`docs/KEY_MANAGEMENT.md`).
  - Never print a value in chat or tickets.
- [ ] Pre-deploy command: `alembic upgrade head` (once Alembic is adopted). Until then, the schema reconciles on startup.
- [ ] Health check path is `/api/v1/ready`.
- [ ] Deploy the web service, then the worker, then admin. Watch Sentry and the request log for 15 minutes:
  - The 5xx rate must not rise.
  - p95 latency must stay within 20 % of the last release.
  - No `circuit_open`, `otp_global_breaker`, `abuse_spike` or `response_trimmed` events that weren't expected.
- [ ] Smoke test against production with the owner's own test account only:
  1. Sign in.
  2. Check that `/api/v1/me` and the dashboard load.
  3. Sign out.
  4. Check that the admin dashboard login works.
- [ ] Rollback is ready: Railway "redeploy previous". Settings added for this release are harmless to the old code. Migrations are forward-only, so never downgrade; ship a fix instead.

## 3. Mobile release (stores)

- [ ] The release build is made by Codemagic from master with `VITE_API_BASE_URL` set. The release guard refuses missing, HTTP or non-approved origins.
- [ ] `VITE_SENTRY_DSN` is set for store builds.
- [ ] The bundle check shows no `console.` calls from app code and no `DHASHU_*` values except the 3 passed-through settings.
- [ ] Version code and name are bumped. Signing material is from the store keychain, **never** from git (sec-apple).
- [ ] Internal testing track and TestFlight: run the manual journey on a real device.
  1. Sign up with an Indian number.
  2. Sign in with a password.
  3. Background the app for more than 15 minutes and resume. It should check the session before showing Home (feat-resume).
  4. Lock the account from the admin dashboard. The app should send the member to sign-in with the "locked" message.
- [ ] After the new app build is live in both stores, consider setting `DHASHU_VALIDATION_STATUS=422`.

## 4. Flags to change only after their prerequisites

| Setting | Prerequisite |
|---|---|
| `DHASHU_CSP_MODE=enforce` | A week of report-only with no unexpected violations |
| `DHASHU_TRUSTED_PROXY=cloudflare` | The API is served only through Cloudflare |
| `DHASHU_ABUSE_LIMITS=1` | `DHASHU_TRUSTED_PROXY` is set, and Adithya's sec-ip is merged |
| `DHASHU_FIELD_ENCRYPTION=1` | Keys set and backed up, then `tools/encrypt_member_fields.py --apply` |
| `DHASHU_SCHEMA_RECONCILE=0` | Alembic adopted (stamp + pre-deploy upgrade) |
| `DHASHU_ASYNC_DIGILOCKER=1` | The worker is deployed and the provider-jobs alert is wired |
| `DHASHU_GZIP=1` | The load test is repeated with compression on |
