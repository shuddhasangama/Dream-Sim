# Go-live runbook

This is the day-by-day plan for opening DhaShu to real members, plus what to do when something goes wrong. The **owner** is Saravanan unless a task says otherwise. Nothing here is automated; every step is done by a named person and noted in the go-live channel.

## T−7 days: readiness

- [ ] Every item in `docs/RELEASE_CHECKLIST.md` §1 is green on the go-live commit.
- [ ] **Staging load test** (never production): 60 concurrent users for 15 minutes on the staging service.
  - Target: 0 errors, p95 under 1 s for reads.
  - Measured locally on one process: 29 req/s, 0 errors, p95 790 ms; REACH p95 1.2 s (perf-pagecache).
  - Record the staging numbers in `docs/SCALING.md`.
- [ ] Settings are reviewed on Railway against the release notes. Encryption keys are in sealed variables, with backups confirmed by two people (`docs/KEY_MANAGEMENT.md`).
- [ ] Sentry projects (backend and app) receive a test event, and the alert rules route to the on-call phone (`docs/ALERTS.md`).
- [ ] MSG91 (the SMS provider for sign-up, sign-in and resend):
  - DLT: the business entity (PE id) and the sender id (header) are registered and approved on the operator DLT portal.
  - The OTP message template is DLT-approved (DLT template id) and created in MSG91 → OTP → Templates with that DLT template id and the approved sender id; `MSG91_TEMPLATE_ID` on Railway is that MSG91 template id (24 hex).
  - `MSG91_AUTH_KEY` (MSG91 → Authkey) is in a sealed Railway variable on the **web** service only; any IP whitelist on the key allows Railway.
  - Account balance is topped up and a low-balance alert is set; a real code reached the owner's phone after deploy.
- [ ] Razorpay is in live mode with webhooks verified by HMAC (Ramya's sec-pay). **No** test keys in production.
- [ ] Admin dashboard is behind Cloudflare Access or an IP allow-list. Owner and support accounts exist with authenticator codes. The read-only reporting user is set (`ADMIN_REPORT_DATABASE_URL`).
- [ ] Backups: a restore drill into a scratch database is done, and the time taken is recorded.
- [ ] Store listings, privacy policy and data-deletion page are live. Support email and phone are monitored.

## T−1 day: freeze

- [ ] Code freeze on master; only fixes go in, through the release checklist.
- [ ] Production database snapshot taken.
- [ ] The on-call rota is posted for launch week. At least two people can redeploy and read Sentry.

## T−0: launch

| Time | Step | Who |
|---|---|---|
| 09:00 | Deploy web → worker → admin (release checklist §2). Watch 15 min. | Saravanan |
| 09:30 | Owner smoke test: sign up, sign in, dashboard, sign out, admin login. | Saravanan |
| 10:00 | Open the store listings and waitlist invitations in batches of 100. | Ops |
| Hourly | Check the dashboards (below); post a status line in the channel. | On-call |
| 18:00 | Day-one review: errors, OTP volume, signups, support tickets. Decide whether to open the next batch. | Owner |

**What to watch** (Sentry, Railway metrics, admin dashboard):

| Watch | Act |
|---|---|
| 5xx rate | Above 1 % for 5 minutes |
| p95 latency | Above 2 s for 10 minutes |
| `/api/v1/ready` failing | Any |
| `otp_global_breaker` | Any |
| `circuit_open` | Any (OTP, Signzy, OpenAI, Razorpay) |
| `abuse_spike` | Any |
| `security_event` (refresh reuse, lock) | More than 10 per hour |
| `stuck_verification_jobs` | Any |
| DB connections | Above 80 % of the budget in `docs/SCALING.md` |

## Incident playbook

| Situation | First action | Then |
|---|---|---|
| Site down or `/ready` failing | Railway: check the deploy logs and the DB status. If the last deploy is the cause, **redeploy the previous release**. | Reconcile any settings added for the release. Never downgrade the database schema. |
| 5xx spike after deploy | Redeploy the previous release. | Read the Sentry fingerprint; fix forward through the checklist. |
| OTP not arriving | Check the MSG91 dashboard (balance, delivery report for the number, template/DLT status) and the `circuit_open` / `otp_provider_down` alerts. | If MSG91 is down, post a status message. Do not raise OTP limits. |
| OTP pumping (`otp_global_breaker`) | Leave the breaker paused. Check the MSG91 delivery reports for unusual numbers and spend. | Tighten `DHASHU_OTP_COUNTRIES` / `DHASHU_OTP_GLOBAL_PER_HOUR` if needed. |
| Abuse or scraping (`abuse_spike`) | Identify the route from the event. If `DHASHU_TRUSTED_PROXY` is set, turn on `DHASHU_ABUSE_LIMITS=1`. | Add a Cloudflare WAF rule. |
| Account compromise reported | Admin dashboard → member → **Lock**, with a reason. This revokes every session. | Investigate. Unlock with a reason; the member signs in again. |
| Key suspected leaked | Rotate immediately (`docs/KEY_MANAGEMENT.md`), run the re-encryption with `--apply`, then remove the old key. | Treat it as a data incident: notify within legal timelines and keep a record. |
| DB overloaded or pool exhausted (`service_busy` 503s) | Check slow queries. Scale replicas only within the connection budget. | perf-index (Adithya) and perf-pagecache follow-ups. |
| Payment failures | Razorpay dashboard and `payment_webhook_failure` alert (sec-pay). | Do not replay webhooks by hand without the owner. |

**Communication:** the status line goes in the channel within 15 minutes of an incident and is updated every 30 minutes. A member-facing message is sent only after owner approval. A blameless postmortem is due within 3 days for anything that affected members.

## Week one

- Daily review at 18:00 using the same dashboards. Open further batches only if the previous day's errors and support load are within targets.
- Day 3: decide on `DHASHU_CSP_MODE=enforce` based on the report-only results.
- Day 7: review the abuse events, OTP spend and lock-ins. Write up the decisions in the release notes.
