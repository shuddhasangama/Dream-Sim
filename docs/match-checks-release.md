# Match check summaries and REACH filters — 3 November 2026

## Delivered scope

| Change | Implementation | Validation |
|---|---|---|
| Court/FIR match-card statuses | Active-case, current-environment exact checks; completed zero-candidate results qualify | Backend isolation, result semantics and authorized match API tests |
| Employment summary | Current confirmed / History found / Self-declared, with processing states | History cannot satisfy current-employment filter |
| Checked on | Real UTC evidence timestamp, date-only disclosure | Future/invalid dates cannot qualify |
| Like/Pass | Existing decision actions preserved | API and browser Pass regression |
| Employment category | Optional self-declared Stats choice | Validation, persistence and live-cycle freeze tests |
| REACH category | Any or selected categories; optional undeclared inclusion | Actual pool counts and weekly generation tested |
| REACH verified/freshness | Court + FIR + current employment; Any time / 90 / 180 days | All three required; legacy overall verified flag insufficient |

## User controls

In Home → Stats, choose an employment category and explicitly enable “Share check statuses and dates with matches.” Existing users default to no sharing. Only statuses and dates are disclosed: no documents, PAN, addresses, case records or employer names. Sharing can be withdrawn at any time; category edits follow the existing match/date freeze rules.

REACH → Employment & verification filters defaults to Any. “Verified checks only” requires a shared summary with verified Court and FIR plus confirmed current employment. Historical employment, self-declarations and missing proof do not qualify. This can exclude self-employed people without current-employment evidence. Freshness applies to all three checks using real time, independently of the simulation clock.

“Any for everything” bypasses the new filters without deleting saved choices. Saving the panel reapplies them. Existing match batches are not rewritten. REACH edits remain frozen during match review and date planning/debrief.

## Release boundaries

No new vendor calls, paid rechecks, database migration or Railway variables are required. Sandbox summaries are explicitly labeled. This does not change overall BGV approval, unlock matching, connect face capture, or restart Signzy checks. Device acceptance remains a tester step after installation.

## Automated checks

Mobile unit suite: 114 passed. Browser suite: 53 passed on the full run; the remaining existing selector test passed after removing ambiguous copy. Three new browser flows cover match decisions, filter persistence and Stats sharing. Backend targeted suites cover active-case ownership, environment isolation, consent withdrawal, exact check outcomes, operator review binding, freshness, generation, enrollment and REACH freeze rules.
