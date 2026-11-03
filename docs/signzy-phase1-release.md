# Phase 1 release and acceptance

Updated 3 November 2026. [Canonical checklist](signzy-phase1-scope.md). New changes are local, not deployed. No new vendor calls were made during implementation.

## App workflows

Phase 1 submissions are Current Employer, criminal court/possible search and FIR/possible search. PAN APIs, UAN and civil are not offered or accepted. PAN remains an input required by the Current Employer API; this does not invoke a PAN verification product.

Court/FIR retrieval accepts a local search ID only. Backend reads the vendor identifier from that account's encrypted evidence. Exactly one child result request per search; the same client UUID is idempotent. FIR parsing supports the observed nested result.status=1/result.verifyId envelope and the original flat searchId contract; contradictory identifiers fail closed.

Only provider-confirmed pending result lookups can be explicitly checked again, at least 60 seconds apart, with at most five rechecks. Timeouts/interrupted calls are never auto-replayed. Completed worker attempts retain separate encrypted BgvAttempt records before the current request snapshot is updated. Court/FIR outcomes require human review; empty results do not automatically clear an account.

The preceding polling rule applies to Court/FIR only. DigiLocker now permits one
retrieval per consent session and a persisted 30-minute default cooldown before a
new attempt (DHASHU_DIGILOCKER_COOLDOWN_MINUTES, 1–1440). The app opens the provider
link; the user completes OTP/sharing outside the app and returns manually to confirm.
There is no automatic app deep-link return or trusted completion callback. An
unconfirmed/pending attempt is unsuccessful, not proof of false identity. A new
session requires fresh consent after cooldown; status refresh makes no vendor call.

New DigiLocker consent is digilocker-identity-photo-v2. New sessions enable getEAadhaarJpeg; PDF and Base64 flags remain false. Old consent is not expanded, and old completed sessions can request new photo consent. Identity fields remain separate from the encrypted document photo reference. Only supported result.photo URLs are retained; no photo URL is returned to the app, and no image bytes are downloaded by this implementation. Actual URL lifetime and Face Smart compatibility remain to be tested.

Face Smart POST /face/smart-verification uses the supplied contract, strict=true and threshold=0.7. CLI is sandbox-only with hidden vendor image URLs and encrypted receipts. It does not upload images. Liveness and face match are separate outcomes; true liveness plus false match never approves identity. The app shows setup_required, with no live selfie verification button or arbitrary image URL submission endpoint.

## Policy foundation and operator setup

Additive schema includes User.active_bgv_case_id; BgvRequest/DigiLockerSession.case_check_id; BgvCaseCheck.check_definition_id; BgvPolicy, BgvMarketPolicy, BgvProviderCoverage and BgvCase.

The initial explicit seed is IN / BLR, policy IN-BLR-phase1-v2, total 147 quoted units. No global/country fallback, production coverage, currency or automatic user assignment is assumed. Assigned cases freeze the policy and location. This is a first Signzy implementation, not a completed multi-vendor routing engine, policy editor, reassessment workflow or review console.

After deploying the reviewed backend/schema, operator commands in Railway are:

```sh
cd /app
/app/.venv/bin/python bgv_policy_admin.py seed
/app/.venv/bin/python bgv_policy_admin.py assign --user-id ACTUAL_INTERNAL_USER_ID --country IN --city BLR --reason "Consented Phase 1 sandbox pilot"
/app/.venv/bin/python bgv_policy_admin.py status --user-id ACTUAL_INTERNAL_USER_ID
```

These initialize/reconcile schema and never call vendors or approve accounts. Second assignment is rejected; reassessment must preserve history and be implemented explicitly.

Set DHASHU_BGV_POLICY_ENABLED=1 on API and worker only after intended accounts are assigned. Unassigned users cannot submit with enforcement enabled; provider availability is rechecked before execution. The legacy DHASHU_BGV_APP_ENABLED remains a service-wide switch, not a cohort manager. No policy changes User.bgv_status, approval or matching eligibility. Approval gates remain not_configured until signup/matching rules and review authority are decided.

Follow [existing app pilot configuration](bgv-app-pilot.md) and [DigiLocker configuration](digilocker-signup.md). API and worker share the same database and stable encryption key. Worker command is /app/.venv/bin/python bgv_worker.py, or add --once to process at most one queued request. Inspect old queued work before enabling: this revision skips PAN/UAN, but queued in-scope operations can still consume calls.

Rebuild/release the app after deploying the backend. Installed apps do not acquire these screens from a Railway-only update. Android sync/build does not establish installed-device or iOS acceptance.

## New private API endpoints

All are under /api/v1 and bearer-only, owner-scoped, no-store.

| Method | Path | Purpose |
|---|---|---|
| GET | /verification/plan | Own assigned market/phase checklist |
| GET | /verification/liveness | Setup placeholder and reference availability; no image URL |
| POST | /verification/{local-search-id}/result | Queue linked result; body request_id UUID |
| POST | /verification/{local-result-id}/check-again | Explicit bounded pending recheck; empty JSON body |

## Vendor inputs needed for liveness

1. Image-upload API or approved mobile capture SDK: method, authentication, file/size limits, return URL/ID, expiry and deletion.
2. Confirm whether camera JPEG upload is accepted or a trusted capture/session SDK is required. Existing camera capture alone is not liveness evidence.
3. Confirm whether DigiLocker result.photo may be used directly as faceMatchImage, or must be uploaded to Signzy first. Current CLI accepts only the supplied Signzy file hosts. Do not expose private captures publicly as a workaround.
4. Confirm sandbox entitlement and whether the combined Face Smart endpoint is included in the quoted Liveness Secure price of 6.
5. Run good capture, liveness failure, face mismatch, expired/inaccessible URL, malformed response, timeout, ownership and restart tests using consented data.

## Live acceptance and launch gates

- Fresh DigiLocker app consent/OTP/retrieval with photo; verify persistence, restart and old-consent behaviour.
- Current Employer app queue/worker/result; confirm employment/exit flag meanings and non-employed applicability.
- Criminal search/result and FIR search/result; validate pending, candidate and review cases.
- Finish approved liveness upload/capture and real-device/vendor tests.
- Validate the operator review/waiver commands in the pilot; implement reassessment and define which 1a/1b checks gate signup or matching.
- Configure and validate production separately. DigiLocker app operation remains explicitly sandbox-only.

No production flags, paid calls, deployments or existing matching eligibility were changed by this local implementation.

## Operator review and exceptions

The status command prints operator-only check/source references, without personal
identity values. A result review refers to a BgvAttempt ID, not an external case ID.
DigiLocker review refers to the corresponding local session ID. Records must belong
to the same check, account and environment and be ready for review. Search
acknowledgements cannot satisfy screening; review the linked result. Notes and the
declared reviewer identity are encrypted. Console access is the operator privilege
boundary; the normal app has no review/waiver endpoint.

```sh
/app/.venv/bin/python bgv_policy_admin.py review --check-id LOCAL_CHECK_ID --source-id LOCAL_ATTEMPT_OR_DIGILOCKER_SESSION_ID --decision satisfied --reason "Reviewed supporting evidence" --reviewer OPERATOR_ID
/app/.venv/bin/python bgv_policy_admin.py review --check-id LOCAL_CHECK_ID --decision waived --reason "Approved applicability exception" --reviewer OPERATOR_ID
```

Decisions are satisfied, needs_review, not_satisfied or waived. Waivers deliberately
have no evidence source and display as exceptions, never verified evidence. Decisions
are append-only and do not alter overall BGV status or matching gates. A newer source
attempt does not inherit an older satisfied decision; waivers remain recorded for
the fixed case. Exception expiry, formal role administration, a review dashboard
and case reassessment remain outside this first console implementation.
