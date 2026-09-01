# Intimacy Expectations, the "Next Level" Conversation & Invite Home — Build Spec

Supersedes Part B of `difficult-questions-invite-home-spec.md`. Read alongside
`relationship-stage-spec.md` and `dating-stage-spec.md`.

**Naming rules:** never "contract" — use playbook / plan / rules of engagement /
acknowledgement / disclosure. Platform is "Dare to Dream".

---

## The governing distinction

Everything in this spec rests on one line:

> **Expectation can be disclosed in advance. Consent cannot be given in advance.**

The platform's job is to make people **radically honest about what they expect**, early
and before they are alone together. It never records, implies, or manufactures consent to
intimacy — consent is present-tense, specific, and withdrawable at any moment by either
person, regardless of anything agreed beforehand.

This is not a limitation working against the goal. It is what makes the record credible:
a document that overclaims collapses under scrutiny and makes its holder look worse. A
narrow, honest disclosure record is the one that actually protects both people.

---

# PART A — Intimacy expectations in the Chemistry layer

Sexual expectation is one of the largest determinants of whether a relationship works, and
one of the least honestly discussed. Capture it as a first-class compatibility field, not
an afterthought.

## A1. What Chemistry captures

Mandatory at Relationship entry; editable at any time (chemistry genuinely evolves).

| Field | Options |
|---|---|
| `intimacy_pace` | slow · led by connection · open to physical intimacy early · waiting until married |
| `intimacy_importance` | how central physical intimacy is to them, 1–5 with a text note |
| `physical_boundary` | namaste · bow · handshake · side-hug · hug · cheek-kiss *(carried from Dating)* |
| `intimacy_notes` | free text: what they want a partner to understand |
| `health_openness` | willing to discuss sexual health and contraception: yes · when it's relevant · prefer not yet |

## A2. Surfacing mismatch early — the point of the whole thing

```
on_chemistry_update(pair):
    if pace_gap(a.intimacy_pace, b.intimacy_pace) >= MATERIAL:
        surface_to_both(
            "You two have described different expectations about physical intimacy.
             That's common and workable — but worth talking about now rather than
             discovering it in the moment."
        )
        offer(next_level_conversation)
```

- Surfaced **as soon as both have filled Chemistry** — before any escalation, before
  anyone is in a private space
- Framed as a **difference to discuss**, never as a failing on either side
- Never blocks progression; the couple decides
- **This is the mechanism that does most of the protective work in this spec** — a
  mismatch caught here never becomes a misunderstanding in a room

---

# PART B — The "Next Level" conversation

Guru-facilitated, reciprocal-unlock, user-initiated. Available once the pair has
completed the Week-2 lock-in and feedback.

## B1. Trigger

Either partner can open it, or Guru may offer it **once** when a material intimacy-pace
mismatch is detected. Guru offers; it never pushes, and it does not re-offer if declined.

## B2. The questions (reciprocal unlock — neither sees the other's answers until both have answered)

**Intent and meaning**
- What would "taking this to the next level" mean to you?
- What are you hoping for, and what are you unsure about?

**Pace**
- What pace feels right to you from here?
- Is there anything you want to happen *before* physical intimacy — meeting friends,
  family, more time, an exclusivity conversation?

**Boundaries**
- What are you not comfortable with, or not ready for?
- How would you want the other person to check in with you?
- How do you each want to be able to say "not now" without it being a big deal?

**Health and practicalities**
- Are you both comfortable discussing sexual health and contraception?
- Is there anything about protection or health you'd want agreed beforehand?

**The honest one**
- Is there anything you're saying yes to because you feel you should, rather than
  because you want to?

## B3. Guru's handling

- Presents questions neutrally; **no right answer** framing throughout
- Reveals both sets of answers only when both have answered
- Surfaces divergence as a conversation, never as a verdict
- **If one partner's answers indicate reluctance or pressure**, Guru privately reflects
  that back to *that person only*: "some of what you've written sounds like you may feel
  you should rather than you want to — that's yours to decide, and there's no wrong answer"
- **Never** encourages progression. Never says a couple is "ready".
- Declining any question is free and shown neutrally as "chose not to answer"

---

# PART C — Invite home, with honest expectation disclosure

## C1. Availability

Unlocks after the Week-2 lock-in and feedback. Either partner may propose. Never
suggested by Guru or the platform — user-initiated only, always.

## C2. The invitation carries an explicit expectation flag

The inviter states honestly what the invitation includes. This is the honesty mechanism:
nobody is ambushed, nobody has to pretend the subject isn't on the table, and the
recipient can decide with full information.

| `expectation_flag` | Shown to recipient as |
|---|---|
| `social_only` | "Time together at home — no expectation of physical intimacy" |
| `open_ended` | "Time together at home — where things go is open, and we'll each decide in the moment" |
| `intimacy_expected` | **"This invitation includes an expectation of physical intimacy"** |

The recipient sees the flag **before** responding, always, prominently.

## C3. What the acknowledgement records — and what it explicitly does not

Both partners see identical text and acknowledge separately, face-verified.

**It records:**
- Both are BGV-verified, identified adults
- A visit was proposed and agreed, at a stated date and time
- **What expectation was disclosed by the inviter, and that the recipient saw it before agreeing**
- Both saw identical safety guidance
- Timestamped, versioned, symmetric — both hold the same copy
- Optionally, that a trusted contact was informed

**Mandatory immutable text — verbatim, prominent, not editable or shortenable:**

> This records a planned visit and the expectations that were disclosed before it.
> **It is not consent to physical intimacy, and it cannot be.** Consent is given in the
> moment, for a specific thing, by a person who is free to change their mind — and it can
> be withdrawn at any time, by either person, no matter what was said or agreed before.
> Changing your mind is not a broken promise. It is your right, always.
> Either person may cancel this visit, or end it once it has begun, without explanation.

## C4. Guidance shown when `intimacy_expected` is selected

Shown to **both** parties before either acknowledges:

- Disclosing an expectation is honest and welcome. It is not, and can never be, agreement
  in advance — the other person decides in the moment, and so do you
- If either of you is unsure, this is the moment to say so. Postponing costs nothing
- Talk about protection and sexual health beforehand, not after
- If there is any ambiguity on the night, stop. Ambiguity is a reason not to proceed
- Alcohol changes the picture; a person who is heavily intoxicated cannot meaningfully agree
- Either of you may leave, or ask the other to leave, at any point

## C5. Flow

```
1. Inviter proposes date/time and selects expectation_flag
2. Recipient sees the flag prominently, plus rules of engagement + immutable text
3. Recipient: accept | decline | ignore          (all three free of consequence)
4. If accepted → both acknowledge separately, face-verified
5. If intimacy_expected → C4 guidance shown to both before acknowledgement
6. Optional: either shares plan with a trusted contact
7. Either may revoke at any point, before or during, no explanation, no penalty
8. Post-visit: private, separate check-in prompt to each
```

---

# PART D — What the record establishes in a dispute

State this plainly in the product and in the ToS, so expectations are correct:

**The record can show:** that two verified, identified adults agreed to meet at a stated
time; what expectation was disclosed and acknowledged beforehand; that both received
identical safety guidance; and the full contemporaneous in-app communication trail.

**The record cannot and does not show:** that consent to intimacy was given. It never
purports to. Consent existed or did not exist in the moment, and no document changes that.

**Why this narrow claim is the protective one:** advance-consent documents are legally void
and read as premeditation — they damage the person holding them. A disclosure record that
claims only what is true is credible, admissible as context, and survives scrutiny. The
protection for both parties comes from **verified identity, contemporaneous communication,
and honest disclosure** — not from a signature that pretends to bind a future decision.

---

# PART E — Data model

```
ChemistryEntry  { id, user_id, intimacy_pace, intimacy_importance, physical_boundary,
                  intimacy_notes, health_openness, updated_at }

NextLevelThread { id, pair_id, opened_by(user|guru_offer), question_key,
                  answer_a, answer_b, declined_a, declined_b,
                  answered_at_a, answered_at_b, revealed_at,
                  reluctance_flagged_to }        # private to that user only

HomeInvite      { id, pair_id, requester_id, proposed_datetime,
                  expectation_flag(social_only|open_ended|intimacy_expected),
                  flag_seen_by_recipient_at,
                  status(pending|accepted|declined|ignored|revoked|completed),
                  guidance_shown_a, guidance_shown_b,
                  ack_signed_a, ack_signed_b, face_verified_a, face_verified_b,
                  trusted_contact_notified_a, trusted_contact_notified_b,
                  revoked_by, revoked_at, acknowledgement_version }
                  # NOTE: no address field, by design
```

---

# PART F — Guardrails (enforce in code, not just UI)

- **No advance consent, ever.** No field, flag, or record may represent consent to
  intimacy. The immutable text in C3 cannot be edited, shortened, or omitted.
- **Revocation is always free** — before or during, by either party, no explanation, no
  penalty, no fault recorded, no effect on compliance rating or matching.
- **Declining or ignoring an invite has zero consequence** and is never surfaced to the
  other party as a rejection.
- **Guru never suggests** an invite home, never encourages progression, never tells a
  couple they are "ready".
- **Reluctance is surfaced privately** to the reluctant person only — never to their partner.
- **Reciprocal unlock** applies to every Next Level question.
- **No address stored.** The record holds consent-to-meet and time, never location.
- **Symmetric record** — both parties receive an identical copy, always.
- **Post-visit check-in is private** to each partner and never shared.
- **No appearance data. No chat. REACH stays sunset.**
- All acknowledgements are **versioned and auditable**; the text version is stored with
  each record so it is always clear what was actually shown.
