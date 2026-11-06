# DhaShu private admin dashboard deployment

Built for admin.shuddhasangama.org, with office@shuddhasangama.org as the initial owner. This is a separate service, not the app's legacy /admin route. No new mobile build is needed.

## Included

- Password plus six-digit authenticator TOTP; no public admin signup, no email-code delivery dependency, no member-login access.
- Owner, support and aggregate-only marketing roles; server-side restrictions on every report.
- Enabled accounts, phone verification, signup flags, stored BGV/journey state, observed activity counts, masked account search, per-user check/error summary, sessions, provider pauses, city/payment aggregates and access audit.
- Opaque server-side sessions, 30-minute idle expiry and eight-hour absolute expiry; revocation on logout/credential reset, login throttling, TOTP replay protection, same-origin/CSRF checks, host-only secure cookies, no-store and restrictive browser headers.
- Bounded report queries in read-only database transactions, five-second PostgreSQL statement timeout and paginated lists. No dashboard provider calls or member updates.
- Opt-in activity recording from authenticated member requests, at most once per account per minute per process. Records only user ID, first/last observed time, coarse platform and mobile/web kind. It does not record routes, IPs, raw user agents, message contents or device identifiers. Backend failure cannot block member login.

## Not represented as complete

Downloads, first opens, campaign attribution/spend/CAC and Brand Meadows invoice counts are not integrated. Chemistry completion is not inferred from default JSON. Dating stage is not a guarantee of current matching eligibility. Valid credentials do not imply online presence. Activity has no retroactive history and account-level last activity is not individual-session activity. Existing beta accounts are not silently labelled genuine new signups. Sandbox captures are not revenue; sandbox BGV is not production approval.

## 1. Publish the prepared code

From Windows PowerShell, in the release worktree, inspect the commit before pushing. Do not push the older dhashu-phase2 working folder or its unrelated edits.

```powershell
Set-Location 'C:\DreamContractLocalBKP\ChatGPT\dhashu-waitlist-release'
git fetch origin master
git log --oneline origin/master..HEAD
git push origin HEAD:master
```

No force push. If rejected, stop and reconcile the newer remote work.

## 2. Create a separate Railway service

In the existing faithful-miracle project (c768517b-18ad-4855-8bad-521915324c10), production environment, create a GitHub service from shuddhasangama/Dream-Sim, branch master. Name it dhashu-admin. Use the repository root, not mobile/. Set its start command to `python service_entrypoint.py` and healthcheck path to `/healthz`.

Set only these required variables on **dhashu-admin**:

| Variable | Value |
| --- | --- |
| DHASHU_PROCESS_ROLE | admin |
| DATABASE_URL | Reference the same private PostgreSQL DATABASE_URL used by Dream-Sim; use Railway's variable picker, do not paste it into chat |
| ADMIN_PUBLIC_ORIGIN | https://admin.shuddhasangama.org |
| ADMIN_TOTP_ENCRYPTION_KEY | A new private Fernet key generated below; distinct from Signzy keys |

Generate the key in your private PowerShell terminal. Copy the output directly into Railway; do not send it in chat or commit it:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

If cryptography is not installed locally, run the same command with `/app/.venv/bin/python` in your existing Railway console. It generates a key only; it changes no database records.

Do not set ADMIN_ALLOW_HTTP, ADMIN_LOCAL_DEMO or ADMIN_LOCAL_DB_PATH in Railway. Do not copy Signzy/OpenAI/Twilio credentials into the admin service. Do not configure the member app's DHASHU_BGV_BOOTSTRAP_USER_ID there. Railway provides PORT. Keep the encryption key stable and stored privately; routine deploys must not rotate it.

The admin start role applies additive schemas, creates no administrator automatically, and never seeds simulated users or invokes providers. If shared variables accidentally include a web/worker role override, correct it before deployment.

## 3. Domain and HTTPS

In dhashu-admin Settings > Networking, add custom domain `admin.shuddhasangama.org`. At the DNS provider, add exactly the record Railway supplies for host `admin`; do not change the root domain or MX/email records. Wait for Railway to verify DNS and provision HTTPS. The production application intentionally accepts only its configured host and HTTPS; its Railway-generated URL will not serve dashboard data as an alternate origin.

## 4. Create the owner privately

Open the **dhashu-admin** service console, not Dream-Sim, and run:

```bash
cd /app && /app/.venv/bin/python -m admin_dashboard.manage create --email office@shuddhasangama.org --role owner --apply
```

Enter a password of at least 14 characters at the hidden prompts. The command displays a PRIVATE authenticator setup key once. Add it to your authenticator as a time-based, six-digit, 30-second account named DhaShu Admin. Enter its current code at the hidden prompt. The identity is created only after the code is verified. Use the NEXT code to sign in at https://admin.shuddhasangama.org. No email is sent. Mailbox existence alone does not create an admin account.

The setup key is private. Do not screenshot or share it. Anyone with it and the password can authenticate. No credentials are included in the repository or previews.

## 5. Enable real activity recording

Deploy the same release to **Dream-Sim** and set `DHASHU_ACTIVITY_ENABLED=1` there. The admin service's migration creates UserActivity; the web backend records subsequent authenticated requests. No BGV-worker deployment is required by this dashboard change. Do not change OTP, signup, billing or simulation settings to deploy the dashboard.

Until observations arrive, activity cards say Not recorded. Counts then cover observed authenticated requests; background authenticated polling may also count and is not evidence of intentional foreground use.

## 6. Read-only launch check

- Before sign-in, reports return 401; no member data appears in the HTML.
- Owner can inspect all six sections; search an owned test phone and verify the correct account reference, masked phone, journey and check summary.
- Compare totals with a read-only Railway query; disabled accounts and seed profiles without Account rows must not inflate enabled-account counts.
- Verify sandbox payment/check labels; do not interpret history as current employment or approval.
- Make a normal authenticated app request and confirm Last active updates within the throttle window.
- Sign out; the previous admin cookie must no longer access reports.
- Create marketing access only with separate individual identities. That role can read Marketing only, not Users, Sessions, Checks, Overview or Audit. No partner receives the owner account.

## Operations

Create another identity privately using `manage create --email ... --role support|marketing --apply`. Provisioning an administrator is a privileged operator action; an ordinary app signup never grants access.

Lost password/authenticator (requires trusted Railway console access):

```bash
cd /app && /app/.venv/bin/python -m admin_dashboard.manage reset --email office@shuddhasangama.org --apply
```

This replaces password/authenticator, revokes all that admin's old sessions and creates an audit entry. It preserves the existing role. Disable access using `manage disable --email ... --apply`. Dry run is the default without --apply. Email addresses should identify individuals; do not share the office owner password with the agency.

The first deployment reuses the private database connection for auth storage and fixed read-only reporting transactions. Optional hardening: provision a dedicated PostgreSQL SELECT-only role limited to required reporting tables/columns and set ADMIN_REPORT_DATABASE_URL on the admin service. It must be able to read the needed tables, including AdminAudit/AdminIdentity for the owner audit view. Do not expose the database through a public endpoint. Admin report access itself is audited; no search strings or personal values are stored in audit rows. Activity and audit retention policy should be agreed before broader rollout; no destructive retention job is enabled in this release.

## Validation scope

Local SQLite and isolated localhost PostgreSQL tests cover authentication, replay/throttle/expiry, CSRF/origin/role boundaries, masked projections/search, read-only queries and schema idempotency. Browser tests cover all sections, private search and account summary, with desktop/mobile screenshots from synthetic data. Production login, DNS, live counts and store analytics are not established by these tests.
