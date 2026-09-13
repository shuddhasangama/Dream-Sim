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

## Block 2 — Week, match decisions and mutual lock-in

Implemented locally on 2026-09-13; no live data changes. New endpoints:

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/v1/week` | Persisted matches, reveal status, schedule, current pair/date; no generation or stale-outcome resolution |
| POST | `/api/v1/week/prepare` | Empty JSON body `{}`; prepare the current verified Dating user's week atomically |
| GET | `/api/v1/matches/{match_id}` | Only an owned, revealed match; disclosure-safe candidate summary |
| POST | `/api/v1/matches/{match_id}/actions` | `action`: interest/pass; optional `pass_reason` (up to 1000 characters, pass only) |
| GET | `/api/v1/lock-ins/current` | Allowlisted current lock-in, or null |

GET Week returns a `prepare_request` when preparation is needed. Clients explicitly
POST that request once, then use GET for polling. HTML retains lazy preparation,
but calls the same atomic service. Empty and non-empty batches are persisted in
the new additive `MatchBatch` table; repeated preparation cannot silently add
candidates when the pool changes midweek. Existing Match rows are adopted on first
preparation. Unverified/non-Dating candidates are excluded during generation.

Future slots expose schedule/status only, never candidate identity or interest.
Match detail rejects unknown, foreign and unrevealed IDs with 404. Candidate JSON
omits contact addresses, internal user IDs, preferences, signatures and private
answers. Display names use the existing disclosure rule. Allowed actions are
rechecked inside the mutation; they are not trusted client authorizations.

The HTML `/week/act` and JSON action call `week_service.decide`. Identical decisions
are natural idempotent retries (`replayed=true`); changing a recorded decision is
a 409 conflict. Windows are enforced using the server's existing simulation clock.
Both interests, lock-in creation and clearing the other candidates commit as one
transaction. A failed write rolls back the entire transition. PostgreSQL uses a
conservative table-lock strategy for this small beta; SQLite uses BEGIN IMMEDIATE.
This trades throughput for correctness and should be narrowed before scaling.

The demo/reset helper includes MatchBatch so local walkthrough resets can prepare
a new week. No public admin/reset or arbitrary lock-in creation API was added.
The old internal `_create_lockin` remains for simulator helpers; live web/API match
decisions use the shared transaction service.

### Validation

- Isolated PostgreSQL full-suite run: **1,266 passed, 728 subtests passed**, no
  skips; includes all five existing PostgreSQL auth tests plus three new Week
  races (reciprocal interest, competing partners, concurrent generation).
- Local tests additionally cover zero-result batches, future reveal privacy,
  closed windows, actor isolation, contact requirements, web/API parity and
  rollback after an injected mid-transaction failure.
- `run_local_postgres_tests.py` creates a password-protected loopback-only
  PostgreSQL 18 cluster, runs the suite, shuts it down and removes its temporary
  data/credentials. It never reads Railway credentials.
- Final full regression run, including candidate-stage exclusion and contract
  reference tests: **1,268 passed, 728 subtests passed**, no skips, in 97.92 seconds.
  The temporary PostgreSQL cluster shut down and its files were removed.

### Deployment boundary

Block 1 is saved in local commit `fc431f6`. Block 2 adds a table: take a fresh
backup before eventual deployment. Both SQL schema files and drift-check.sql
include the new table. No push or Railway deployment is part of these local runs.
The clock remains the existing simulator clock: this block does not claim a
wall-clock scheduler or resolve stale dates via GET. Date outcome reconciliation
belongs with block 4's transactional date cycle.

## Block 3 — calendar, alignment, plans and date agreements

Implemented locally on 2026-09-13. Builds on `fc431f6` and `1b99582`.
No schema migration is needed for this block.

| Method | Route (under `/api/v1`) | Purpose |
|---|---|---|
| GET | `/lock-ins/{lid}/calendar` | Own availability, shared overlap, alignment answers/options/missing fields, current plan and payment prerequisite |
| PUT | `/lock-ins/{lid}/alignment` | Replace own budget/diet/cuisine answers |
| PUT | `/lock-ins/{lid}/availability` | Atomically replace own selected slots |
| POST | `/lock-ins/{lid}/date-plan` | Confirm an actual shared slot and create one plan |
| GET | `/date-plans/{pid}` | Allowlisted plan, own selections, signature completion flags and payment prerequisite |
| PUT | `/date-plans/{pid}/selections` | Replace own dietary/dress selections before either partner signs |
| GET | `/date-plans/{pid}/agreement` | Read clauses, required acknowledgements and own ceremony state without inserting rows |
| POST | `/date-plans/{pid}/agreement/steps` | Explicit playbook/sign/face transition; complete ceremony and Signature mirror atomically |

The calendar response advertises valid slots and alignment options. The client
uses the authenticated user's current lock-in ID from journey status. `lid` and
`pid` are resource identifiers, never actor IDs. Another user's resources return
404. Unverified or non-Dating actors are rejected. Closed dates and released
pairs reject mutations. Full partner availability, private profile fields,
contact details and partner typed signatures are not serialized.

Request examples:

```json
{"slots": [{"day": "Sat", "meal_slot": "dinner"}]}
```

The confirmation POST takes `{"day":"Sat","meal_slot":"dinner"}`. Both
partners must have complete alignment and the slot must exist in both saved
availability sets. Both availability entitlements are checked if fees are on.
The same confirmation returns the existing plan; a different slot conflicts.
Alignment and availability freeze once the plan exists. Selections freeze once
either actor signs, including through the older HTML signing flow.

Agreement step bodies are explicit, so retrying a previous step never silently
executes the next one:

```json
{"step":"playbook"}
```

```json
{"step":"sign","signed_name":"Your name","acks":["ack_conduct","ack_cancellation","ack_not_a_relationship","ack_liability"]}
```

```json
{"step":"face"}
```

Identical completed-step retries do not duplicate signatures. Changing a recorded
signature conflicts. A failed signature write rolls back ceremony completion.
Each actor must complete their own agreement; one actor cannot sign for both.

### Shared services and compatibility

`planning_service.py` owns the transactions. The HTML calendar submit/confirm,
alignment, selections and date-agreement ceremony now call it too. The older
HTML `/plan/sign` retains its checkbox flow, sharing the atomic signature mirror
and preventing a retry from downgrading a completed signature. Browser ceremony
forms include the displayed step to make retries explicit.
The existing HTML no-overlap reset/release is also serialized with confirmation:
it cannot clear slots or release a pair after a plan exists, or claim no overlap
when shared availability exists.

Corrected HTML behaviour: selecting a merely valid slot is insufficient without
mutual availability; editing inputs for an already created/signed date conflicts.
Existing redirects for missing alignment and payment prerequisites remain.
The PostgreSQL locking strategy deliberately serializes date-planning writes for
the small beta; narrow its table locks before scaling. SQLite uses BEGIN IMMEDIATE.

Journey status advertises calendar/alignment/plan read links when an eligible
actor has the corresponding current resource. OpenAPI 0.3.0 documents all eight
new operations, input shapes, responses and error outcomes.

### Simulation and deployment boundaries

- Payment responses say `provider_mode=simulation`. This block creates no payment
  endpoint and grants no payment entitlement. When existing fees are enabled,
  unpaid actors are blocked; the existing HTML simulation checkout remains the
  prerequisite until a real payment provider is implemented. Tests disable fees
  explicitly in isolated fixtures; that is not evidence of real payment delivery.
- API face simulation defaults OFF. `BETA_DATE_SIMULATION_ENABLED=1` enables it
  only for an approved Account (`auth_enabled=1`). It calls the existing random
  simulator and takes no face image; it is not biometric identity verification.
  Existing HTML simulation behaviour is retained. The stored legacy field
  `face_verified` remains a simulation result, not proof of real identity.
- No environment variables were changed in Railway. Real payment and face
  providers are not implemented by this block. The existing simulation clock
  and calendar epoch remain in use; no real-time scheduler was added.
- Cancellation, no-overlap release/reset and repeat-cycle resolution are not
  exposed by this block. A closed first-cycle plan cannot be overwritten to
  start another date. Block 4 owns that lifecycle and its API coverage.

### Validation

- Initial full isolated PostgreSQL regression: **1,280 passed, 728 subtests**,
  no skips, in 90.88 seconds.
- Follow-up API/contract checks: **13 passed**, including added foreign-mutation,
  media-type and mixed HTML/API signature tests.
- Full regression after additional authorization/parity and concurrency tests:
  **1,284 passed, 728 subtests**, no skips, in 92.60 seconds.
- Follow-up checks after the HTML recovery guard: **24 passed, 8 subtests**.
- Final full regression, including the recovery guard: **1,284 passed,
  728 subtests passed**, no skips, in 101.91 seconds. The isolated PostgreSQL
  instance stopped and its temporary data and credentials were removed.
  Coverage includes
  simultaneous plan confirmation, simultaneous partner agreement completion,
  availability-versus-confirmation races, injected rollback failures, no overlap,
  invalid fields, missing alignment, payment enforcement and opt-in simulation.
- Local test runner starts a password-protected loopback PostgreSQL instance and
  removes its temporary data and credentials after shutdown. No Railway data,
  provider requests, pushes or deployments are involved.

## Remaining sequence

4. Feedback and repeated dates; 5. After-date/gates/profile evolution;
6. Relationship/ROAD/later stages; 7. Enrollment and API-only full-journey tests.

Email sender-domain authentication and live mobile token validation remain
separate Phase 3 items. The user reported successful SMS login and browser
REACH/logout/re-entry for the designated testers; no new live tests were run here.
