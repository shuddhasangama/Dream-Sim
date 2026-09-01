# Stage use cases for testing & validation (v1.0)

Readable version: **Dream Contract Test Atlas** — https://claude.ai/code/artifact/fdea2e8b-c063-471f-868e-0001789e8187

127 use cases across Onboarding, BGV, Dating, Relationship, Engaged, Marriage plus cross-cutting invariants.
Each case: ID, actor, precondition, trigger, expected results, Given/When/Then, agents, contract touchpoint, test notes.
Machine-readable `usecases.json` + Gherkin `.feature` files were delivered in `dream-contract-validation.zip` for engineering handoff.

Derived from: datingdesignprinciples.pdf, agent1reach.pdf, agent3road.pdf.

## Contract model assumed

| # | Stage | Contract | Gate out |
|---|---|---|---|
| 01 | Onboarding | C0 - Intent Contract (self-attested) | C0 accepted + identity verified -> BGV unlocked |
| 02 | BGV | C1 - Verification & Disclosure Consent (user / platform / vendor) | Required checks resolved (verified or explicitly unverifiable) -> Dating unlocked |
| 03 | Dating | C2 - Dating Contract (per match, dual digital approval before first date) | Mutual lock-in -> Relationship unlocked, REACH sunsets |
| 04 | Relationship | C3 - Relationship Contract (dual digital approval) | Mutual declaration + C4 approval -> Engaged |
| 05 | Engaged | C4 - Engagement Contract (dual approval, families acknowledged) | C5 approved -> Marriage |
| 06 | Marriage | C5 - The Dream Contract (dual approval, annual review) | Annual review / amendment / dignified exit |
| — | Cross-cutting | Applies to every contract C0-C5 | n/a - invariants that must hold in every stage |

## Case index

| ID | Kind | Pri | Title |
|---|---|---|---|
| DTD-ONB-001 | happy | P0 | New user signs up and passes identity verification |
| DTD-ONB-002 | happy | P0 | User declares their Vision (end goal) |
| DTD-ONB-003 | happy | P0 | User declares Stats, marked unverified |
| DTD-ONB-004 | happy | P0 | Preferences split into fixed dealbreakers vs adjustable levers |
| DTD-ONB-005 | happy | P0 | Consent and practical preferences captured |
| DTD-ONB-006 | happy | P0 | User digitally accepts the C0 Intent Contract |
| DTD-ONB-007 | failure | P0 | User declines the Intent Contract |
| DTD-ONB-008 | failure | P0 | Identity verification fails on ID/selfie mismatch |
| DTD-ONB-009 | guardrail | P0 | Verification camera performs identity match only |
| DTD-ONB-010 | guardrail | P0 | No system-inferred appearance attribute exists anywhere in onboarding |
| DTD-ONB-011 | edge | P1 | Self-declared appearance preference, if the feature is enabled |
| DTD-ONB-012 | edge | P1 | Age-ineligible signup is blocked |
| DTD-ONB-013 | edge | P1 | Currently-married applicant declares their status |
| DTD-ONB-014 | abuse | P0 | Duplicate account on the same verified identity |
| DTD-ONB-015 | abuse | P0 | Applicant uploads someone else's ID |
| DTD-ONB-016 | edge | P2 | Abandoned onboarding resumes exactly where it stopped |
| DTD-ONB-017 | guardrail | P0 | DPDP consent is granular, not bundled |
| DTD-ONB-018 | happy | P1 | REACH's first reciprocity read after preferences are saved |
| DTD-ONB-019 | guardrail | P0 | REACH refuses to run out of phase |
| DTD-ONB-020 | edge | P2 | Vision edited after onboarding |
| DTD-BGV-001 | happy | P0 | User consents to an itemised verification scope |
| DTD-BGV-002 | happy | P0 | All checks pass and stats flip to verified |
| DTD-BGV-003 | failure | P0 | Declared income band does not match the verified band |
| DTD-BGV-004 | failure | P0 | Adverse criminal record finding |
| DTD-BGV-005 | failure | P0 | A check cannot be completed - unverifiable is not false |
| DTD-BGV-006 | edge | P1 | Partial verification lets the user proceed with visible gaps |
| DTD-BGV-007 | guardrail | P0 | The BGV vendor is never asked to capture or grade appearance |
| DTD-BGV-008 | guardrail | P0 | Raw verification documents never reach a match or an LLM agent |
| DTD-BGV-009 | abuse | P0 | Forged document submitted |
| DTD-BGV-010 | failure | P1 | User withdraws BGV consent mid-flow |
| DTD-BGV-011 | edge | P1 | Verification exceeds SLA |
| DTD-BGV-012 | edge | P2 | A life change makes a verified stat stale |
| DTD-BGV-013 | guardrail | P0 | Marital status verified without stigma labelling |
| DTD-BGV-014 | abuse | P1 | User revises a declared stat after a failed check |
| DTD-BGV-015 | happy | P1 | Match-facing visibility of a verified stat |
| DTD-BGV-016 | edge | P2 | Vendor outage |
| DTD-DAT-001 | happy | P0 | Weekly reciprocity read surfaces best-reciprocity matches first |
| DTD-DAT-002 | happy | P0 | What-if simulator shows the trade-off before anything changes |
| DTD-DAT-003 | guardrail | P0 | REACH never suggests widening nationality or religion |
| DTD-DAT-004 | happy | P1 | User widens a sensitive lever themselves |
| DTD-DAT-005 | guardrail | P0 | REACH never narrows and never touches dealbreakers |
| DTD-DAT-006 | failure | P1 | Nobody realistic is on the platform yet |
| DTD-DAT-007 | guardrail | P0 | REACH receives only aggregate integers |
| DTD-DAT-008 | happy | P0 | Dating Contract must be dually approved before a first date |
| DTD-DAT-009 | failure | P0 | One party declines the Dating Contract |
| DTD-DAT-010 | happy | P0 | Greeting and boundary preferences reach both parties before the date |
| DTD-DAT-011 | happy | P1 | Dietary preferences drive venue suggestions |
| DTD-DAT-012 | happy | P1 | In-app together photo verifies the date happened |
| DTD-DAT-013 | guardrail | P0 | The date photo is never mandatory |
| DTD-DAT-014 | guardrail | P0 | The date photo never enters any scoring or inference pipeline |
| DTD-DAT-015 | happy | P1 | Shared bill photo supports the agreed split |
| DTD-DAT-016 | happy | P1 | Post-date pass with an optional reason |
| DTD-DAT-017 | guardrail | P0 | The reason for a pass is never inferred from a photo |
| DTD-DAT-018 | failure | P1 | Ghosting after a date |
| DTD-DAT-019 | abuse | P0 | Safety incident reported after a date |
| DTD-DAT-020 | abuse | P0 | Fake date claim |
| DTD-DAT-021 | abuse | P1 | Pressure to move off-platform and skip the contract |
| DTD-DAT-022 | edge | P1 | Date cancelled or rescheduled |
| DTD-DAT-023 | happy | P0 | Mutual lock-in ends the searching phase |
| DTD-DAT-024 | guardrail | P0 | REACH invoked after lock-in |
| DTD-DAT-025 | edge | P1 | Lateral-entry couple never sees REACH |
| DTD-DAT-026 | edge | P2 | Concurrent matches stay isolated |
| DTD-DAT-027 | failure | P1 | A narrow dress-style preference gets an honest reality check |
| DTD-REL-001 | happy | P0 | ROAD setup runs once on entry to Relationship |
| DTD-REL-002 | guardrail | P0 | ROAD is not re-collected weekly |
| DTD-REL-003 | happy | P0 | Weekly availability update |
| DTD-REL-004 | guardrail | P0 | Availability sharing is off by default and never set by the agent |
| DTD-REL-005 | happy | P0 | Date suggestion only where both are genuinely open |
| DTD-REL-006 | guardrail | P0 | Guru never auto-books |
| DTD-REL-007 | edge | P1 | Solo travel stays private and blocks in-person suggestions |
| DTD-REL-008 | happy | P1 | Together travel is visible to both |
| DTD-REL-009 | guardrail | P0 | The calendar service owns persistence |
| DTD-REL-010 | happy | P0 | Relationship Contract drafted, amended and dually approved |
| DTD-REL-011 | failure | P0 | An amendment after the other party approved resets approval |
| DTD-REL-012 | failure | P1 | C3 left unapproved |
| DTD-REL-013 | happy | P0 | Relationship playbook generated |
| DTD-REL-014 | happy | P1 | A playbook item counts only when both confirm |
| DTD-REL-015 | abuse | P1 | Unilateral playbook completion |
| DTD-REL-016 | happy | P1 | Weekly Report is honest rather than flattering |
| DTD-REL-017 | guardrail | P0 | The Weekly Report never scores a person |
| DTD-REL-018 | failure | P0 | Breakup during the Relationship stage |
| DTD-REL-019 | edge | P1 | Stepping back from Relationship to Dating |
| DTD-REL-020 | abuse | P0 | Coercive-control signals in conversation |
| DTD-REL-021 | guardrail | P0 | Guru refuses to arbitrate a conflict |
| DTD-REL-022 | edge | P1 | Long-distance couple across time zones |
| DTD-ENG-001 | happy | P0 | Transition to Engaged requires mutual declaration and C4 |
| DTD-ENG-002 | guardrail | P0 | ROAD is not re-run at Engaged |
| DTD-ENG-003 | happy | P0 | Guru facilitates the hard topics |
| DTD-ENG-004 | happy | P0 | A disagreement is recorded, not smoothed over |
| DTD-ENG-005 | failure | P0 | An unresolved critical item blocks approval |
| DTD-ENG-006 | happy | P1 | Engagement playbook with validated completion |
| DTD-ENG-007 | happy | P0 | Dual digital approval is legally clean |
| DTD-ENG-008 | failure | P0 | Engagement called off |
| DTD-ENG-009 | edge | P1 | Family given limited, consented visibility |
| DTD-ENG-010 | abuse | P0 | Family pressure does not override the couple's consent |
| DTD-ENG-011 | edge | P1 | Mid-engagement amendment |
| DTD-ENG-012 | guardrail | P1 | Contracts are framed as guideline, not legal instrument |
| DTD-ENG-013 | edge | P2 | Cross-border or NRI engagement |
| DTD-ENG-014 | failure | P1 | A verified stat goes stale during the engagement |
| DTD-MAR-001 | happy | P0 | The Dream Contract is drafted and executed |
| DTD-MAR-002 | happy | P0 | Annual review is never auto-renewed silently |
| DTD-MAR-003 | happy | P1 | Romance suggestions continue after marriage |
| DTD-MAR-004 | happy | P1 | Weekly report shifts from formation to maintenance |
| DTD-MAR-005 | failure | P0 | One partner claims the contract has been breached |
| DTD-MAR-006 | edge | P1 | Life event triggers renegotiation |
| DTD-MAR-007 | abuse | P0 | Abuse disclosed in conversation |
| DTD-MAR-008 | failure | P0 | Separation or divorce |
| DTD-MAR-009 | guardrail | P0 | Guru never gives legal or financial advice |
| DTD-MAR-010 | edge | P1 | One partner leaves the platform |
| DTD-MAR-011 | happy | P2 | Milestone playbook items |
| DTD-MAR-012 | guardrail | P1 | Marriage is not blanket consent |
| DTD-MAR-013 | edge | P2 | Already-married couple joins directly |
| DTD-XCT-001 | guardrail | P0 | No skin-tone classification exists anywhere in the system |
| DTD-XCT-002 | guardrail | P0 | No agent ever receives raw user rows |
| DTD-XCT-003 | guardrail | P0 | Every agent enforces its own lifecycle |
| DTD-XCT-004 | guardrail | P0 | Contract records are immutable and fully versioned |
| DTD-XCT-005 | guardrail | P0 | Dual approval requires two distinct verified identities |
| DTD-XCT-006 | edge | P0 | Simultaneous approvals do not double-execute |
| DTD-XCT-007 | failure | P1 | Approval on a superseded version is rejected |
| DTD-XCT-008 | guardrail | P0 | DPDP access, correction and erasure across all stages |
| DTD-XCT-009 | guardrail | P1 | Consent is granular and independently revocable |
| DTD-XCT-010 | abuse | P1 | Contract approval requires re-authentication |
| DTD-XCT-011 | guardrail | P1 | Stage regression is always mutual and logged |
| DTD-XCT-012 | guardrail | P1 | Guru is a mirror, not a menu |
| DTD-XCT-013 | edge | P1 | Agent failure degrades honestly |
| DTD-XCT-014 | guardrail | P0 | No agent output ever scores or ranks a person |
| DTD-XCT-015 | guardrail | P1 | Per-field visibility holds at every stage |

## Open questions these cases surface (need a decision before they can be tested)

- Whether the optional self-declared appearance preference ships at all (DTD-ONB-011 specifies the only acceptable mechanics if it does).
- The exact policy rule for an adverse criminal-record finding (DTD-BGV-004).
- Numbers needed: closure window (DTD-DAT-018), nudge cadence cap (DTD-REL-012), cooling period before re-entry (DTD-MAR-008).
- How a joint contract record survives one party's erasure request (DTD-MAR-010, DTD-XCT-008) — needs a counsel-reviewed position.
- How C4 relates to C3, and C5 to C4: supersede, extend, or coexist (DTD-ENG-001).