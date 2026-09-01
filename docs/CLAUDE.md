# Dare to Dream — Simulation Harness

Local simulation of the DREAM framework. Python + SQLite. No mobile, no real
BGV, no payments — this simulates product LOGIC only.

## Specs (read these before building)

- docs/dream-full-journey-build-brief.pdf — data model & state machine
- docs/agent-*.pdf — the five agent specs
- docs/stage-use-cases-testing-validation.md — 127 test scenarios
- date-contract-sample.md — contract sample

## Non-negotiable rules

- Never use the word "contract". Use playbook / plan / agreement of understanding.
- Stages: Dating → Relationship → Engaged → Married (the DREAM framework).
- REACH runs ONLY pre-lock-in. It sunsets at mutual lock-in.
- No appearance/skin-tone data anywhere. Not in the schema, not in matching.
- Matching, reciprocity and cadence are DETERMINISTIC — no LLM calls.
  Only agent narration calls the API (added later, step 6).
- Consent-gated: nothing crosses between partners without explicit opt-in.

## Conventions

- SQLite at data/dream.db, plain SQL (no ORM) for readability
- Every module gets a matching test file
- Seeded randomness so runs are reproducible
