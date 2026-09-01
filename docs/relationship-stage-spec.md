# Dating Exit → Relationship Entry & Relationship Stage — Build Spec

Build spec for the simulation harness. Read alongside `dating-stage-spec.md`,
`dream-full-journey-build-brief.pdf`, and the five agent specs.

**Naming rules:** never "contract" — use playbook / plan / agreement of understanding /
rules of engagement. Stages are the DREAM framework. Platform is "Dare to Dream".

---

# PART A — Progressive disclosure during Dating

Two escalations unlock **after the second week's lock-in and feedback** — not before.
Both are mutual-consent, and both are consequence-free to decline.

## A1. The unlock ladder

| Point | State |
|---|---|
| Week 1 lock-in → date → feedback | Nothing extra unlocked |
| Week 2 lock-in → date → feedback | **Contact exchange** and **Invite home** both unlock |

```
unlocks_available(pair):
    return pair.completed_dates >= 2 and pair.feedback_complete_both
```

## A2. Contact exchange (phone / social media)

- Either partner can **request**; the other may **accept**, **decline**, or **ignore**
- Nothing is revealed unless accepted. Partial acceptance is allowed
  (e.g. share phone, not Instagram)
- Per-channel: phone · WhatsApp · Instagram · LinkedIn
- **Declining or ignoring carries no penalty** — no rating impact, no flag, no visibility
  to the other party beyond "not shared yet"
- Re-raisable later; rate-limit to one request per channel per week to prevent pestering
- Rationale shown in-app: exchange happens through the app so nobody is put on the spot
  in person

```
ContactRequest { id, pair_id, requester_id, channel, status(pending|accepted|declined|ignored),
                 requested_at, responded_at }
```

## A3. "Invite home" — rules of engagement

A significant escalation from a public-venue date. Treated with its own light playbook.

**Flow:** requester proposes → **rules of engagement** shown to both → recipient accepts,
declines, or ignores → if accepted, both acknowledge the terms → visit is logged.

**Rules of engagement (both must see and acknowledge):**
- Either person may change their mind at any time, before or during — no explanation owed
- The stated physical-boundary preference carries over and still applies
- No recording or photography without consent
- Either may leave at any point
- Share the plan with a trusted contact outside the platform
- In-app reporting and an emergency check-in remain available throughout

**Hard guardrails (enforce in code):**
- **Declining or ignoring must have zero consequence** — no compliance-rating effect,
  no flag, no reduced matching, no visibility as a "rejection"
- Cannot be requested before the Week-2 unlock
- Revocable by either party at any time up to the visit, without penalty
- One pending request at a time; rate-limited
- Never suggested or nudged by Guru — the platform does not encourage this escalation,
  it only provides safe structure if users choose it

```
HomeInvite { id, pair_id, requester_id, proposed_datetime,
             status(pending|accepted|declined|ignored|revoked),
             rules_ack_a, rules_ack_b, trusted_contact_shared }
```

---

# PART B — The Dating exit / Relationship entry gate

## B1. Two entry triggers

The gate can open in either of two ways:

1. **Guru checks in** — after a pattern of sustained lock-ins, Guru asks each partner
   privately: continue dating · progress to Relationship · share feedback and step back
2. **Either partner raises exclusivity** — can happen at any time, from either side

Neither trigger forces anything. Both route into the same gate sequence.

## B2. Gate sequence

```
1. Getting-to-Know Agreement closes         (Dating stage exit)
2. Stage-gate questionnaire                  (private, both partners — see B3)
3. Guru compares answers, surfaces gaps      (see B4)
4. Both confirm intent to progress           (mutual, either may decline)
5. Prerequisites completed                   (Vision / Stats / Chemistry — see B5)
6. Exclusivity acknowledged                  (both)
7. Consent block signed                      (face-verified, independently)
8. Partnership Vision opens                  (Relationship stage entry)
9. ROAD setup runs once                      (see Part C)
```

If either declines at step 4, the pair continues in Dating or exits — never forced forward.

## B3. The stage-gate questionnaire — the difficult questions

Asked **privately to each partner**, answers not shown directly to the other.
Free text plus a readiness scale where noted.

**Readiness & visibility**
- Are we ready to meet each other's friends? *(ready now / soon / not yet / unsure)*
- Are we ready to meet each other's family? *(same scale)*
- Would you update your relationship status on social media? *(yes / not yet / I'd rather not / I don't use it)*
- Who in your life already knows about this person?

**Intent & pace**
- What does moving into the Relationship stage mean to you, in your own words?
- What's your honest expectation on timeline from here?
- Are you dating anyone else, or open to? *(exclusivity check — answered before it's formalised)*

**The open question**
- **"What's on your mind that you still want to know from them before you move forward?"**
  *(free text — this is the most important field; it surfaces the unasked question)*

**Harder ground**
- What would make you step back from this?
- Is there anything you haven't told them that they'd want to know?
- What are you most unsure about?
- How do you each handle disagreement — and have you seen theirs yet?

**Practical**
- Do you expect family involvement, and when?
- Have you talked about money at all?
- Is there anything about your life circumstances that would surprise them?

## B4. Guru's gap analysis at the gate

Reuse the four-view gap mechanic from the Weekly Report. Guru compares the two private
answer sets and surfaces **divergence, not content**:

- Where readiness levels differ materially (e.g. one "ready now" on family, other "not yet")
  → surface as a conversation to have, not a problem
- Where one has an unasked question in the open field → prompt them to ask it
- Where exclusivity expectations differ → **flag as a must-resolve before proceeding**
- Never quote one partner's raw answer to the other; synthesize into neutral prompts

**Hard rule:** Guru does not block the gate. It surfaces. The couple decides.
Only an unresolved **exclusivity mismatch** produces a "resolve before continuing" state.

```
GateResponse  { id, pair_id, user_id, question_key, answer_text, readiness_scale }
GateAnalysis  { id, pair_id, divergences[], must_resolve[], guru_prompts[] }
```

---

# PART C — Prerequisites: Vision, Stats, Chemistry

At Relationship entry, previously-optional fields become **mandatory**.

| Layer | Dating | Relationship entry |
|---|---|---|
| **Vision** | Core fields required | Full detail required; granularity expected |
| **Stats** | Partly optional | All mandatory, verified where verifiable |
| **Chemistry** | Optional | Mandatory |

## C1. The additive-only Vision rule

**Vision may be refined, never quietly reduced.** Users add granularity over time;
they cannot silently remove or contradict a prior commitment.

```
Allowed  — ADD granular detail beneath an existing Vision element
           "wants children"  →  "wants children · 2 · within 3–4 years"
           "open to relocation"  →  "open to relocation · within India · not before 2028"

Blocked  — silently DELETE a Vision element
Blocked  — silently CONTRADICT a Vision element
           "wants children"  →  "does not want children"    [not a silent edit]
```

**Material reversal path.** A genuine change of mind must be possible — otherwise the
system forces dishonesty. So:

1. Reversal cannot be made as an ordinary edit
2. It requires an explicit **Vision Change Declaration**
3. The change is **disclosed to the partner** (the fact and the field, in the user's own words)
4. It routes to Guru for a conversation
5. Full version history is retained and visible to both

```
VisionEntry  { id, user_id, element_key, detail_text, added_at, parent_id }
VisionChange { id, user_id, element_key, from_value, to_value, declared_at,
               disclosed_to_partner, guru_conversation_id }
```

Implement `add_vision_detail()` (free) and `declare_vision_change()` (gated, disclosed).
There is no delete operation.

## C2. Stats at Relationship entry

All mandatory: age, height, profession, income band, education, diet, marital history,
location, languages. Verified fields carry their badge; unverifiable fields are marked
"not verified" — never as false.

Stats **can** be updated (life changes), but a change to a previously-verified field
drops that field to `declared` and re-opens its verification.

## C3. Chemistry at Relationship entry

Mandatory. Individually addable and updatable at any time — this is the one layer that is
freely editable, because chemistry genuinely evolves.

Captures: intimacy goals, vibes they want to keep alive, love-language style,
communication preference, what makes them feel appreciated.

Feeds Guru's **Keep Romance Alive** pillar and the Weekly Report's vibes section.

---

# PART D — Relationship stage mechanics

## D1. Entry actions

```
on_relationship_entry(pair):
    close getting_to_know_agreement
    require exclusivity_ack from both
    require consent_block signature (face-verified, independent, per partner)
    open Partnership Vision
    run ROAD setup (once)
    activate Guru four pillars
    schedule weekly report
    REACH remains sunset
    stage_week_index = 0        # 16-week window
```

## D2. ROAD — set once, carried forward

Set at entry, referenced for all 16 weeks. **Not re-collected weekly.** Carries forward
unchanged into Engaged and Married (re-runnable if the couple chooses, never forced).

| Letter | Captures | Stored in |
|---|---|---|
| **R — Routine** | Work pattern, fitness pattern | Stats |
| **O — Obligations** | Recurring commitments: self, friends, family, professional | Calendar |
| **A — Availability** | Open time projected across the window; shareable per-week | Calendar |
| **D — Dates** | Connect proposals drawn from availability | Calendar |

**Travel** is a distinct calendar entry type with three modes:
`solo` (private) · `partner_solo` (visible only if shared) · `together` (joint)

**Sharing is opt-in per entry, off by default.** The agent never sets the `shared` flag.

## D3. Guru's four pillars (activate at entry)

| Pillar | Mechanic |
|---|---|
| **1 · Air & Resolve** | Two-step. Step 1 private: partner airs a difference → Guru comforts → offers reference material. Step 2 **consent-gated**: only if they agree, Guru informs the partner and mediates. Auto-tag each difference `new` or `repeated`. |
| **2 · Keep Romance Alive** | Draws on latest intimacy goal + vibes + playbook entries, or something new. User-initiated or surfaced at the mid-week checkpoint. New ideas writeable back to the playbook. |
| **3 · Expense Handling** | Simple yes/no compliance check against the playbook's expense strategy. Captures new goals. No bill-scanning at launch. |
| **4 · Mediator** | Standalone invoke, **and** the shared engine Pillar 1 step 2 calls. |

**Mid-week checkpoint** sweeps all four pillars. **End-of-week** produces the report.

## D4. Weekly report

Qualitative, **no numeric score**. Fixed order:
appreciation first → sorted this week → still sorting (tagged new/repeated) →
four views (own / Guru-on-you / combined / Guru-on-pair) → **the gap** →
vibes & romance → expenses → opt-in resources.

Surfaces and tracks; heavy or repeated topics route to the Mediator, never resolved inline.

## D5. Relationship playbook (three tiers)

| Tier | Contents |
|---|---|
| **Generic** (everyone) | Communication & conflict (incl. keep-it-off-social-media), emotional ownership, debt transparency (not income/property), quality time, extended family, values, when to bring in Guru |
| **Specific** (Vision-unlocked) | Household & shared space, shared expenses, children, career & relocation — only the ones their Vision selections unlock |
| **Custom** (Guru-assisted) | Anything the couple adds themselves |

Plus the **bold consent block**: enforceability disclaimer + platform jurisdiction only,
signed separately by each partner with face verification. Re-taken at Engaged and Married.

## D6. The 16-week window

Soft checkpoint at the end — Guru checks in. No forced decision. Three paths presented
with equal weight: progress toward Engaged · continue in Relationship · part ways.

---

# PART E — Data model additions

```
StageGate      { id, pair_id, trigger(guru_checkin|exclusivity_raised),
                 opened_at, status, resolved_at }
GateResponse   { id, pair_id, user_id, question_key, answer_text, readiness_scale }
GateAnalysis   { id, pair_id, divergences_json, must_resolve_json, guru_prompts_json }
ContactRequest { id, pair_id, requester_id, channel, status, requested_at, responded_at }
HomeInvite     { id, pair_id, requester_id, proposed_datetime, status,
                 rules_ack_a, rules_ack_b, trusted_contact_shared }
VisionEntry    { id, user_id, element_key, detail_text, added_at, parent_id }
VisionChange   { id, user_id, element_key, from_value, to_value, declared_at,
                 disclosed_to_partner, guru_conversation_id }
ChemistryEntry { id, user_id, key, value, updated_at }
```

Extend `Couple` with: `exclusivity_ack_a`, `exclusivity_ack_b`, `stage_week_index`,
`partnership_vision_id`.

---

# PART F — Guardrails (enforce in code)

- **Declining costs nothing.** Declining or ignoring a contact-exchange or invite-home
  request has zero effect on compliance rating, matching, or visibility. Never surfaced
  as a rejection.
- **Guru never nudges escalation.** It does not suggest inviting someone home, sharing
  contacts, or progressing stages. It surfaces and structures; the couple decides.
- **Vision is additive-only.** No delete operation exists. Reversals require an explicit,
  partner-disclosed declaration.
- **Gate answers stay private.** Guru synthesizes divergence; it never quotes one partner's
  raw answer to the other.
- **Guru does not block the gate** — except an unresolved exclusivity mismatch, which
  produces a must-resolve state.
- **Consent block is signed independently per partner**, face-verified; neither is bound
  until both sign.
- **ROAD sharing is opt-in per entry, off by default**; the agent never sets it.
- **No appearance data anywhere.** No chat anywhere. REACH stays sunset post lock-in.
- **Escalations are rate-limited** — one pending request per channel, to prevent pestering.
