# Mobile Build — Round 4 Fixes

Build spec for Claude Code. Read alongside `docs/round3-fixes-spec.md`,
`docs/mobile-journey-build-spec.md`, `docs/dating-stage-spec.md`,
`docs/relationship-stage-spec.md`.

All UI work is in `mobile/src/` — shared JavaScript, one fix covers iOS and Android.
Item 5 requires backend work as well.

**Naming:** platform is **DhaShu**. Never "contract" — use playbook / plan /
agreement of understanding.

---

## 1. Edit Stats — "Age should be a whole number" on untouched field *(bug, do first)*

Editing Stats fails validation on **Age**, a field the user never edited.

Diagnose properly:
- Is Age being sent as a string, a float, or with whitespace when untouched?
- Is the whole Stats object being PATCHed rather than only changed fields?
- Is a number input coercing `38` into `"38"` or `38.0` on read?

**Requirements:**
- **Send only fields the user actually changed.** A partial PATCH avoids re-validating
  untouched data and is the correct fix, not a coercion patch on Age alone.
- Coerce types correctly where a field *is* edited.
- Validation errors must name the field and say what's wrong, inline next to it.
- Add a test: open edit, change one unrelated field, save, confirm success.

---

## 2. Fold Vision and Chemistry into the Dashboard

Vision and Chemistry are set-once, rarely-changed data. Having them behind separate
nav items scatters the user's own information.

- Move both onto the **Dashboard** as **collapsible sections**
- Section headers **Vision** and **Chemistry** in bold, collapsed by default
- **Functionality stays identical** — same controls, same validation, same save
  behaviour as the standalone screens. This is a relocation, not a redesign.
- Remove both from the top navigation
- Result: Dashboard is the single place for everything about the user — stats,
  vision, chemistry

---

## 3. REACH — Age marker position

The vertical marker showing the user's own age does not sit at the correct position
on the horizontal track.

- The marker must be **positioned proportionally** to the user's age within the
  21–80 track (38 sits at roughly 28% along, not centred or offset)
- The marker must render **on** the track, not above or beside it
- Verify with several ages (21, 38, 60, 80) that the position is correct at each end
  and in the middle

---

## 4. Group verified fields; shorten the re-verify message

**Age, Education, Nationality, Profession and Salary band** are BGV-verified.

- **Group them together** in the Stats display, visually distinct from self-declared
  fields, with a single shared "verified" treatment rather than a badge repeated
  per field
- **Condense the re-verification warning** into one short line covering the group —
  e.g. *"Editing a verified field re-opens its BGV check."* Not a paragraph, and not
  repeated per field.

---

## 5. Sign-up — capture existing children *(backend + client)*

Sign-up must ask whether the user **already has children**.

- This is distinct from the Kids pillar in Vision, which is about *wanting* children.
  Do not conflate them.
- Capture it in the enrolment flow with whatever detail the API supports (yes/no, and
  count if the backend models it)
- **Add the field to the backend** if it doesn't exist — schema, API and validation
- Make it available as a REACH filter if the API exposes filters generically

---

## 6. Calendar — match close labels

Tuesday, Wednesday and Thursday mornings should read **"Match 1 closes"**,
**"Match 2 closes"**, **"Match 3 closes"** respectively — mirroring the reveal
labels, so the open/close pairing is legible at a glance.

Abbreviate as needed to fit (`M1 closes`), but never truncate mid-word.

---

## 7. Calendar — explainer video

The weekly cadence is not self-explanatory. Add an embedded short video explaining
the calendar workflow.

- Place it near the existing "What each one means" expander
- **Build the player and placement now**; the video file itself will be supplied
  later — use a placeholder and make the source path configurable
- Must not autoplay, and must not block the calendar from being used

---

## 8. Calendar — "Prepare this week"

Clarify or remove. Determine what `POST /api/v1/week/prepare` actually does, then:

- **If it's a real user action** — label it accordingly and explain what it does
  before the user taps it
- **If it's internal setup** the app should call automatically — remove the button and
  call it at the right point in the flow
- **If it's redundant** — remove it

Report which of the three it is rather than guessing. Do not route it to Guru unless
the endpoint genuinely does something Guru owns.

---

## 9. Guru — collapsible sections

"Before you meet" and best-practice content should be **collapsible**, matching the
Dashboard treatment in §2. Collapsed by default, bold headers, expand on tap.

---

## 10. Guru — surface the consent approach

Embed the consent-driven approach in Guru as a preview of how Dating works:

- Declining anything is always free, carries no penalty, and is never surfaced to the
  other person as a rejection
- Contact details are exchanged **in-app, when both choose** — never asked for in person
- The stated greeting/physical-boundary preference is shown before you meet and is
  expected to be respected

**Constraint (unchanged):** Guru reflects and structures. It **never nudges
escalation** — never suggests progressing a stage, inviting someone home, or sharing
contacts.

---

## Constraints (unchanged)

- Match the web templates in `templates/` as the visual source of truth
- No hardcoded constants — enums, filters and options come from the API
- Treat **409 as "already handled"**, never as a retry
- No appearance or skin-tone fields anywhere; no chat anywhere
- Keep all existing unit and e2e tests passing; add tests for every fix above
- Close resources opened in tests
- **Verify fixes on a real run before reporting them done**
