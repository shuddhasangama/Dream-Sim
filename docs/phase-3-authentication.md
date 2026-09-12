# Phase 3 — email/SMS sign-in and revocable sessions

## Scope and status

The beta supports a choice of email OTP or SMS OTP, using Twilio Verify.
SendGrid is connected to the Verify service for email delivery. This is
passwordless sign-in; it does not require both channels for each login and is
not multi-factor authentication.

The implementation is for approved existing beta profiles. New-user API
onboarding remains Phase 4. When secure mode is enabled, public simulation
signup/onboarding redirects to sign-in; it cannot create a trusted session.
Approve and review tester accounts before switching the existing Railway
service to secure mode. The simulation's grandfathered contact flags are not
accepted as sign-in credentials.

No live messages have been sent by development tests. Provider calls are
mocked. Provider configuration and live delivery tests remain required.

## Local validation — 2026-09-12

The complete suite passed: **1,243 tests and 718 subtests**, including five
integration tests on an isolated, password-protected local PostgreSQL 18
instance. Coverage included concurrent refresh, concurrent OTP redemption,
shared throttling, revocation, and upgrading a legacy Account schema. Provider
responses were mocked; real email/SMS deliverability remains unverified. The
temporary PostgreSQL instance and its credentials/data were removed afterward.

The Phase 3 changes remain local and have not been pushed or deployed.

## Seven work items

| Work item | Implementation |
| --- | --- |
| Account identity | Existing Account-to-User association; explicit beta approval; canonical contact collisions fail closed |
| Email and SMS OTP | Twilio Verify HTTPS adapter; email through its SendGrid integration; no displayed-code fallback |
| Mobile sessions | Random access/refresh tokens, database hashes, expiry, rotation, refresh replay revocation |
| Web sessions | OTP sign-in page, secure cookie, server-side expiry/revocation, same-origin mutation checks |
| Ownership and bypass protection | Session identity drives existing APIs; invalid bearer tokens never fall back to cookies; simulation identity routes blocked in secure mode |
| Tests | Local SQLite and isolated PostgreSQL coverage, including concurrent refresh and throttling |
| Deployment | Additive schema and account approval helper; provider setup and live validation described below |

## Provider setup — required before enabling secure mode

1. Create/configure a Twilio account and a Verify service. Enable SMS for the
   intended tester destinations. Follow Twilio's trial-recipient and country
   requirements. Review available fraud controls and usage limits.
2. Create/configure SendGrid. Authenticate a sender/domain, create a verification
   email template, and connect the SendGrid email integration to the Twilio
   Verify service. The SendGrid API key belongs in that integration; this Flask
   application only calls Verify.
3. Add the following variables to the Railway Dream-Sim service. Enter secrets
   directly in Railway, not in source files, command history, chat or screenshots.

| Variable | Value |
| --- | --- |
| `TWILIO_ACCOUNT_SID` | Twilio account SID beginning `AC` |
| `TWILIO_AUTH_TOKEN` | Twilio account authentication secret |
| `TWILIO_VERIFY_SERVICE_SID` | Verify service SID beginning `VA` |
| `AUTH_PUBLIC_ORIGIN` | `https://dream-sim-production.up.railway.app` |
| `SECRET_KEY` | A strong random secret of at least 32 characters; retain the existing one if it meets this requirement |
| `AUTH_ENABLED` | Leave unset/`0` until accounts and provider configuration are ready; set `1` for secure beta mode |

`DATABASE_URL` remains the existing PostgreSQL connection. No SMTP setting,
password database, Redis or new Python dependency is required.

When `AUTH_ENABLED=1`, missing/invalid essential configuration fails startup.
This checks configuration shape, not delivery: incorrect credentials or an
unconfigured email template must still be caught by the live checks below.

Railway supports outbound HTTPS for these APIs. Its email guidance recommends
HTTPS email services; SMTP is restricted on lower plans.

## Schema and existing data

Phase 3 adds `Account.auth_enabled` (default `0`) and four tables:
`AuthSession`, `AuthRefresh`, `AuthChallenge`, `AuthThrottle`.
SQLite and PostgreSQL schema files stay in parallel. The existing initialization
and reconciliation path adds the column/tables without deleting profiles or
changing journey states. The reconciliation helper now recognizes BIGINT and
uses the active PostgreSQL schema instead of hard-coding `public`.

No existing account is automatically approved for secure login. No migration has
been run against Railway during development. Back up the database before the
first Phase 3 deployment. Turning off secure mode reopens the simulator; it is
not a safe fallback once real beta users depend on authentication. If an enabled
release fails, keep access restricted while repairing configuration or rolling
back to a secure release.

## Approve testers and recover contact details

Use `auth_admin.py` from a trusted operator environment connected to the intended
database. It is not an HTTP endpoint. Confirm the profile ID and real contacts
with the tester before associating them; never infer a user's ownership from a
similar display name.

Example placeholders (replace them yourself):

```text
python auth_admin.py enable --user-id USER_ID --email TESTER_EMAIL --phone +COUNTRYCODE_NUMBER
python auth_admin.py enable --user-id USER_ID --email TESTER_EMAIL --phone +COUNTRYCODE_NUMBER --apply
python auth_admin.py disable --user-id USER_ID --apply
```

Without `--apply`, account changes are only described. The helper still runs
normal schema initialization; schema creation/reconciliation can therefore occur
even on a dry run. Without `DATABASE_URL`, it targets the local SQLite database.
Do not assume a local command changes Railway.

- A seeded profile without an Account can be enrolled with real contact details.
- An existing account can retain its stored contacts by omitting those options.
- Phone numbers must include a country code. There is no automatic conversion
  of an ambiguous local number into an Indian number. Confirm legacy contacts.
- Duplicate canonical email/phone associations are rejected.
- Re-approval/contact correction clears contact verification and invalidates
  existing sessions/challenges; a fresh provider-approved OTP is required.
- Disabling an account revokes all sessions immediately.
- Lost access to both contacts requires operator recovery after checking identity.
  Self-service contact replacement is not included in this beta phase.

## API contract

All routes use the Phase 2 envelope: `{"data": ..., "error": null}` or
`{"data": null, "error": {"code": ..., "message": ..., "detail": ..., "reference": ...}}`.

| Method/path | Body / behavior |
| --- | --- |
| POST `/api/v1/auth/request` | `{"channel":"email","destination":"tester@example.test"}` or `{"channel":"phone","destination":"+919876543210"}`; returns 202 with `challenge_id`, `expires_in`, generic message |
| POST `/api/v1/auth/verify` | `{"challenge_id":"...","code":"123456"}`; returns mobile access/refresh tokens on provider approval |
| POST `/api/v1/auth/refresh` | `{"refresh_token":"..."}`; returns replacement credentials and invalidates the old access/refresh pair |
| POST `/api/v1/auth/logout` | Bearer token; revokes that session |
| POST `/api/v1/auth/logout-all` | Bearer token; revokes all sessions for its user, including web sessions |

Successful verify/refresh includes `access_token`, `refresh_token`,
`token_type: Bearer`, `expires_in`, `refresh_expires_in`, `session_id`, `user_id`.
Subsequent mobile API calls send `Authorization: Bearer ACCESS_TOKEN`.
Tokens must never be sent in query strings. Future mobile clients should keep
access tokens in memory and refresh tokens in platform-protected secure storage.
They must serialize refresh requests: reuse of a consumed refresh token revokes
that session family, including after an ambiguous network retry.

Access tokens last 15 minutes. Refresh credentials last up to 7 days and rotate,
with an absolute session lifetime of 30 days. Web sessions last 12 hours and
require a fresh OTP afterward. Expiry uses real time, not the simulation clock.

Login challenges expire locally after 10 minutes and allow 5 code checks.
Resending invalidates earlier local challenges for the same account/channel.
The provider may enforce shorter validity or additional limits. Wrong, expired,
unknown and disabled-account verification attempts return generic 401 errors.
Unknown/disabled contacts get the same 202 request response but receive no
message. Provider delivery failure also fails closed without revealing details.

Requests are limited per canonical contact (one send per minute), resolved
client address (20 sends/10 minutes, 30 checks/10 minutes), and refresh requests
(60/minute). Limits live in PostgreSQL across workers. The app does not trust a
client-supplied X-Forwarded-For header; if Railway exposes a shared proxy address,
these address-based limits are shared and conservative. Confirm behavior during
beta and configure trusted proxy handling only after checking Railway's headers.

## Web behavior and security boundary

`/signin` offers email or SMS, then code entry. Its challenge stays in a signed
cookie and cannot be exchanged for mobile tokens. Successful login rotates the
cookie contents. The secure cookie is named `dhashu_auth`, is HttpOnly, Secure,
and SameSite=Lax. Old simulation user-id cookies do not establish identity.

Unsafe cookie-authenticated requests require Origin (or Referer when Origin is
absent) matching `AUTH_PUBLIC_ORIGIN`. Mobile bearer requests do not rely on
cookies. Invalid Authorization headers never fall back to an existing cookie.
Existing REACH handlers read the same authenticated identity as the API wrapper.

Secure mode blocks `/pool`, `/login/*`, `/admin*`, `/demo*`, `/verify/simulate`
and the old displayed-code `/verify-contact*` routes. It hides the demo bar and
changes Switch user to Sign out. It blocks public simulation onboarding and
keeps account approval in the operator CLI. Background-verification, payment and
journey simulations are not transformed into real providers by this work.

The API retains same-origin web behavior; cross-origin CORS support for a future
Capacitor WebView is not configured here. Phase 5 must select a native HTTP
transport or add an explicit origin allowlist—never wildcard credentialed CORS.

## Validation and release sequence

1. Run local authentication, API and regression tests. Provider calls must be
   mocked unless a tester explicitly authorizes real delivery.
2. Deploy the additive code/schema with `AUTH_ENABLED=0` while preparing the
   provider configuration and approving the tester accounts.
3. Enable secure mode only once both email/SMS configuration and approved
   accounts are ready. Confirm the user picker is now inaccessible.
4. On real tester contacts, request and verify one email code and one SMS code.
   Verify they map to the intended profile, not another similarly named user.
5. Verify authenticated REACH, refresh rotation, logout, and browser sign-out.
   Confirm wrong codes, expired codes and old simulation cookies are rejected.
6. Record live results. Local provider mocks cannot establish deliverability or
   actual provider-account configuration.

Optional PostgreSQL tests use `AUTH_TEST_POSTGRES_DSN_FILE`, an explicit file
containing credentials for a disposable localhost test database. They create
and drop uniquely named test schemas and refuse a remote database host.
Never point the test fixture at a database containing real user information.

## References

- [Railway outbound networking/email](https://docs.railway.com/networking/outbound-networking)
- [Twilio Verify email with SendGrid](https://www.twilio.com/docs/verify/email)
- [Twilio verification requests](https://www.twilio.com/docs/verify/api/verification)
- [Twilio verification checks](https://www.twilio.com/docs/verify/api/verification-check)
- [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
