# Action-driven pair rehearsal

An optional Dating test policy shared by Android and iOS. Each unmatched verified
Dating user starts a persisted personal introduction on their first authenticated
app entry (POST /rehearsal/start); GETs remain read-only. This start is not reset
by logout, another device, app restart or repeated calls. Offline time counts.

| Elapsed since first entry | Simulated checkpoint |
| --- | --- |
| 0 minutes | Monday 10:00, REACH |
| 3 minutes | Monday 12:00, Match 1 |
| 6 minutes | Tuesday 12:00, Match 2 |
| 9 minutes | Wednesday 12:00, Match 3 |
| 12 minutes and later | Wednesday 18:00, availability; wait for pair actions |

Matches are still subject to existing eligibility and a maximum of three.
Revealed choices do not expire while the other person catches up. An early
mutual match retains each user's remaining introduction; planning requires both
introductions to finish. Existing pairs with no introduction record keep their
current action-driven progress and are not restarted.

## What testers experience

- At minute 12 an unmatched user can save weekend slots in the test banner on
  Home/Dashboard or Week. These are personal draft availability, not a confirmed
  date or a payment entitlement. Alignment remains in the pair calendar.
- Mutual interest creates the pair and atomically transfers the saved slots.
  If pairing races a draft save, it either transfers the saved draft or rejects
  the late draft with a refresh to the pair calendar. Drafts are consumed once.
- One person's interest does not reserve the other person or force a reciprocal
  match. Candidate generation does not guarantee reciprocal slots.
- Alignment and availability stay saved until the partner responds. Both must
  supply alignment and an overlapping slot before a plan can be created.
- The agreement waits for both signatures and the existing verification steps.
- After both agreements, each partner chooses **Ready for simulated date**.
  The shared pair clock advances only after both choose it.
- Each then chooses **Ready for Debrief**. Both must respond before Debrief opens.
  These acknowledgements are navigation for a rehearsal, not proof of meeting,
  consent to contact, a no-show finding or a Debrief decision.
- Debrief remains open while the other person is away. Existing rejection,
  cancellation and outcome rules remain in force. A rejection can end the pair;
  it is not necessary to obtain the other person's approval to stop dating.
- Both choosing continue preserves date history and starts the next date cycle
  in the pair's next simulated week, with fresh readiness acknowledgements.
  There is no automatic reset or repeating 30-minute timer. Only the initial
  personal introduction is timed; later stages wait for actions.

This policy covers the Dating walkthrough. It does not accelerate later
relationship-stage waiting periods. It does not turn a cancelled/rejected
match into a fresh match in the same batch. Normal future-week/restart management
remains an operator task; do not delete users or reassign their accounts to restart.
The old calendar/video is a reference for normal cadence, not a deadline in this
mode. Mobile copy labels this explicitly. The readiness buttons are in the mobile
app (and its web bundle); the legacy server-rendered web UI has no new buttons.

## Activate after deploying and updating the mobile test builds

On the **existing Dream-Sim service**, set:

```text
DHASHU_SIMULATED_CLOCK=true
DHASHU_ASYNC_TEST=true
DHASHU_TEST_START_WEEK=39
DHASHU_ACCELERATED_TEST=false
```

Apply/deploy these backend settings after publishing this code. Start week is
captured at first entry for new unmatched users; an existing active pair keeps its saved week/date.
DHASHU_TEST_START_UTC is not read in this mode; the old value can remain unused.
No expiration date is imposed: leave this mode on for the intended test period,
then switch modes deliberately. All testers on this backend use this policy.

The additive RehearsalReady and RehearsalIntro tables are created by the existing database initializer
on both SQLite and PostgreSQL. No manual data deletion or migration command is
needed. Existing profile data and phone associations are unchanged. Existing
confirmed dates require the new readiness actions before Debrief in this mode.

Rebuild both mobile platforms from this source through the existing Codemagic
workflows. TestFlight and Play testers must update: older apps do not show the
readiness buttons. The banner must say **Test journey · at your own pace**.
Mobile checks for partner progress every 15 seconds while visible and on resume,
preserving dirty forms and playing videos. Refresh progress is also available.

Quick verification: A saves availability; B returns later and sees the same pair.
After signing, A chooses readiness. Confirm no advancement until B chooses it.
Repeat for Debrief. A's Debrief must not expose B's private flags or reason.
An unrelated tester must see neither this pair nor its readiness.

## Revert the behaviour without reverting data

Set `DHASHU_ASYNC_TEST=false` and apply/deploy. New mobile UI disappears based
on server metadata; no mobile rollback is required. Leave RehearsalReady in place
so re-enabling resumes readiness. No records are automatically deleted.

Then explicitly choose the desired clock:

- Real time: `DHASHU_SIMULATED_CLOCK=false`, `DHASHU_ACCELERATED_TEST=false`.
- Existing one-shot test: simulated=true, accelerated=true, and a fresh valid
  start UTC/week. Old UTC values can immediately finish that run.
- Legacy manual simulation: simulated=true, accelerated=false. This returns to
  the saved manual clock file; it does not copy the action-driven pair clock.

Turning off the mode preserves data but restores normal timing rules. A saved
test date can therefore become past/closed under the restored clock. Finish or
review active test journeys before switching; rollback is not a data rewind.

## Updating an existing deployment

Push this change, deploy Railway, and rebuild both Android and iOS from the same
commit. No new Railway variables are required beyond the four listed above.
Older mobile builds cannot start the introduction or edit pre-match draft slots.
Do not change the start UTC to restart a user: it is ignored. Disabling this mode
preserves intro rows; re-enabling counts the real elapsed time since their start.
This is a one-time introduction per user, not a fresh timer on every login.

## Implementation boundary

`async_rehearsal.py` owns the policy and readonly state projection. Small hooks
in clock selection, match status and preparation are guarded by enabled(). The
flag is ineffective without DHASHU_SIMULATED_CLOCK. Action mode takes precedence
over accidental simultaneous activation of the old accelerated mode.

`POST /api/v1/rehearsal/date-plans/{pid}/ready` accepts only
`{"step":"date"}` or `{"step":"debrief"}`. The actor comes from authentication,
never JSON. Ownership, active verified Dating state, confirmed/current plan and
step ordering are rechecked within the existing planning transaction. A unique
key and transaction serialization make duplicate/concurrent submissions safe.
Reads are read-only. No readiness field exposes partner feedback or identity.
Draft endpoints use the authenticated actor, reject unknown JSON fields, validate
slots through the shared planning validator, and are gated by the test flag.

Journey responses add nullable `async_rehearsal` metadata with an optional
server-provided action. `mobile/src/rehearsal.js` contains the separate mobile UI
and progress-key helper. All ordinary eligibility/payment/consent validation
remains in the existing shared services.

## Previous baseline validation (23 September 2026)

- Full Python suite: 1,397 passed, 29 skipped; 757 subtests passed.
- Disposable local PostgreSQL suite: 13 passed, including concurrent readiness,
  rollback, planning, weekly matches and date outcomes.
- Mobile unit tests: 47 passed. Playwright preview tests: 27 passed.
- Production web bundle built successfully; git whitespace checks passed.

Coverage includes delayed partner actions, two successive dates, duplicate and
concurrent submissions, foreign access, private feedback, mode rollback and
preservation of unsaved mobile edits. Browser tests use the local preview mock;
API tests use isolated databases. Native Android/iOS builds and live Railway
validation have not been performed for this change.


## Timed introduction validation (24 September 2026)

Full Python suite: 1,400 passed, 30 skipped, 759 subtests passed.
Isolated localhost PostgreSQL: 14 passed (including concurrent introduction
starts/draft replacements and transactional transfer rollback). Mobile unit:
47 passed. Browser preview suite: 28 passed. Production web bundle built.

Tests cover exact 3/6/9/12-minute boundaries, late partner entry, unchanged start
on repeated calls, read-only GETs, early-pair waiting, draft validation/privacy,
transfer on mutual interest, payment prerequisites, and existing date-cycle flows.
Browser tests use preview mocks; native devices and live Railway are not tested.
