# Guided sign-up and accelerated beta walkthrough

For the optional **action-driven pair rehearsal**, see [async-rehearsal.md](async-rehearsal.md).
It uses `DHASHU_ASYNC_TEST=true`: a personal 12-minute introduction followed by
waiting for partner actions, instead of this document's shared one-shot timer. Keep the two modes distinct; action mode takes precedence.

Shared implementation for the Android and iOS Capacitor applications. Changes
remain local until the backend is deployed and both mobile bundles are rebuilt.

## Guided sign-up

Home offers **Log in** and **Sign up**. Both use the existing phone OTP and
approved-account association. No profile is read before successful authentication;
an unknown number receives the same generic request response as before.

Log in goes straight to Dashboard. Sign up opens **Vision → Stats → Chemistry**,
prefilled from the authenticated person's profile. Existing profile endpoints
save edits, so existing validation, ownership, disclosure, RC change windows and
BGV re-check rules still apply. This is simulated onboarding for existing invited
profiles, not public account creation or a verification bypass. Unchanged steps
can be continued without writing anything. Unsaved edits block progression until
saved or explicitly discarded. Saved steps survive application restarts; the
walkthrough position does not. A restored session opens Dashboard.

## Shared test timetable

| Real elapsed minutes | Simulated time | Purpose |
| --- | --- | --- |
| 0 | Monday 10:00 | REACH / Reality Check |
| 3 | Monday 12:00 | Match 1 |
| 6 | Tuesday 12:00 | M1 closes / Match 2 |
| 9 | Wednesday 12:00 | M2 closes / Match 3 |
| 12 | Wednesday 18:00 | M3 closes / weekend Slots |
| 15 | Thursday 12:00 | Overlap and plan selection |
| 18 | Thursday 18:00 | Agreement |
| 21 | Latest saved weekend date start, rounded up | Date |
| 24 | That date's Debrief opening, rounded up | Flags and decision |
| 27 | Sunday 21:00 | RC, when lock-in has ended |
| 30 | Next Monday 12:00 | Cross RC close at 11:00; next cycle |

The last jump crosses Monday 11:00 and lands at 12:00; these cannot be two
separate three-minute checkpoints at the same elapsed minute. The run then
**stops**, rather than continually expiring weeks while testers are away.

All users in the deployment share the clock. When multiple pairs select
different dates, jumps 21/24 use the latest saved date in the chosen week. This
keeps the clock coherent across partners; earlier dates may already have their
Debrief open at minute 21. Completed/cancelled plan rows are retained in the date
calculation so finishing a date does not rewind time. When there is no saved
weekend plan, these two jumps remain at Thursday 18:00. Sunday 21:00 and next
Monday still occur at minutes 27/30. Plan eligibility and outcomes remain subject
to the existing services. No match selection, availability, alignment, signatures,
payment, verification, consent, debrief or lock-in release is fabricated.

This is a fast clock, not an automatic user-action script: complete each task
within its interval. There is no automatic pause for an unfinished partner.
Use a fresh test week and preassigned tester accounts; old unresolved lock-ins
are not reset. Do not enable on a deployment serving ordinary live users.

## Operator activation (not performed by this change)

Use a dedicated beta backend/database. Configure these **backend** variables:

```text
DHASHU_SIMULATED_CLOCK=true
DHASHU_ACCELERATED_TEST=true
DHASHU_TEST_START_UTC=<scheduled start as ISO 8601 with UTC offset, e.g. ...Z>
DHASHU_TEST_START_WEEK=<positive week number for this run>
```

Week 1 starts 2026-01-05. Choose the week containing the test plans you intend to
use, or a fresh week for fresh matches. The start must include a timezone. Pick a
future start so everyone can complete sign-up before the first match appears.
Before the start, the clock remains at Monday 10:00. Example to calculate a UTC
start ten minutes ahead in **Windows PowerShell** (prints a value only):

```powershell
(Get-Date).ToUniversalTime().AddMinutes(10).ToString("yyyy-MM-ddTHH:mm:ssZ")
```

Before enabling, validate the configuration in the target environment:

```bash
python -c "import accelerated_clock as a; print(a.settings()); print(a.metadata())"
```

Absolute start time survives process restarts and is shared by every worker.
No background scheduler, recurring Codemagic build, client timer mutation or
database migration is needed. Reads derive time without modifying the database.
The authenticated journey/status response adds `accelerated_test` metadata.
Manual clock mutation receives 409 while the automatic clock is active.

The mobile app checks server time every 15 seconds while visible, and on resume.
It reloads the current screen when time changes, unless an edited form or playing
video would be interrupted. In that case a notice offers an explicit refresh.
Each user action still gets the server's current-state validation. Polling does
not require the mobile manual-clock build flag to be enabled.

To return to real time, turn **both** simulation flags off. Turning off only
acceleration returns to the previous file-backed manual clock, which may be an
earlier week. Do not reuse a simulated test database for real customer journeys.

## Video and platform builds

### Calendar and profile polish

- Week's **How the week works (short video)** opens the existing
  `/media/calendar-explainer.mp4`. Playback and the missing-file fallback are
  tested separately. The new Home video is a separate walkthrough.
- Dashboard Vision's **Add detail** and **Declare a change** start collapsed.
  The guided sign-up keeps those editors expanded to aid the walkthrough.
- **Choose Marriage** adds every Vision pillar and its choices, with Kids set
  to Naturally. It does not add Adoption/Surrogacy, remove previously declared
  choices, change the journey stage, or supply consent. Removing an existing
  choice still uses the disclosed-change workflow. The new authenticated
  `POST /api/v1/profile/vision/presets` is transactional and request-idempotent.
- Age, height, weight and waist use one shared track for min/max labels,
  range thumbs and the person's vertical marker. Positioning uses DOM style
  properties compatible with the production CSP instead of blocked inline
  HTML styles. Tests cover both 375px and 430px widths.
- REACH has only **Have kids** / **Don't have kids** for existing children.
  They are mutually exclusive; neither selected means no children filter.
  Unknown existing-children values do not satisfy either explicit choice.
  Future-parenting compatibility remains in Vision. Legacy `wants_kids` and
  `no_kids_wanted` tags are retained in stored records but no longer filter
  candidates or appear as active filters, preventing invisible constraints.
  Existing frozen weekly match batches are not regenerated by this change.

`mobile/public/media/how-it-works.mp4`: 90 seconds, 1600×900, H.264/yuv420p,
fast-start, silent with burned-in explanatory text and optional English VTT.
Includes local-preview screenshots and the complete timetable. No real tester
details or live provider calls were used. Home and Dashboard expose it at the
top; it loads on expansion, has playback controls and never autoplays.

Source screenshots can be recreated from the shared UI:

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2\mobile
node scripts/capture-how-it-works.mjs
python scripts/render-how-it-works.py
```

Rendering requires Pillow and imageio-ffmpeg; screenshot capture uses installed
Playwright/Edge. Intermediates are in ignored `mobile/artifacts/how-it-works/`.
The old calendar-explainer.mp4 remains separate and unchanged.

Rebuild both existing Codemagic workflows after reviewing and pushing the code:
`android-play` for the signed AAB and `ios-testflight` for the IPA. Both build
the same web source and bundle the same video. A Railway deployment alone cannot
update an installed native app. Native archive/device validation must be done
through those builds; this Windows task does not claim an iOS archive or device run.

No deployment, account association, real messages or clock activation was
performed while implementing this change.

## Local validation — 2026-09-22

- SQLite regression: 1,391 passed, 27 PostgreSQL-only skips; 755 subtests.
- Disposable loopback PostgreSQL regression: 1,418 passed; 755 subtests.
  Includes concurrent Marriage preset retries and the existing journey races.
  The helper stopped PostgreSQL and removed its temporary data/credentials.
- Mobile unit tests: 45 passed. Browser E2E: 26 passed, using local mock data.
  Includes guided sign-up persistence, direct login, strict-CSP scale geometry,
  mutually exclusive existing-children filters, clock refresh preserving drafts,
  Marriage and collapsed editors, both actual MP4 players, and video fallback.
- Production web bundle builds successfully. No native device, TestFlight,
  Play Store, real OTP or production-backend test was performed.
- A stale PostgreSQL Vision test was updated to the current structured detail
  service. The API-only happy-path test now explicitly mocks the existing face
  simulator's random result; dedicated failure-path tests remain in place.
