# Mobile Journey Build Spec — Phase 5, Steps 3 & 4

Build spec for Claude Code. Connects the remaining DhaShu journey screens in
`mobile/src/` to the Phase 4 JSON APIs, and adds phone navigation, error and
session handling.

Read alongside: `docs/phase-4-api-inventory.md`, `docs/openapi-phase4.json`,
`docs/dating-stage-spec.md`, `docs/relationship-stage-spec.md`,
`docs/difficult-questions-invite-home-spec.md`, `docs/intimacy-expectations-spec.md`.

**Naming:** platform is **DhaShu**. Never use the word "contract" — use playbook,
plan, agreement of understanding. Stages are the DREAM framework
(Dating → Relationship → Engaged → Married).

---

## 0. What already exists — reuse, do not rewrite

| File | What it does |
|---|---|
| `src/main.js` | App bootstrap, sign-in, dashboard render, `CapacitorHttp` transport |
| `src/session.js` | Token lifecycle, refresh rotation, `SessionVault` persistence |
| `src/style.css` | Existing design tokens and component styles |
| `src/preview.js` | Browser preview transport (dev only) |
| `tests/session.test.js` | 8 passing tests — **must keep passing** |

Extend these. Do not replace the transport, the session handling, or the auth flow.
Follow the existing style conventions in `style.css` rather than introducing a new
visual language.

---

## 1. Navigation shell (build first)

Everything else hangs off this.

- **Stack/tab navigation** in vanilla JS — no framework, no build-step change
- **Android hardware back** — handle via Capacitor `App.addListener('backButton')`;
  pop the stack, and on the root screen prompt before exiting
- **Loading states** on every async call — never a blank screen
- **Keyboard handling** — inputs must not be obscured; scroll into view on focus
- **Route source of truth:** `GET /api/v1/journey/status` returns current stage,
  pair data and allowed actions. **Derive navigation from it** — never infer stage
  client-side.

---

## 2. Screen → API mapping

### 2.1 REACH *(Phase 2 baseline endpoints)*

- `GET /api/v1/reach` — reciprocity read
- `POST .../widen`, `POST .../set-range` — what-if levers

Rules:
- Preserve counts, filters and locked-in access restrictions exactly as the API returns them
- **REACH sunsets at lock-in** — hide the entry point when `journey/status` says locked in
- Nationality and religion are user-controllable levers but **never** surfaced as
  suggestions (see `intimacy-expectations-spec.md` §C2 sensitive-lever rule)
- No appearance or skin-tone field anywhere

### 2.2 Week & Match *(Block 2)*

- `GET /api/v1/week` — current week state and revealed matches
- `POST /api/v1/week/prepare` — week setup

**Critical:** a separate atomic execution setup is required so repeated `GET /week`
calls do not duplicate transitions. Treat `GET` as read-only; never let a screen
re-render trigger a state change.

- Staggered reveals with colour-coded match slots — read slot/timing from the API,
  never hardcode the schedule
- Actions: express interest · pass · no action (window expiry)

### 2.3 Lock-in *(Block 2 & 5)*

- `POST /api/v1/matches/{id}/actions`

Lock-in is **created automatically on mutual interest**. There is no partner-picking
endpoint — do not build one. The client expresses interest; the server decides.

### 2.4 Date — calendar & ceremony *(Block 3)*

- Availability submission as structured `{day, meal_slot}` objects
- **Ceremony is multi-step and order-enforced:** playbook → sign → face

Each step must pass its payload **explicitly**, e.g. `{"step": "sign"}`. The server
validates sequence legality. Never skip, batch, or double-advance steps — the client
must not be able to bypass a signature check.

Payment opens only after the calendar slot is confirmed.

### 2.5 Feedback *(Block 4)*

- **Exactly two green flags** and **up to two red flags** required before submitting
- Decision: continue · relationship · pass
- **"One No is Enough"** — a single pass immediately releases the pair. Reflect this
  in the UI copy so the user understands the consequence before submitting.

### 2.6 Vision & Evolution *(Block 5 & 6)*

- JSON reads and patches only
- **Private partner entries are strictly protected.** Data is revealed only per
  explicit reciprocal disclosure rules — the client must never display an entry the
  API hasn't already disclosed
- Vision is **additive-only**: add granular detail, never delete. A material reversal
  goes through the declared-change path (see `relationship-stage-spec.md` §C1)
- ROAD setup on Relationship entry; sharing opt-in per entry, **off by default**

---

## 3. Error, session and state handling *(Block 1)*

Map these explicitly — each needs distinct user-facing behaviour:

| Status | Meaning | Client behaviour |
|---|---|---|
| **401** | Expired session | Attempt refresh via existing `session.js` rotation; if that fails, return to sign-in with a clear message |
| **409** | State conflict | The action was already processed, or the client is stale. **Do not retry blindly.** Re-fetch `journey/status` and re-render. Explain plainly: "This has already been handled." |
| **400** | Invalid request | Surface the server's validation message; do not invent copy |
| Network failure | Offline / timeout | Retry affordance, preserve entered data, never lose user input |

**Idempotency:** match decisions, agreement signing and feedback finalisation are
strictly transactional. Submitting a modified decision on an already-processed
transaction returns 409. Guard against double-taps and treat 409 as "already done,"
not as an error to retry.

---

## 4. Hard constraints

1. **No hardcoded constants.** Schedule slots, survey options, enums and blocked
   reasons are discovered from API read models. Do not duplicate Python constants
   in JavaScript.
2. **Simulation flags are visible.** Payment, BGV and face verification run as beta
   simulations. The UI must say so explicitly — never present a simulated check as
   a live one.
3. **No chat.** There is no messaging between matched users anywhere in the product.
4. **Consent-gating.** Nothing crosses between partners without explicit opt-in.
   Declining anything is consequence-free and never surfaced to the other party as
   a rejection.
5. **Guru never nudges escalation** — it reflects and structures; it does not
   suggest progressing, inviting home, or sharing contacts.

---

## 5. Testing

- Keep all 8 existing `tests/session.test.js` tests passing
- Add tests for: 409 handling (no blind retry), the two-green-flag feedback rule,
  ceremony step-order enforcement, and REACH being hidden after lock-in
- Extend `e2e/foundation.spec.js` to cover navigation and back-button behaviour
- **Close any resources opened in tests** — unclosed handles fail on Windows

---

## 6. Build order

Build and commit in this sequence so each stage is independently verifiable:

1. Navigation shell + `journey/status` routing + error/session handling
2. REACH + Week + Match + Lock-in
3. Date calendar + ceremony + feedback
4. Vision + ROAD + Guru entry

Run `npm test` after each. Do not proceed to the next if the previous is failing.
