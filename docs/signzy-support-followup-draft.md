# Draft only - not sent

Subject: DhaShu sandbox integration - PAN Simple 403, API entitlements and response-contract confirmations

Hello Signzy Support,

We have implemented six preproduction API operations for DhaShu and need help resolving access and confirming contracts before our next test round.

Our sandbox base URL is https://api-preproduction.signzy.app/api/v3. The latest saved results are:

| POST path | Latest recorded completion time (UTC) | Result |
|---|---|---|
| `/pan/simple` | 2026-10-29 16:28:43 UTC | HTTP 403; previous attempts also returned 403 |
| `/employment-verification/current-employer` | 2026-10-28 08:33:42 UTC | HTTP 200; resultCode 200; current-employment interpretation needs confirmation |
| `/individual/search` | 2026-10-28 09:19:28 UTC | HTTP 200 |
| `/individual/result` | 2026-10-28 09:39:17 UTC | HTTP 200; cases=[], total=0 |
| `/panextensive` | 2026-10-29 16:31:56 UTC | HTTP 403; access denied |
| `/underwriting/uan-passbook-without-otp` | No saved live result available | Implemented; awaiting confirmed sandbox access/test |

Could you please:

1. Investigate PAN Simple and PAN Extensive HTTP 403 responses using our account logs and confirm the exact cause: product entitlement, credential scope, IP restrictions or another restriction. Please confirm sandbox and production access separately for all six APIs.
2. Provide approved sandbox test fixtures and expected outcomes, plus current pricing/credit rules, especially for pending, failed, timed-out and result-lookup requests.
3. Confirm the PAN Extensive response schema and PAN Simple name/DOB/status field formats.
4. Explain current-employer flags, particularly `is_employed=false` with `date_of_exit_marked=true`, historical versus current records, and data freshness/coverage.
5. Confirm court search/result lifecycle: caseId location, pending/completed signals, result lookup interval, empty-list semantics, exact/possible matching, civil/criminal and party filters, and DOB wire format. Please confirm when a zero-result response is complete and what coverage limitations apply.
6. Confirm whether UAN passbook without OTP is available in preproduction, required consent, ttl/cutoff semantics, synchronous versus asynchronous response shapes, and any polling/callback requirements.
7. Supply the India Face Smart endpoint/authentication and approved SDK/capture flow; reference-image requirements; liveness and face-match score/strict-mode semantics; billing; and retention/deletion requirements. We currently have only an offline simulator for this product.
8. Confirm request correlation headers and `x-client-unique-id` semantics, error/insufficient-credit response codes, and timeout reconciliation/idempotency support.

Please provide a ticket reference, owner and expected resolution date for each open item. We can provide provider request/trace IDs via an approved private channel if available. We will not include API keys, PANs, UANs or full private responses in ordinary email.

Regards,
DhaShu team
