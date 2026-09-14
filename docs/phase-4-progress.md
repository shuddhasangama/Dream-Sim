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

## Block 4 — date feedback, cancellation, no-show and repeat cycles

Implemented locally on 2026-09-13, building on Block 3 commit `2d1d2ad`.

| Method | Route under `/api/v1/date-plans/{pid}` | Purpose |
|---|---|---|
| GET | `/debrief` | Timing, own feedback, options, mutual photo consent, resolution and cancellation terms |
| PUT | `/feedback/flags` | Exactly two distinct green flags, up to two red flags, optional per-actor photo consents |
| POST | `/feedback/decision` | continue / relationship / pass, with optional private pass reason |
| POST | `/cancel` | Assisted cancellation before the date starts; assess applicable fee without collecting it |
| POST | `/no-show` | Record an unverified report and release the pair; no green flags required |
| POST | `/feedback/reconcile` | Explicit, idempotent timeout resolution after the date's simulation week closes |

New additive tables: `DateFeedback` (one private submission per actor/date),
`DateResolution` (one resolution receipt per date), and `DateCharge` (one pending
assessed cancellation charge per date). Both database schemas, reset ordering
and drift-check.sql include them. Take a fresh backup before any later deployment.

`date_cycle_service.py` shares transactions with the Block 3 planning service.
HTML feedback, cancellation, no-show and legacy Week timeout reconciliation call
the same service. API GETs never resolve outcomes. The existing web Week still
performs its lazy timeout check, now idempotently. No scheduled worker was added.

DatePlan, Signature, Ceremony and DateOutcome history is retained. Continuing
together marks that date completed, increments the pair count once, clears only
availability and opens the next calendar cycle. The next plan gets a new ID and
the next simulation week. Existing availability payment history is retained;
repeat cycles have distinct payment scopes and cannot reuse the first fee.

Calendar now returns `cycle`. Pass it with the plan-confirmation JSON, e.g.
`{"day":"Sat","meal_slot":"dinner","cycle":2}`. It is mandatory after the
first date. An old confirmation cannot create/overwrite a later date. New HTML
forms carry cycle/date identifiers; legacy forms without a date ID are accepted
only in the first cycle. API feedback paths always name the exact date.

Same recorded submissions are safe retries. Changed decisions, updates after
resolution and foreign dates are rejected. Private partner reasons and flags
are never in the debrief response. Shared photo consent requires both actors'
explicit opt-in; one person's report/checkbox cannot grant the other's consent.

Feedback opens one hour after the stored date, rounded up to the existing
simulation hour, and closes at the next simulation week. Invalid stored times
require correction rather than allowing early feedback. Cancellation after the
date starts is rejected. Late cancellation records one compliance event and,
when fees are enabled, one pending DateCharge; early cancellation records neither.
The existing Payment purpose CHECK excludes cancellation, so the assessment has
its own table rather than silently altering deployed payment constraints. This
does not implement a payment provider or collect money.

One explicit pass releases the pair immediately, following the existing documented
"one no is enough" rule (the old pure helper waited for both). A date is counted
only when both actual decisions are present; no-show, cancellation, timeout and
one-sided rejection do not assert a mutually completed date. Both relationship
decisions open the existing gate once without changing either user's stage.

No-show releases the pair as before, but is stored as an unverified report:
it does not create a punitive no_show strike, claim mutual non-attendance or count
a completed date. A user who already submitted affirmative date feedback cannot
then submit a contradictory no-show report through this endpoint. Review and
adjudication are not implemented here. The web copy now describes a report.

Historical DateOutcome rows with both decisions but no resolution receipt are
rejected for further mutation (`legacy_resolution_required`): local code cannot
reliably infer whether production already incremented their count. No production
records were examined or backfilled. Previously deleted history cannot be recovered
by this change.

### Validation

- Focused web and two-user API flow checks: **81 passed, 5 subtests**.
- Coverage includes two successive API-arranged/signed dates, both decision
  orders, rejection, early/late cancellation, no-show, consent/privacy, timeout,
  stale retries and rollback after an injected resolution failure.
- PostgreSQL race tests cover simultaneous partner decisions, duplicate final
  decisions, competing cancellations and competing no-show reports.
- Full isolated PostgreSQL regression: **1,298 passed, 734 subtests passed**,
  no skips, in 106.53 seconds. Temporary PostgreSQL data/credentials were removed
  after the instance stopped.
- All changes remain local. No provider messages, Railway access, pushes or
  deployment were performed.

## Block 5 — after-date, relationship gate and own-profile editing

Implemented locally, 2026-09-14. OpenAPI 0.5.0 lists the callable resources.
Profile stats support atomic strict patches with existing edit holds, re-review
requests, activities, chemistry questions with pacing, and append-only vision
details/disclosed reversals with actor-scoped request IDs. Re-review only records
a request; it neither contacts a provider nor clears BGV.

After-date JSON resources cover neutral contact requests, recipient responses,
home invitation/flag/guidance/acknowledgement/revocation, reciprocal Next Level
questions, and contact/home/entry ceremonies. Foreign IDs and requester self-
acceptance are rejected. Contact values require recipient acceptance and both
ceremonies. Phone/WhatsApp use the approved account phone; social handles have
no existing storage and remain null. Trusted-contact delivery is explicitly
unavailable; no notification endpoint or fake delivery receipt was added.

Gate questions, private answers, reflection, confirmations, exclusivity and
entry share a transactional service with HTML actions. Current-round input and
separate authenticated actions prevent one partner confirming for the other.
Both confirmations, prerequisites and entry agreements are checked again before
atomically creating Couple/ROAD/playbook/topics and completing the LockIn.
Retries cannot advance that couple twice. Text answers and partner-directed
Guru prompts remain private. Selected questions drive the gate analysis, avoiding
the old dead end where the selected-question UI could never satisfy an obsolete
all-fifteen-questions entry check.

Profile edits, contact responses, invitation actions, Next Level and gate writes
reuse shared services from web routes. Existing non-date HTML ceremony/face
simulation remains a legacy harness flow; mobile face simulation is default-off
and requires an approved account plus BETA_DATE_SIMULATION_ENABLED=1. Real
biometrics, payment processing and Guru narration remain unimplemented.

The database helper can defer per-row commits to an explicit connection-scoped
transaction, safely isolated between concurrent requests. PostgreSQL flag values
are normalized to the integer representation required by both schemas.
Historical happened=true encounters remain eligible; completing a new date also
preserves the after-date milestone when its plan becomes historical.

Validation covers three-user ownership/privacy, exact retries, question pacing,
home acknowledgements/revocation, reciprocal answers, mutual gate entry and an
injected rollback after partial legacy helper writes. PostgreSQL races cover
duplicate contact requests, simultaneous conversation creation and vision appends.
Final full isolated PostgreSQL run: **1,309 passed, 734 subtests passed**, no
skips, in 110.18 seconds. Temporary database and credentials removed afterward.

## Remaining sequence

7. Enrollment and API-only full-journey tests.

Email sender-domain authentication and live mobile token validation remain
separate Phase 3 items. The user reported successful SMS login and browser
REACH/logout/re-entry for the designated testers; no new live tests were run here.

## Block 6 — relationship tools, ROAD and later stages

Implemented locally 2026-09-14; OpenAPI 0.6.0 records the exact routes.
Couple-owned APIs expose current playbooks/topics/checkpoint status and own
weekly-report views; add custom/romance ideas, private concerns with author-only
sharing/closure, and actor-scoped expense self-reports. A private concern does
not appear in the partner's HTML or JSON. Expense reports never assert that the
other partner complied. Existing generated report fields are read when present;
automated weekly narration/report generation remains an unimplemented stub.

ROAD supports validated work/fitness/free blocks, dated obligations/travel,
removal, live explicit availability sharing, overlap, and selected vision stances.
Neither private routines nor unshared obligations cross to the partner. Inclusive
obligation dates remove that day's slots; invalidated shares disappear on reads.
Vision changes keep an audit receipt and require explicit partner disclosure.
Append requests use actor-scoped request IDs, so retries neither duplicate data
nor resurrect a deleted block. Existing HTML helpers use the same services.

Engaged and Married transitions require separate authenticated typed agreements
for the exact source/target stage, plus both payment prerequisites if enforced.
No client-supplied partner opt-in exists. The former two-checkbox HTML bypass is
replaced by a checkpoint screen. Stage advancement is atomic, replay-safe and
carries ROAD/playbook history forward; old stage agreements cannot authorize a
later transition. Face confirmation remains explicit approved-beta simulation,
not biometric verification. Payments are prerequisites, not a new checkout.

Either partner may initiate exit. Each separately acknowledges the interview and
submits or declines private feedback. Both feedback actions start the existing
generic Guru-synthesis stub and 14-day server-simulation-clock cool-off. After
expiry each verified partner returns to Dating independently. Raw feedback is
never sent to the other partner. There is no background overdue-exit adjudicator;
incomplete interview/feedback steps remain pending. Reuniting the same historical
Couple is not implemented; the Dating relationship-entry gate fails closed for
that existing couple rather than overwriting its history.

`JourneyAction` is an additive table in both schemas, registered in reset/drift
checks. It stores retry/audit receipts and actor expense/exit acknowledgements.
No production schema or data was accessed. The current production simulation
clock and absence of a real weekly runner remain unchanged.

Validation: **1,319 passed, 736 subtests passed** in the full isolated PostgreSQL
run (111.05 seconds, no skips). Races cover simultaneous stage advance, parallel
partner ideas and duplicate ROAD creation. Tests also cover two later stages,
private concerns, invalid/foreign ROAD writes, explicit sharing, failed-transition
rollback, exit privacy, cool-off and independent re-entry.
