# Phase 4 Block 7: enrollment and API-only validation

Implemented locally on 2026-09-14. No push, deployment, Railway data access or
real message delivery was performed. OpenAPI 0.7.0 describes every registered
`/api/v1` operation, including the existing Phase 2/3 authentication endpoints.

## Enrollment boundary

The beta supports **operator-invited new profiles** and previously approved
existing profiles. It does not offer anonymous public signup or automatic BGV.
The operator reserves a new onboarding identity using a tester-controlled email
or phone. The normal OTP flow proves ownership before the draft can be written.
The caller cannot supply a user ID, approve themselves, alter the bound contact,
or set verification, payment or journey-state fields in an enrollment request.

Prerequisites for later use: secure authentication enabled; a working OTP
provider for the chosen contact; an authorized operator; and an actual manual
background-review process before a new user can enter Dating. These tests mock
the OTP provider. They do not establish delivery or implement background checks.

Operator commands below are examples for a deliberately selected database.
They were not executed against Railway. The first command is a dry run; only
`--apply` creates the pending profile. Neither command sends a message.

```powershell
python enrollment_admin.py --email "tester@example.com"
python enrollment_admin.py --email "tester@example.com" --apply
```

Contact collisions with any existing account fail without creating a profile.
For an existing account use the existing `auth_admin.py` approval workflow;
enrollment never rebinds or overwrites it. Pending invitations do not expire
automatically; an operator can disable account access with existing account
administration. Public signup, identity merging, recovery/contact changes and
automated BGV remain outside this beta implementation.

## Mobile request sequence

All paths below have prefix `/api/v1`. Use JSON and, after verification,
`Authorization: Bearer <access_token>`. Never put tokens in URLs. Responses use
`{data, error}` and `Cache-Control: no-store`.

1. `POST /auth/request` with `{"channel":"email","destination":"tester@example.com"}`
   (or `phone` with country code). Save the returned `challenge_id`.
2. `POST /auth/verify` with `{"challenge_id":"…","code":"…"}`; retain the
   returned access/refresh tokens securely. Unknown/unapproved accounts cannot
   obtain tokens through the generic accepted request response.
3. `GET /enrollment` returns own draft, revision and canonical options/ranges.
   Existing accounts without an enrollment draft return `existing_profile` and
   use the normal profile-editing APIs.
4. Replace each complete section with `PUT /enrollment/sections/vision`,
   `/stats`, `/activities`, using `{"revision":0,"values":{…}}`. Supply the
   latest returned revision for each changed write. Vision requires all five
   arrays, including empty arrays for unselected detail families. Stats requires
   city, gender, salary and the fields listed in `options.required_stats`.
   Activities requires at least four valid activity/bucket selections.
5. `POST /enrollment/complete` with the latest `{"revision":3}` submits the
   complete profile atomically. It returns `submitted_for_review`, with
   `bgv_status: pending`; the user remains `onboarding`. Exact salary is removed
   from the stored draft on submission, while the profile stores its derived band.

Identical section retries do not increment the revision. A changed stale draft
returns 409; read the latest draft and reconcile rather than silently overwrite.
Completion is replay-safe and concurrent completion produces one final revision.
Submitted enrollment is closed to further section changes. No mobile endpoint
in this block can mark BGV successful or move a pending user into Dating.
Manual approval is a separate operator/provider responsibility, not a simulated
step in the API journey test.

## Executable evidence

Final full run: **1,331 passed, 738 subtests passed**, no skips, in 148.39 seconds.
The temporary PostgreSQL cluster and credentials were removed afterward.

Run the full isolated suite from the repository with PostgreSQL 18 installed:

```powershell
python run_local_postgres_tests.py
```

The helper creates a new localhost-only cluster with temporary credentials,
clears `DATABASE_URL` in the child environment, and removes the cluster and
credentials afterward. It does not connect to Railway. Focused checks:

```powershell
python -m pytest -q test_enrollment_api.py test_api_only_journey.py test_phase4_contract.py
python run_local_postgres_tests.py test_enrollment_postgres.py
```

The continuous journey test starts with isolated, already approved synthetic
profiles. Every subsequent journey action is a JSON request with a bearer token;
there are no HTML actions or inter-step database changes. Test-controlled
simulation-clock advancement is explicit. It exercises:

- Mocked OTP sign-in and identity, REACH, actual Week preparation and mutual interest.
- Both partners' alignment/availability, two distinct date plans and agreements,
  early-feedback rejection, both feedback submissions, and exact count/retry history.
- Own Vision/Chemistry answers, reflection delay, both gate confirmations and
  agreements, and relationship entry.
- ROAD creation/sharing/overlap, separate consent for Engaged and Married,
  duplicate advancement, unrelated-user rejection, refresh and logout revocation.

The same complete test runs on SQLite and isolated PostgreSQL. Additional
enrollment tests cover missing OTP proof, disabled accounts, unknown fields,
invalid numeric/vision values, dry runs, contact collisions, stale edits,
rollback on failed completion, and concurrent invitation/draft/completion.
Existing Block 3–6 tests retain cancellation, rejection, no-show, privacy,
independent exit/re-entry, transaction rollback and partner-order coverage.
The contract test checks both directions: every documented route exists and
every registered JSON operation is documented.

## Remaining limitations

This is local backend validation, not mobile beta deployment certification.
Real email sender authentication/delivery and live mobile token checks remain
Phase 3 work. SMS success previously reported by the user is separate evidence.
Face confirmation is the explicitly enabled approved-beta simulation; payments
are enforced prerequisites when enabled, not a real checkout. Guru synthesis,
automated weekly reports, trusted-contact delivery and the simulation clock
retain the limitations recorded in Blocks 3–6. Capacitor packaging, real-phone
testing, deployment validation and production hardening remain subsequent phases.
