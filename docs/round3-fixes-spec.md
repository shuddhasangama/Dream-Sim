# Mobile Build — Round 3 Fixes

Build spec for Claude Code. Read alongside `docs/mobile-journey-build-spec.md`,
`docs/mobile-ui-fixes-spec.md`, `docs/road-fixes-clock-spec.md`,
`docs/dating-stage-spec.md`, `docs/relationship-stage-spec.md`.

All UI work is in `mobile/src/` — shared JavaScript, one fix covers iOS and Android.

**Naming:** platform is **DhaShu**. Never "contract" — use playbook / plan /
agreement of understanding.

---

## 1. Chemistry save — still broken *(highest priority)*

Reported fixed in the last pass, but still failing: the UI shows **"Saved"** while
nothing persists. That message appearing on a failed save means success is being
reported regardless of the response — the worst kind of bug, because it hides itself.

**Diagnose properly, do not patch the symptom:**

1. Log the actual request and response — is the call fired at all? What status comes back?
2. Is the payload shape what the API expects? Compare against the web template's save path.
3. Is the response checked before showing "Saved"? It clearly isn't — fix that first.
4. Does the value survive a reload, and a force-quit + reopen?

**Requirements:**
- The success message must be driven by a confirmed successful response, never assumed
- On failure, show a clear error and preserve the user's selections
- Add a test covering the full round-trip: set → save → reload → still set

---

## 2. Remove the Stats screen

The standalone Stats screen is redundant — the Dashboard shows stats, and REACH links
to editing them.

- Remove it from the navigation
- Remove the screen and its route
- Ensure nothing else links to it

---

## 3. Edit Stats — not working from either entry point

Fields are not editable from the **Dashboard** or from **REACH**. Make both work:

- Tapping edit puts fields into an editable state with a clear save/cancel
- Use the existing PATCH endpoints; do not invent new ones
- Editing a previously-verified field drops it to `declared` and re-opens verification
  — tell the user this before they save
- Confirm persistence the same way as Chemistry: save → reload → still changed
- Add tests for both entry points

---

## 4. REACH

### 4.1 Age control
- The **vertical marker for the user's own age must sit on the horizontal track**,
  not float above or beside it
- Track range: **21 to 80**
- The user's age (38 in the test fixture) must fall visibly on that track

### 4.2 Kids filter
"Wants kids" and "Does not want kids" as two separate filters is duplicative and
unintuitive. Replace with **one** control offering the available options
(wants / doesn't want / open — whatever the API exposes). Read the options from the
API; do not hardcode them.

### 4.3 Missing filters
Height, weight, education, religion and others are still absent from "More filters".

**Enumerate every filter the API exposes and render all of them.** If the API returns
a filter, the UI offers it. Log the full filter list from the API during development
to confirm nothing is being dropped.

---

## 5. Week calendar

### 5.1 Wording
Inside the calendar cells, use **"RC Opens"** and **"RC Closes"**. The word
"Reality" inside a small cell is unreadable and adds nothing. Keep the full term in
the legend only.

### 5.2 Debrief scheduling
Debrief must be **scheduled relative to the date itself**, based on the confirmed
slot — not at a fixed weekly position. If a date is scheduled Saturday dinner, the
debrief appears after that, not on a generic Sunday marker.

### 5.3 Post-date sequence
After a date: **Debrief opens → if the pair returns to the pool, RC opens**. These are
conditional and sequential, not fixed calendar positions.

**Note:** how best to represent conditional, sequence-dependent events in a weekly
grid is a design question, not purely an implementation one. Build the scheduling
logic correctly first (5.2), and propose a visual treatment for review rather than
committing to one.

---

## 6. Guru

### 6.1 Date prep in the Dating stage
Surface **date preparation** while the user is in Dating — the courtesies content
from `dating-stage-spec.md` §8: punctuality, presence, respecting the stated greeting
preference, handling the bill gracefully, ending respectfully, plus the safety notes
and the in-app contact-exchange rule.

### 6.2 Add consent and playbook context
Give Guru a place to explain, in its own voice:
- The **consent-driven approach** — declining anything is always free and never
  surfaced to the other person as a rejection
- The **rules of engagement / playbook** relevant to the user's current stage

### 6.3 Open-ended help
Add an "anything I can help you with?" entry point offering the actions available at
the user's current stage.

**Constraint (unchanged):** Guru reflects and structures. It **never nudges
escalation** — never suggests progressing a stage, inviting someone home, or sharing
contacts.

---

## 7. Vision

### 7.1 The four pillars — exact structure

**Remove Relocation and Career entirely.** Vision is these four pillars only:

| Pillar | Required? | Sub-selections | Rule |
|---|---|---|---|
| **Intimacy** | **Mandatory** | Emotional · Physical | Pick one or both |
| **Travel together** | Optional | *(none)* | No detail required |
| **Kids** | Optional | Naturally · Surrogacy · Adoption | Pick as many as apply. **Requires Physical selected under Intimacy** |
| **Cohabitate** | Optional | Chores split · Expenses sharing | Pick one or both |

**Validation rules — enforce in the UI:**

1. **Intimacy is mandatory.** Sign-up cannot complete without it, with at least one of
   Emotional or Physical selected.
2. **At least one of** Travel together / Kids / Cohabitate must also be selected —
   so a minimum of **two pillars** overall.
3. **Kids is only selectable if Physical is selected under Intimacy.** If Physical is
   deselected, Kids and its sub-selections must be cleared, with a clear explanation
   rather than a silent reset.
4. **Kids and Cohabitate require at least one sub-selection each.** Picking the pillar
   without saying what it means is not a valid state.
5. **Travel together takes no sub-detail.**

Show the explanatory copy from the design: *"Travel together takes no detail now.
Kids and Cohabitate do, because picking either without saying what you mean says
almost nothing — and they are revisited together, at the Relationship stage, once it
is a decision rather than a preference."*

### 7.2 "Add Detail" — scope it correctly
Add Detail captures a pillar or sub-selection **not present in the original Vision** —
e.g. adding Cohabitate if it was never set, or adding Adoption alongside Surrogacy.
It is not a general edit affordance and must not allow removals.

### 7.3 "Declare a Change" — scope and gate it
- Supports **adding sub-selections** within a pillar (e.g. Kids → Surrogacy *and*
  Adoption) and **removing an existing** selection
- **Only editable while RC is open.** Locked outside that window — show why, don't
  just disable silently.
- Removing a selection must not be allowed to break the validation rules in §7.1
  (e.g. removing the last sub-selection under Kids, or dropping below two pillars)
- Once in **Relationship or beyond**, a declared change is **notified to the partner**
  — consistent with `relationship-stage-spec.md` §C1: Vision is additive-only by
  default, and a material reversal must be declared and disclosed, never silently edited

---

## Constraints (unchanged)

- Match the web templates in `templates/` as the visual source of truth
- No hardcoded constants — enums, filters and options come from the API
- Treat **409 as "already handled"**, never as a retry
- No appearance or skin-tone fields anywhere; no chat anywhere
- Keep all existing unit and e2e tests passing; add tests for every fix above
- Close resources opened in tests
- **Verify fixes actually work before reporting them done** — Chemistry was reported
  fixed once already and was not
