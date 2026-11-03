# Signzy Phase 1 progress and launch checklist

Updated **3 November 2026**. This supersedes the earlier 227 scope. Criminal court only; civil is quantity zero. PAN Simple/Extensive and UAN are excluded.

Vendor testing means saved real sandbox evidence. Automated tests use synthetic responses. Installed-app E2E means a fresh app/vendor journey. HTTP 200 alone is not person verification. **Backend and worker deployed for m06 on 3 November 2026. Android APK built; iOS build 68 uploaded/processed; user confirmed iOS deployment completed. User confirmed installed-app Aadhaar retrieval working; fresh combined PAN/screening acceptance is pending.**

| Product | Data element / purpose | Testing status / implementation | Quote | Quantity | Cost | Phase | App launch pending |
|---|---|---|---:|---:|---:|---|---|
| Current Employer Verification | Current employer evidence | Vendor 200; adapter, comparison, app queue and worker built | 4 | 1 | 4 | 1a | Flag interpretation and fresh installed-app E2E; API/worker deployed |
| DigiLocker Create URL | Consent/access link | Vendor 200; prior consent completed; new photo consent/request automated-tested | 3.5 | 1 | 3.5 | 1a | Prior installed-app Aadhaar consent confirmed by user; new ADHAR/PANCR scope pending |
| DigiLocker Get Details | Available issued-document listing, PAN identifier and mobile | Supplied contract implemented; encrypted worker evidence and synthetic workflow tested | TBC | 1 | TBC | 1a | Live combined listing received; confirm endpoint billing and PAN-document download contract |
| DigiLocker get eAadhaar | Name, DOB/age, document address and photo reference | Vendor 200 for prior request; new photo flag and encrypted reference implemented | 3.5 | 1 | 3.5 | 1a | User reported installed-app identity/photo reference received; fresh combined flow, persistence/restart and URL expiry pending |
| Individual Court Search - Civil | Civil candidates | Prior vendor 200; excluded from new app submissions | 40 | 0 | 0 | Inactive | Not scheduled |
| Individual Court Result - Civil | Civil results | Excluded from new Phase 1 workflow | 40 | 0 | 0 | Inactive | Not scheduled |
| Individual Court Search - Criminal | Criminal candidates | Vendor 200; app enforces criminal/possible; linked result workflow built and automated-tested | 40 | 1 | 40 | 1b | Fresh app search/result chain |
| Individual Court Result - Criminal | Linked criminal results | Live criminal result lookup completed; pending/complete parsing corrected and regression-tested | 40 | 1 | 40 | 1b | Operator review acceptance; existing app can refresh corrected results |
| Entity Court Search/Result | Entity legal records | Not implemented/tested; quantity zero | 40 | 0 | 0 | 1b, inactive | Not scheduled |
| FIR Search | FIR candidates | Vendor 200; observed result.verifyId envelope reconciled; app/worker chain built and automated-tested | 25 | 1 | 25 | 1b | Fresh linked vendor/app test |
| FIR Result | Linked FIR results | Live result HTTP 200 received; nested result/numResults mapping corrected and candidate-review messaging tested | 25 | 1 | 25 | 1b | Candidate identity review and counter-semantics confirmation |
| Liveness Secure / supplied Face Smart endpoint | Liveness and separate face-match outcome | Adapter/CLI and synthetic tests built; app setup placeholder only | 6 | 1 | 6 | 1a | Upload/capture contract, photo URL compatibility, entitlement/price confirmation, device E2E |
| ConsenzAI | Video consent/liveness/optional match | Not implemented/tested | 7 | 0 | 0 | Inactive | Not scheduled |
| Face Match, standalone | Compare face images | Separate product excluded; combined Face Smart adapter reports match separately | 2.5 | 0 | 0 | Inactive | No separate paid call scheduled |
| Face Extraction | Extract document portrait | Not implemented; DigiLocker photo reference used if returned | 3 | 0 | 0 | Inactive | Not scheduled |
| **Total** | **1a: 17; 1b: 130** | **Original scope only; Get Details price, currency/tax unspecified** | | | **147** | | |

The two historical employer records came from Past Employment History, a different endpoint. Current Employer is the selected product, not an additional historical call. Shifted Result rows are interpreted as Court 40 x 1 and FIR 25 x 1. Confirm separate search/result billing before treating 147 as invoice terms.

## Engineering and release checklist

- [x] Active app submissions: employer, explicit criminal court, FIR. PAN/UAN/civil removed.
- [x] Owner-bound result IDs; duplicate protection; explicit bounded pending rechecks.
- [x] Separate encrypted evidence for each worker attempt, including result rechecks.
- [x] Country/city policy tables, immutable assigned user-case snapshot and provider coverage.
- [x] User.active_bgv_case_id, per-attempt case_check_id and business check definition.
- [x] Explicit IN/BLR sandbox seed/assignment commands; no automatic user assignment/global fallback.
- [x] Face Smart sandbox transport/CLI with separate liveness and face-match outcomes.
- [x] DigiLocker photo consent v2, opt-in JPEG flag, encrypted server-only photo reference.
- [x] Liveness setup placeholder explaining the missing upload integration.
- [ ] Vendor-approved upload/capture implementation and live Face Smart test.
- [x] Append-only operator review/waiver command; decisions bound to evidence, private review notes encrypted.
- [ ] Reassessment workflow and explicit signup/matching approval gates.
- [x] Backend/worker release and Android APK build; iOS build uploaded and processed.
- [x] User confirmed iOS deployment completed; uploaded build number 68. Group membership was not independently inspected.
- [ ] Fresh installed-app E2E for every active check.
- [ ] Production entitlements, configuration and acceptance.

Release regression: **1,690 backend tests passed, 33 skipped, 820 subtests passed; 110 mobile unit tests and 48 browser tests passed**. PostgreSQL schema/policy bootstrap succeeded on Railway. Provider calls in automated tests were mocked; fresh installed-device/vendor acceptance is not established. DigiLocker confirmation now has one retrieval per session and a configurable 30-minute default cooldown. See [release runbook](signzy-phase1-release.md).

## Combined DigiLocker and background screening update — 3 November 2026

- Installed-app Aadhaar retrieval was confirmed working by the user. PAN listing and the combined fresh device journey still need live acceptance.
- New consent `digilocker-screening-v3` requests ADHAR + PANCR and photo, and explicitly covers criminal Court/FIR/current-employer screening. Older v2 sessions are not retroactively expanded. Existing completed identity can authorize legal screening separately; PAN sharing needs a fresh DigiLocker session.
- Supplied `/digilocker-v2/getDetails` is implemented in the worker. It receives the owner-bound requestId from encrypted session storage. Only unambiguous `in.gov.pan` / PANCR issued-record identifiers with a complete PAN pattern are eligible as employer API input. This is document-list evidence, not full PAN-card retrieval or independent PAN verification. Masked, malformed, conflicting identifiers are held for review. Mobile must meet the employer API's ten-digit format, and account name must agree with retrieved Aadhaar name before employer submission.
- Successful adult Aadhaar retrieval schedules criminal-only Court and FIR searches automatically after bundle consent. Missing PAN/mobile/employer declaration does not block legal checks. Name/address come only from the saved encrypted Aadhaar projection.
- Employer starts once the PAN identifier and mobile are available and the user has supplied their declared employer. Manual PAN input remains deferred.
- The worker schedules one linked result lookup per successful search. Repeated refreshes do not submit vendor calls. Automatic pending-result rechecks default to zero (`DHASHU_BGV_AUTO_RESULT_RECHECKS`, optional 0–5); the user can explicitly request bounded rechecks after 60 seconds. Confirm pending/result billing before enabling automatic repeated polling. Unknown outcomes are never replayed automatically.
- New local workflow uses existing encrypted columns and deterministic request IDs; no schema migration. Case-level suppression prevents automatic reassessment after a new link. No account approval/matching gate was changed.
- Compact UI now has seven status rows, document-detail disclosure, age-declaration difference, conditional employer declaration, and read-only progress refresh. It distinguishes received identity, processing, review and unavailable states. Document address is not proof of current residence. Face capture/upload remains unavailable until the vendor contract is connected.
- Aadhaar is required for this pilot identity route. Installing/creating a DigiLocker account does not issue Aadhaar; users without Aadhaar need support and cannot complete this route.

Validation: 53 focused backend tests passed, all 53 Signzy tests passed (overlapping suites), 111 mobile unit tests passed, all 50 browser regression tests passed, and the production web bundle built. No new live vendor calls were made during automated testing.

Current combined-flow release: API and worker deployed successfully; iOS build 70 uploaded to App Store Connect. User will distribute build 70 personally. See [acceptance steps and release status](bgv-compact-flow.md).

## Response reconciliation and portrait caching

The sandbox returned Court HTTP 200 with status 0 / `Process pending.` and FIR results nested under `result`, using `numResults`. Both shapes now have regression coverage. Pending results are not completed empty searches; candidate results and provider-counter discrepancies require review. Public messages now distinguish pending processing, completed candidate/empty results, contract/access problems and unconfirmed current employment.

The configured sandbox pilot bootstrap reprojects saved result receipts without changing raw encrypted evidence, creating attempts, calling the provider, granting approval or overwriting operator-reviewed checks. A pending linked result can then be checked again within the existing 60-second / five-recheck limit; no new Court/FIR search is needed.

A consented Aadhaar photo reference now supports one bounded file download into encrypted session storage. The original image is validated and retained without AI enhancement. No image bytes or private URLs are returned through normal app status responses. Cached original image bytes expire after 30 days and are purged by the worker. Download failures/interruptions are not retried automatically. This is preparation for avatar-source use, not avatar generation or face verification.

Get Details supplies a PAN record identifier, not a PAN portrait. PAN-photo availability stays false until a documented retrieval contract exists. Live face/liveness testing remains on hold. Sending original portraits to an avatar provider still needs a separate app workflow and purpose-specific consent.

Backend correction release `74d1fd39`: API and worker both deployed successfully on 3 November 2026. Saved projections were repaired without provider calls; one existing pending Court result was subsequently rechecked. The original Aadhaar portrait was downloaded and validated successfully. Existing app build 70 can read the updated messages and result state; no mobile rebuild is required for this correction. Validation: 45 focused backend tests and all 53 Signzy tests passed (overlapping suites). No live face/liveness call or avatar-generation call was performed.
