# Phase 2A deployed validation — 2026-09-11

Deployment tested: `https://dream-sim-production.up.railway.app`, following
Phase 2A commit `df89ada`. Used only the two user-designated Bangalore test
accounts. Both were verified, Dating, and able to access REACH.

## Completed live checks

74 assertions passed; one validation assertion failed.

- Session login and authenticated identity/profile/REACH returned HTTP 200.
- An alternate user-id query did not change whose profile was returned.
- Verified accounts received the verified-only REACH scope flag.
- Rendered REACH HTML counts and slider ranges matched API values.
- Single-filter Any toggles, bulk Any toggles, age widening and range changes
  succeeded; their returned state matched a subsequent API read and rendered
  HTML counts/ranges.
- Invalid fields, unknown lever, wrong boolean type, reversed bounds,
  malformed JSON and non-JSON requests returned validation/media errors.
- Rejected requests left preferences unchanged.
- Each account's full original preferences object was restored and verified
  equal to its pre-test snapshot (not merely reset to defaults).
- Dashboard, REACH, stats and Vision HTML returned HTTP 200 with the brand.
- Logout made identity/profile/REACH return JSON HTTP 401.

These were HTTP/session integration checks, including rendered HTML
inspection. They do not constitute interactive browser or real-phone testing.
No verification, lock-in, date, payment or shared-clock transitions were made.

## Finding and correction

The API accepted a known widen lever that was absent from the user's available
filters. The existing handler then raised a ValueError, producing HTTP 500.
Live incident reference: `DC-C67V-89`. This was an intentional invalid-input
test, not a normal-user incident.

The correction validates that a widen/set-range lever exists in the signed-in
user's adjustable preferences before invoking the existing handler. It returns
HTTP 400 `validation_error`. This also prevents set-range from adding a filter
the profile has not unlocked. Existing web handlers and schema are unchanged.
A regression test covers both actions and verifies no preferences are changed.

Correction deployed and verified live after commit `2bda060`: unavailable-filter widen and set-range both returned HTTP 400 validation_error. The complete preferences object remained unchanged. Health, authenticated REACH and dashboard returned HTTP 200; identity after logout returned HTTP 401.

## Remaining coverage

- Pending-verification REACH scope: passed locally; not checked live because
  neither designated account is in that state.
- Mutual-lock-in and later-stage REACH HTTP 403: passed locally; not checked
  live because neither designated account is locked in or in a later stage.
- Full journey screen/interaction walkthrough beyond the four listed pages:
  not covered by this live run. Journey transitions are outside these
  non-destructive Phase 2 checks.

The correction deployment verification is complete. Pending-verification and locked-in/later-stage live coverage remains outstanding; local regression coverage passed.

Local validation of the correction: 1,208 tests and 707 subtests passed.

