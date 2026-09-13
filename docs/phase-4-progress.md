# Phase 4 implementation record

## Block 1 — contracts and journey/dashboard status

Implemented locally on 2026-09-13; no Railway deployment or provider calls.

New GET routes:

- `/api/v1/dashboard`
- `/api/v1/journey/status` (same projection as dashboard)
- `/api/v1/guidance` (existing Guru next-action logic, gated by verification)

`docs/openapi-phase4.json` is the incremental OpenAPI 3.1 contract for these
implemented reads. It intentionally does not pretend to document unimplemented
Phase 4 actions. Existing Phase 2/3 endpoints retain their contracts.

The status response includes the authenticated user's identity/stage, contact
verification flags (no addresses), milestone and stage display, simulated clock,
allowlisted current pair/date/couple summaries, surface eligibility and next
action. The canonical `user.journey_state` remains exact even for onboarding,
exiting, cooloff and re-entry; the existing four-stage visual indicator has its
own display fallback. A contact verification flag is not proof of BGV.

`surfaces[].eligible` describes the existing journey rules. `api_available`
separately describes whether a JSON read endpoint is implemented. `request` is
null whenever either is false. Consumers must not construct missing URLs from
surface names. The response's next action uses the existing Guru decision rules;
it can name a later surface while leaving its request null until that block ships.

These routes do not generate matches, resolve stale outcomes, change the clock,
or send messages. They report currently persisted state. Normal application
database initialization still runs as it does for other authenticated routes.
The clock is explicitly labelled simulation; this does not implement scheduling.

Shared helpers in `api_contract.py` provide allowlisting and strict JSON-object
validation. Existing REACH mutations now use that validator while keeping their
field-specific checks, persistence and envelope. Illegal journey transitions can
use the added `409 state_conflict` envelope code in subsequent blocks.

### Validation

- Focused API/authentication run: 44 passed, 30 subtests passed.
- New tests cover actor isolation, anonymous/invalid/revoked bearer requests,
  refresh rotation, unverified users, all journey stages, pair allowlists,
  absent API destinations, method errors and repeated read-only requests.
- Full regression suite: **1,249 passed, 5 skipped, 726 subtests passed** in
  51 seconds. The skipped tests require the separate isolated PostgreSQL fixture;
  this block adds no schema changes or transactional mutations.

### Local use

With a valid mobile access token, request `GET /api/v1/journey/status` with an
`Authorization: Bearer ...` header. The token must never be put in the URL.
Browser clients can use the secure session cookie. All responses retain the
Phase 2 `{data, error}` envelope and `Cache-Control: no-store`.

## Remaining sequence

2. Week/matches/mutual lock-in; 3. Calendar/alignment/plan/agreement;
4. Feedback and repeated dates; 5. After-date/gates/profile evolution;
6. Relationship/ROAD/later stages; 7. Enrollment and API-only full-journey tests.

Email sender-domain authentication and live mobile token validation remain
separate Phase 3 items. The user reported successful SMS login and browser
REACH/logout/re-entry for the designated testers; no new live tests were run here.
