# Dream Contract — validation handoff

Everything a coding agent or QA engineer needs to turn the use-case catalogue into
executable tests, without re-deriving the product context.

**Readable version:** the Dream Contract Test Atlas (published artifact) — same content,
filterable by stage / kind / priority.

## What's in this bundle

| File | Purpose |
|---|---|
| `usecases.json` | Source of truth. 127 cases with full structure. Generate from this, never edit downstream copies. |
| `features/*.feature` | One Gherkin feature per stage, generated from the JSON. Drop into Cucumber / Behave / pytest-bdd / Playwright-BDD. |
| `build.py` | The generator. Edit the case data here and re-run to regenerate JSON + features. |
| `HANDOFF.md` | This file. |

Regenerate: `python3 build.py`

## Case schema (`usecases.json` → `cases[]`)

```
id         DTD-<STAGE>-<NNN>   stable; cite in tickets and test names
stage      Onboarding | BGV | Dating | Relationship | Engaged | Marriage | Cross-cutting
title      one-line summary
type       happy | failure | edge | abuse | guardrail
pri        P0 (blocks launch) | P1 (blocks GA) | P2 (can follow)
actor      who is acting
agents     which of REACH / ROAD / Playbook / Guru / Weekly Report are involved
contract   which contract (C0–C5) the case touches, and in what state
pre        precondition
action     the trigger
expected   [] assertions, most important first
given/when/then   the acceptance criterion, mirrored into the .feature files
notes      test-data hints and the reason the case exists
```

`stages[]` carries each stage's contract, exit gate, active agents and purpose.

## The stage / contract model these cases assume

| # | Stage | Contract | Gate out |
|---|---|---|---|
| 01 | Onboarding | C0 Intent Contract (self-attested) | C0 accepted + identity verified |
| 02 | BGV | C1 Verification & Disclosure Consent | required checks resolved |
| 03 | Dating | C2 Dating Contract (per match, dual approval) | mutual lock-in; REACH sunsets |
| 04 | Relationship | C3 Relationship Contract (dual approval) | mutual declaration + C4 |
| 05 | Engaged | C4 Engagement Contract (dual approval) | C5 approved |
| 06 | Marriage | C5 The Dream Contract (dual approval, annual review) | review / amend / exit |
| — | Cross-cutting | applies to C0–C5 | invariants |

## How to prioritise the build

1. **P0 + `guardrail`** (35 cases) — invariants that must never break. Write these as
   assertions in CI, not as manual test scripts. Several are best implemented as
   schema or data-flow checks that fail the build when a future field or consumer is added:
   `DTD-XCT-001` (no skin-tone classification anywhere), `DTD-XCT-002` (no raw rows to any
   agent), `DTD-DAT-007` (REACH input schema), `DTD-DAT-014` (date-photo consumers).
2. **P0 + `abuse`** — safety and bad-faith paths. `DTD-DAT-019`, `DTD-REL-020`,
   `DTD-MAR-007`, `DTD-ENG-010`. No LLM may sit in any of these decision paths.
3. **P0 + `happy`** — the flows that must work for a first cohort.
4. **P0 + `failure`**, then P1, then P2.

## Test-layer guidance by case type

- **`guardrail`** → unit / contract / static-analysis tests. Deterministic, run on every commit.
- **`happy` / `failure` / `edge`** → integration or end-to-end tests against a seeded
  two-user fixture.
- **`abuse`** → integration tests plus a manual red-team pass before each release.
- Any case asserting on **agent-generated language** (tone, framing, absence of a nudge)
  needs an LLM-output eval, not a string match. Build these as a small eval suite with a
  judge rubric derived from the case's `expected[]`, and keep a human review pass over
  sampled outputs. Applies to `DTD-DAT-003`, `DTD-DAT-006`, `DTD-XCT-012`, `DTD-XCT-014`,
  `DTD-REL-016`, `DTD-MAR-007`.
- **Adversarial prompting** is required, not optional, for every agent guardrail: the test
  must try to talk the agent past its boundary, not just observe it behaving.

## Fixtures worth building once

- `user.declared` / `user.verified` / `user.partially_verified` / `user.unverifiable`
- `pair.matched` (pre-C2), `pair.locked_in`, `pair.relationship`, `pair.engaged`, `pair.married`
- `pair.lateral_entry` (joins at Relationship or Marriage — REACH must never run)
- REACH input fixtures: `healthy`, `narrow`, `no_realistic_matches`, and one where the
  **sensitive lever has the largest delta** (the key `DTD-DAT-003` case)
- ROAD fixtures: overlapping availability, near-miss availability, solo travel in window,
  partners in different time zones incl. a DST crossing
- Contract fixtures: v3-approved-by-A, superseded v4, concurrent-approval harness

## Known open questions these tests do not settle

- Whether the optional self-declared appearance preference ships at all (`DTD-ONB-011`
  specifies the only acceptable mechanics *if* it does).
- The exact policy rule for an adverse criminal-record finding (`DTD-BGV-004`) — must be
  written down before it can be tested.
- The closure-window duration for `DTD-DAT-018`, the nudge cadence cap for `DTD-REL-012`,
  and the cooling period for `DTD-MAR-008` — all need a number.
- How a joint contract record survives one party's erasure request (`DTD-MAR-010`,
  `DTD-XCT-008`) — needs a documented, counsel-reviewed position.

## Source

Derived from the project's *Dating design principles*, *REACH (agent 01)* and
*ROAD (agent 03)* specs. Guardrail cases restate bright lines already decided in those
documents — they are assertions, not proposals, and should not be relaxed without
revisiting the reasoning there. Nothing here is legal advice; validate the consent,
verification and e-signature designs with counsel before build.
