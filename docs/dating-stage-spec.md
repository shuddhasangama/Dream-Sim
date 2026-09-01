# Dating Stage — Detailed Build Spec

Build spec for the simulation harness. Read alongside `dream-full-journey-build-brief.pdf`
and the five agent specs. This document is authoritative for Dating-stage mechanics.

**Naming rules:** never "contract" — use playbook / plan / agreement of understanding.
Stages are the DREAM framework. Platform is "Dare to Dream".

---

## 1. The weekly cadence — exact timeline

The Dating stage runs on a fixed weekly rhythm. Every user in a city is on the same clock.

| When | What happens |
|---|---|
| **Mon 12:00** | Match 1 revealed. Review window opens (~22 hrs). |
| **Tue 12:00** | Match 1 window closes. Match 2 revealed. |
| **Wed 12:00** | Match 2 window closes. Match 3 revealed. |
| **Wed evening** | Match 3 window closes. **Availability calendar opens** for anyone with mutual interest. |
| **Thu 12:00** | Availability calendar closes. |
| **Thu evening** | **Matches go live** — "Date is Set". Date plans generated for confirmed pairs. |
| **Fri** | Dates: **Coffee and Dinner slots only** (working day). |
| **Sat / Sun** | Dates: Breakfast · Lunch · Coffee · Dinner slots. |
| **Sun night** | Date feedback opens. Lock-in decisions. REACH refreshes for next week. |

Implementation notes:
- Model a `SimulationClock` with day + hour so windows can be tested deterministically.
- Staggering is per-match, not per-user — everyone sees Match 1 on Monday.
- A user who does not act within a window is treated as **no response** (not a pass) —
  track separately for the compliance signal.

---

## 2. Match availability — variable, honest count

**Rule: up to 3 matches per week, but the actual number is based on that user's honest
available pool.** Never fabricate a match to fill a slot.

```
determine_match_count(user, pool):
    eligible = [u for u in pool if mutual_open(user, u)
                                and u.bgv_status == 'verified'
                                and not u.locked_in
                                and u not in user.recent_matches (last 8 weeks)]
    return min(3, len(eligible))
```

- If `eligible` is 0 → user sees the honest REACH message, no matches this week.
- City is a rough proxy for depth (Delhi may sustain 3, Bangalore 2, Pune 1) but the
  calculation is **per-user**, driven by their filters — not a per-city constant.
- Match slots are colour-coded in the UI as Match 1 / 2 / 3 (see §11 for dark-theme colours).

### BGV gating (two lanes)

| Lane | State | What they can do |
|---|---|---|
| **Lane A — Verified** | BGV complete | Full weekly matches, stats visible, calendar, dates |
| **Lane B — Unverified** | Skipped or in progress | **Vision-level browse only.** Stats hidden (theirs and others'), **no calendar, no dates, no matches** |

Lane B users can resume verification any time and join Lane A at the next week boundary.
This is a real product state, not a dead end — model it explicitly.

---

## 3. Profile review & expressing interest

For each revealed match, the user sees:
- Vision (values / long-term alignment) — the primary basis
- Verified Stats (age, height, profession, income *band*, education, diet)
- Verified badges; unverifiable fields shown as "not verified", never as false
- Photo (identity-verified) — **presented after the Vision, never as the headline**

Actions: **Express interest** · **Pass** (optional reason) · **No action** (window expires)

**Transparency rule:** if one party expresses interest, the other is shown that fact —
but it never forces a decision. No pressure mechanics, no countdown shaming.

---

## 4. Mutual lock-in

Mutual lock-in is the pivotal event of the Dating stage.

```
on_mutual_interest(user_a, user_b):
    create LockIn(a, b, week)
    clear all other candidates for BOTH users this week   # short-circuits the week
    open calendar for the pair
    REACH sunsets for both                                 # no longer searching
    no parallel dating permitted while locked in
```

- Only **mutual** interest triggers this. One-sided interest never does.
- Once locked in, both users' remaining match slots are cleared for the week.
- If the date does not happen (cancelled, no-show), the pair returns to the pool at the
  next week boundary with the reason recorded.

---

## 5. Calendar process

Opens Wed evening for locked-in pairs, closes Thu 12:00.

**Each partner submits availability** across the Fri/Sat/Sun slots:

| Day | Available meal slots |
|---|---|
| Friday | Coffee, Dinner |
| Saturday | Breakfast, Lunch, Coffee, Dinner |
| Sunday | Breakfast, Lunch, Coffee, Dinner |

- System finds the **overlap**. If multiple overlaps, the pair picks one.
- If **no overlap** → offer next weekend, or return both to the pool (their choice).
- Venue: **pre-agreed** (system suggests, dietary-aware) or **"decide together"**.
- Dietary preferences drive venue suggestions (veg / non-veg / Jain / halal / vegan).

**Payment opens only once the calendar slot is confirmed — never before.**

---

## 6. Date plan generation & playbook signing

On calendar confirmation, generate the **date plan** (see `agent-2-playbook.pdf` for the
full 12-section structure). Auto-filled fields:

- Date & time (from confirmed slot)
- Meal type · Venue / cuisine
- **Bill split**: 50/50 · alternate-treats · host-pays · pay-your-own
- Per-date fee or subscription coverage
- Cancellation & no-show terms (notice window, fee — from config)
- Plan scope: **single date instance only**, expires on completion

### Selections carried into the plan

Both partners' selections appear in the signed plan so each has explicitly seen them:

| Selection | Options |
|---|---|
| **Greeting / physical boundary** | namaste · bow · handshake · side-hug · hug · cheek-kiss |
| **Dietary** | veg · non-veg · Jain · halal · vegan · allergies |
| **Dress style** | casual · smart casual · formal · elegant (soft signal) |
| **Bill split** | as above |

### Signing flow

1. Plan rendered for review
2. Acknowledgement checkboxes: code of conduct & courtesies · cancellation policy ·
   "this is not a relationship or a contract" · platform liability
3. **Face verification + digital signature — per partner, independently**
4. **Neither party is bound until both have signed**
5. On dual signature → date confirmed, payment opens

Simulation note: stub the biometric call as `verify_face(user) -> bool` with a
configurable success rate. Do not implement real biometrics.

---

## 7. Guru's role in the Dating stage (limited)

Guru's **four pillars are Relationship-stage only**. In Dating, Guru appears in three
narrow places:

| Moment | Guru's role |
|---|---|
| **Before the date** | Courtesies note: be on time, be present (phone away), respect the stated greeting preference, handle the bill gracefully, end respectfully regardless of outcome. Also: contact details are exchanged **in-app when both are ready**, never asked for in person. |
| **After the date** | Facilitates feedback capture. Neutral, non-leading prompts. |
| **On a pass** | If a reason is volunteered, receives it as free text. **Never infers a reason, never asks about appearance.** |

Guru does **not** mediate, does not run pillars, does not generate weekly reports in
Dating. All of that begins at Relationship entry.

---

## 8. Dating best practices (surfaced by Guru pre-date)

Content to show, framed as shared etiquette — never as rules or threats:

**Courtesies**
- Arrive on time; message through the app if delayed
- Be present — phone away, genuine attention
- Basic table courtesy, and politeness to venue staff
- Honour the agreed bill split gracefully — no scene over payment
- End the date respectfully regardless of romantic outcome

**Safety**
- Meet at the confirmed public venue
- Share date details with a trusted contact outside the platform
- In-app reporting is available at any time

**Boundaries**
- The other person's stated greeting preference is shown before you meet — respect it
- No recording or photographing without consent
- Contact exchange happens in-app, by mutual choice

---

## 9. The date, and after

**During (simulated):**
- Optional **in-app together photo** — mutually consented, never mandatory.
  Purpose: date-verification + shared memento. **Never enters any scoring or inference.**
- Optional **shared bill photo** — supports the agreed split.

**After (Sunday night):**

| Action | Behaviour |
|---|---|
| **Both want to continue** | → Lock-in for Relationship stage transition |
| **One passes** | Optional free-text reason. The other is told plainly and kindly. |
| **Both pass** | Both return to the pool next week |
| **Ghosting** (no response by close) | Flagged after the closure window; counts toward compliance |
| **Safety incident reported** | Routed to trust & safety; both accounts flagged pending review |
| **Fake date claim** (photo/bill absent + dispute) | Flagged for review |

**Compliance rating (service-platform style):**
- Each partner rates conduct and adherence to the plan
- Pattern of low ratings / verified misconduct / plan violations →
  warning → temporary suspension → permanent removal
- Independent of any single match's romantic outcome
- Late cancellations and no-shows feed the same signal

---

## 10. Data model additions

Extend the existing schema:

```
Match          { id, user_id, candidate_id, week, slot(1|2|3), revealed_at,
                 window_closes_at, action(interest|pass|none), pass_reason }
LockIn         { id, user_a, user_b, week, created_at, status }
Availability   { id, lockin_id, user_id, day, meal_slot }
DatePlan       { id, lockin_id, datetime, meal, venue, cuisine, bill_split,
                 fee, cancel_notice_hrs, cancel_fee, status }
Signature      { id, dateplan_id, user_id, signed_at, face_verified }
DateOutcome    { id, dateplan_id, happened, together_photo, bill_photo,
                 a_decision, b_decision, a_reason, b_reason }
ComplianceEvent{ id, user_id, type(rating|no_show|late_cancel|report|violation),
                 value, week, notes }
```

---

## 11. UI notes (dark theme)

Match slots are colour-coded. The original light-theme colours need dark equivalents:

| Slot | Dark-theme treatment |
|---|---|
| Match 1 | Lavender accent `#B9A3C9` on `#171320` card |
| Match 2 | Blue accent `#8FB4E8` on `#111C28` card |
| Match 3 | Gold accent `#E8B54D` on `#241F12` card |

Standard system: background `#0C0912`, cards `#14101C`, borders `#241E2E`,
primary action green→teal `#3DDC97`→`#2CC5C5`, Guru avatar coral `#FF6B5E`→`#FF9548`,
gold Fraunces-italic eyebrow labels, IBM Plex Mono uppercase micro-labels.

---

## 12. Guardrails (enforce in code, not just UI)

- **No appearance data anywhere.** No skin-tone field, no inference, no photo analysis.
  The photo pipeline does identity verification only.
- **No chat.** There is no messaging between matched users at any point in Dating.
  Match → lock-in → calendar → real date.
- **REACH sunsets at lock-in** — assert this; it must not run for locked-in users.
- **Consent-gated:** together photo, bill photo, and contact exchange all require
  mutual opt-in. Default off.
- **Payment gated:** never opens before calendar confirmation.
- **Dual signature gate:** the date is not confirmed until both partners have signed
  independently.
- **Honest counts:** never pad match slots. Zero matches is a valid, honest outcome.
