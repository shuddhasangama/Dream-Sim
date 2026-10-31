# Signzy coverage and decision brief

Prepared 30 October 2026. Based on local requirements, adapter code and saved sandbox receipts; no new provider calls. Recommendation: proceed with a controlled pilot and scoped commercial discussion, conditional on written coverage and acceptance criteria. Full verification coverage and production readiness are not established.

Launch target confirmed by the user: end November / early December 2026. Prioritise a small, reliable and easy-to-operate scope using available checks, with future additions. Missing optional coverage is not itself a launch blocker; claim verification only for the specific fields actually supported and validated.

## What DhaShu requires

Core field list in bgv.py / stats_edit.py: age, education, nationality, profession and salary/income band. Identity/name/face, address and court checks also appear in the onboarding/website scope. Marital-status verification appears in planned use cases. Do not assume self-reported values are independently verified.

| Data element | Evidence and gap | Ask Signzy |
|---|---|---|
| Legal name, DOB and age | PAN Simple/Extensive return 403. DOB appears in the supplied history schema but is not a substitute for an authoritative identity check. | Resolve PAN access; identify authoritative source and comparison policy, including name variations and DOB mismatch. |
| Identity document authenticity + selfie ownership/liveness | Face Smart mapper/simulator only; no connected live transport. PAN validity alone does not bind a live person to an identity. | Exact product, endpoint, reference-document checks, approved mobile capture SDK, replay/deepfake controls and accessible fallback. |
| Nationality/citizenship | No implemented check or tested evidence. PAN/UAN possession does not establish citizenship. | Accepted documents, source authenticity, Indian/foreign coverage and explicit returned fields. |
| Education | No implemented check or tested evidence. | Degree, institution, course, year and completion verification; supported institutions, document-only versus source verification, fallback and SLA. |
| Current employer | HTTP 200 and employment summary received; returned flags require interpretation. | Source freshness, exit flags and reconciliation when sources disagree. |
| Profession / designation | Employer record does not establish occupation, job title, professional licence or practice status. | Designation/registration verification; self-employed, freelancer and non-EPFO paths. |
| Past employment | HTTP 200; 2 records; limitedOutput=false. No automated comparison. That flag does not prove a complete career history. | Source coverage, date/tenure units, gaps, overlaps, multiple UANs and completeness limitations. |
| Salary / income band | No income-verification operation implemented/tested. Employment history is not salary proof; UAN passbook is untested and cannot be assumed to equal total compensation. | Specific product and evidence: salary credits, employer confirmation, Form 16/ITR or another supported route; gross/net/CTC and non-salaried income treatment. Return only band to matches. |
| Address | Address is currently court-search input, not independently checked. | Current versus document address, source, recency, digital/physical verification options. |
| Court records | Exact and possible search submissions return 200; earlier result lookup returned 200/zero cases. Latest two result lookups pending. No court-clearance decision. | Coverage of courts/time periods, case roles/status, identity disambiguation, pending/completed response, empty-result meaning and manual review. A case match is not proof of guilt. |
| Marital status | Planned requirement; no implemented/tested check. Court/PAN data cannot establish a comprehensive unmarried status. | What can actually be source-verified, jurisdiction gaps, supporting documents and what must remain self-declared. |
| Phone/email ownership | Not established by the tested Signzy operations; supplying or receiving a number is not OTP verification. | Confirm separate ownership verification route and responsibilities. |

## Meeting agenda and requested outputs

1. Agree the minimum launch scope, distinguishing required checks from optional enrichment.
2. Obtain a written matrix: field -> product/API -> authoritative source -> input/consent -> output -> geography/population coverage -> limitation -> turnaround -> price.
3. Resolve both PAN 403 failures; confirm sandbox/production entitlements and approved fixtures. Exercise UAN passbook and complete both latest court result lookups.
4. Run an agreed acceptance set: salaried EPFO user, self-employed user, non-EPFO employee, no employment record, name/DOB mismatch, ambiguous court match, partial result and provider timeout. Measure accuracy/coverage with an agreed truth set, not HTTP success alone.
5. Confirm product use for matchmaking, permission to show only derived field badges/bands to matches, consent wording, biometric treatment, retention/deletion, data locations/subprocessors and incident support in the proposed agreement.
6. Price the complete person-level package: successful/no-hit/failed/pending calls, retries and court result polling; minimums, onboarding fees, support SLA and refresh charges.
7. Record a named owner, ETA and acceptance evidence for each gap. Avoid a full long-term commitment until the essential fields and unit economics are demonstrated.

## Our implementation work remains

Add approved identity and missing field integrations; wire new employment history into app flow if wanted; implement approved court completion/reconciliation; establish review/correction/appeal and deletion processes; connect verified field evidence to profile badges with expiry/recheck rules. Current checks do not update overall BGV approval or unlock matching. Local code and offline tests do not establish deployed production behaviour.

## Opening statement

We have seven API operations implemented. Six have been exercised in sandbox: four returned successful responses, two PAN operations are blocked by 403, and UAN passbook remains untested. We now need to validate coverage against our actual fields: age, education, nationality, profession and income band, alongside identity and court checks. We want to leave with a field-by-field scope, access-resolution dates, acceptance tests and a complete per-user quote.

## Decision gate

Proceed to a limited pilot now. Commit to full launch only after required field coverage, PAN access, live identity/liveness, court review, production permissions, agreed acceptance tests and operational/commercial terms are confirmed. If Signzy cannot cover an essential field, narrow the launch claim, use a supplementary/manual provider or reconsider a single-vendor approach.

Vendor public identity/background product descriptions: https://www.signzy.com/ . These advertise product categories; they do not establish our account entitlement, endpoint suitability or field-level coverage.

## Court filters actually tested

Receipt inspection confirms all three saved individual_search requests sent only name, address and matchType. No caseCategory or party type was sent. On 28 October exact matching was tested; on 29 October both exact and possible matching returned HTTP 200. We did not explicitly test criminal-only or civil-only calls. The adapter accepts a single caseCategory value, civil or criminal; the CLI currently omits this filter. Whether omission searches both categories is unconfirmed and must be established with Signzy.
