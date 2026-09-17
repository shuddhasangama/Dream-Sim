# Mobile Build — ROAD, Fixes & Simulated Clock

Build spec for Claude Code. Read alongside `docs/mobile-journey-build-spec.md`,
`docs/mobile-ui-fixes-spec.md`, `docs/relationship-stage-spec.md`,
`docs/phase-4-api-inventory.md`.

All UI work is in `mobile/src/` — shared JavaScript, one fix covers iOS and Android.
Task 7 requires backend changes as well.

**Naming:** platform is **DhaShu**. Never "contract" — use playbook / plan /
agreement of understanding.

---

## 1. ROAD (the deferred Step 3 gap)

Previously deferred because `journey/status` points at the full couple-summary
endpoint (`/api/v1/couples/{cid}`) — a large payload covering playbook, differences,
checkpoints and exits — and the preview fixture never advances past Dating, so it
was unreachable and untestable.

**Do this in order:**

1. **First, make it reachable.** Extend the preview fixture (`src/preview.js`) so a
   mocked user can be advanced into Relationship stage. Without this there is no way
   to develop or test ROAD.
2. **Read the couple-summary payload carefully** and build only the ROAD slice —
   do not try to render the whole payload in one screen.
3. **Build ROAD per `relationship-stage-spec.md` §D2:**
   - **R — Routine** (work, fitness) → stored with Stats
   - **O — Obligations** → calendar entries
   - **A — Availability** → shareable per-week, **opt-in, off by default**
   - **D — Dates** → connect proposals drawn from availability
   - **Travel** as a distinct entry type with three modes: `solo` (private) ·
     `partner_solo` (visible only if shared) · `together`
4. **Set once at entry, carried forward** to Engaged and Married. Not re-collected
   weekly. Re-runnable if the couple chooses, never forced.
5. **The client must never set an entry's `shared` flag on the user's behalf.**

---

## 2. Chemistry does not save

Selections on the Chemistry screen are not persisting. Diagnose and fix:

- Confirm the save request is actually fired (network log)
- Confirm the payload shape matches what the API expects
- Confirm the response is handled and state updated
- Add an explicit saved/failed indicator so a silent failure is visible to the user
- Add a test covering the save round-trip

---

## 3. REACH heading — revert

Change the heading back to plain **"REACH"**. Remove "Reality Check" from the screen
heading, nav item and any button label added in the previous pass.

---

## 4. Sign-up — investigate and report before building

**Do not assume.** Determine and report back:

- Is there a self-service sign-up path, or is the beta **invite-only** via the
  `EnrollmentDraft` / `enrollment_admin` flow?
- Can a brand-new phone number, on a device that has never run the app, complete
  registration end to end — or must the number be pre-enrolled server-side first?
- If pre-enrolment is required, what is the exact admin step to enrol a new tester?

If sign-up is incomplete, list precisely what is missing rather than building
speculatively. Note that `EnrollmentDraft` uses multi-section optimistic locking and
returns **409 on stale edits** — the client must handle that, not retry blindly.

---

## 5. "More filters" is incomplete

REACH's "More filters" does not expose all available filters. Add the missing ones —
including **Religion, Height, Weight, Waist** and any others the API exposes.

- **Discover the filter list from the API**, do not hardcode it. If the API returns a
  filter, the UI must offer it.
- Apply the same consistent visual treatment as the existing filters (one pattern for
  all, per `mobile-ui-fixes-spec.md` §5)
- Nationality and religion remain user-controllable but are **never suggested** by
  the system

---

## 6. Editing Stats

Make Stats editable from **two entry points**:

- The **Dashboard** — an edit affordance on the Stats section
- **REACH** — where a missing or limiting stat is flagged, offer inline editing there

Rules:
- Editing a previously-verified field drops it back to `declared` and re-opens its
  verification — reflect that clearly in the UI before the user saves
- Use the existing PATCH endpoints; do not invent new ones

---

## 7. Simulated clock (testing only)

Allow moving through days and hours of the week for testing, while production always
uses real time.

### Design — server is the authority

**The client must never be able to set its own time.** A user who could would be able
to reveal matches early, bypass review windows, or break the weekly cadence. So:

**Backend:**
1. Add an environment variable, default **off**:
   `DHASHU_SIMULATED_CLOCK=false`
2. When `false` (production): all time comes from the real system clock. Any override
   supplied by a client is **ignored**, and the API reports
   `"simulated_clock": false`.
3. When `true` (testing only): the API accepts an offset or explicit datetime
   override, and reports `"simulated_clock": true` plus the current simulated
   day/hour in `GET /api/v1/journey/status`.
4. Centralise this in a single clock module. **No other code may call
   `datetime.now()` directly** — everything goes through the clock abstraction, or
   the simulation will be inconsistent.

**Mobile client:**
5. Always display the **current day and hour of the week** in the Week screen, read
   from the API — not computed on the device.
6. Show day/hour stepping controls **only when the API reports
   `simulated_clock: true`**. Never render them otherwise, and never infer the flag
   from a build variable alone.
7. Label the controls clearly as simulation, consistent with how other beta
   simulations (payment, BGV, face verification) are surfaced.

**codemagic.yaml:**
8. Add a build variable so the behaviour can be changed per build without code edits:
   ```yaml
   environment:
     vars:
       DHASHU_SIMULATED_CLOCK: "false"
   ```
   This is a convenience switch for the build. It does **not** replace the server-side
   gate — both must be true for controls to appear.

---

## Constraints (unchanged)

- Match the web templates in `templates/` as the visual source of truth
- No hardcoded constants — enums, slots, filters and options come from the API
- Treat **409 as "already handled"**, never as a retry
- No appearance or skin-tone fields anywhere; no chat anywhere
- Consent-gated: nothing crosses between partners without explicit opt-in
- Keep all existing unit and e2e tests passing; add tests for new behaviour
- Close resources opened in tests
