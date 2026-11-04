# Signzy Phase 1 progress and launch checklist

Updated **3 November 2026**. This supersedes the earlier 227 scope. Criminal court only; civil is quantity zero. PAN Simple/Extensive and UAN are excluded.

Vendor testing means saved real sandbox evidence; automated tests use synthetic responses. Status as of **3 November 2026**, including installed-app DigiLocker testing, fresh exact Court/FIR sandbox results, and the deployed match-summary/REACH release. Sandbox success is not production launch approval. Earlier dated notes below are historical; this table is the current snapshot.

| Product | Data element / purpose | Testing status / implementation | Quote | Quantity | Cost | Phase | App launch pending |
|---|---|---|---:|---:|---:|---|---|
| Current Employer Verification | Current employer evidence; may return historical employment | Live sandbox response received; PAN/mobile-driven app integration works. Tested profile returned history, not current employment; meaningful dates/duration and History found status implemented | 4 | 1 | 4 | 1a | Live positive current-employer confirmation and mismatch/no-data device acceptance |
| DigiLocker Create URL | External consent/access link | Live sandbox and installed-app link → Aadhaar/OTP/consent flow tested successfully; ADHAR + PANCR scope connected | 3.5 | 1 | 3.5 | 1a | Additional-device cancellation/expiry/resume acceptance |
| DigiLocker Get Details (additional dependency) | Issued-document listing, PAN identifier, mobile | Live response received; PAN identifier retrieved and used as eligible employer input. Not full PAN-card verification or PAN photo retrieval | TBC | 1 | TBC | 1a | Confirm vendor billing; PAN document/photo retrieval contract if required |
| DigiLocker get eAadhaar | Name, DOB/age, document address, original photo | Live decryption and installed-app retrieval successful; original Aadhaar photo downloaded/validated and stored encrypted; 30-day cache expiry/purge implemented | 3.5 | 1 | 3.5 | 1a | Wider device/recovery acceptance; photo does not establish liveness |
| Individual Court Search — Criminal | Exact criminal case candidates | Fresh live sandbox exact search succeeded; automatically queued from consented Aadhaar name/address; linked result request implemented | 40 | 1 | 40 | 1b | Production access/coverage acceptance |
| Individual Court Result — Criminal | Completed criminal screening outcome | Fresh exact result completed with zero cases; individual check Verified. Positive cases → Review required; pending/invalid results cannot verify | 40 | 1 | 40 | 1b | Live positive-case reviewer acceptance; dashboard not built |
| FIR Search | Exact FIR candidates | Fresh live sandbox exact search succeeded; automatic identity-driven submission and linked result lookup work | 25 | 1 | 25 | 1b | Production access/coverage acceptance |
| FIR Result | Completed FIR screening outcome | Fresh exact result completed with zero candidates; individual check Verified. Nested result/count/completion parsing corrected and regression-tested | 25 | 1 | 25 | 1b | Live positive-candidate reviewer acceptance |
| Liveness Secure / supplied Face Smart endpoint | Liveness plus separate face comparison | Request/response mapper and synthetic tests exist; no live call or app capture/upload E2E. Aadhaar reference photo available; integration on hold | 6 | 1 | 6 | 1a | Signzy capture/upload contract, image compatibility, access/product/price confirmation, device E2E |
| Entity Court Search/Result | Entity legal records | Not implemented/tested; quantity zero | 40 | 0 | 0 | 1b, inactive | Not scheduled |
| Individual Court Search — Civil | Civil case candidates | Earlier sandbox search 200; excluded from active app scope | 40 | 0 | 0 | Inactive | Not scheduled |
| Individual Court Result — Civil | Civil results | No new civil E2E acceptance; excluded from active scope | 40 | 0 | 0 | Inactive | Not scheduled |
| ConsenzAI | Video consent/liveness/optional match | Not implemented/tested | 7 | 0 | 0 | Inactive | Not scheduled |
| Face Match, standalone | Compare face images | No standalone live test; combined Face Smart mapper only | 2.5 | 0 | 0 | Inactive | Not scheduled |
| Face Extraction | Extract document portrait | Not implemented/tested as separate API; original DigiLocker Aadhaar photo used instead | 3 | 0 | 0 | Inactive | Not scheduled |
| **Total** | **1a: 17; 1b: 130** | **Original supplied pricing only; Get Details is unpriced** | | | **147** | | |

Today's match-summary release is deployed to API and worker (`ddc2cb6f`). Shared Court/FIR/employment statuses and dates, self-declared employment category, and REACH category/verified/freshness filters have automated coverage. Sharing is explicit opt-in; no documents/raw records are shared. Verified-only currently requires Court + FIR + confirmed current employment. No new Signzy calls were made for this presentation/filter release. Face/liveness and avatar generation remain unconnected. Overall member approval remains separate from per-check Verified.

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

## Exact-screening outcome rule (supersedes earlier possible matching)

New app Court and FIR searches use `matchType: exact`; Court remains criminal only. Request IDs include the new exact-search revision and old encrypted possible-search inputs/results are preserved. A completed old possible result is not relabelled as an exact result. New exact searches are scheduled once per consented identity/case, with one linked result request each; pending rechecks remain explicit/bounded.

For each linked exact result: explicit successful completion plus an empty cases list and consistent zero counters yields `verified` for that check. Positive case candidates yield `needs_review`. Pending, malformed, mismatched-owner/environment/source links and contradictory zero counts never verify. These rules do not change overall member BGV/matching approval. The earlier mandatory-review wording on zero cases was an application decision, not Signzy's response.

Employment is now projected separately as `history_available`, `employment_mismatch`, `not_confirmed` or verified current employer. Historical employer name and validated joining/exit dates and duration are shown without PAN/UAN/member identifiers. A historical exit record does not establish unemployment or account for all later employment. No new employer vendor call is needed to update saved evidence.

There is an append-only operator review command; reviewer assignment, notifications and a case-review dashboard are not built. Positive exact case candidates therefore require an operator action rather than implying somebody is already reviewing them. The mobile update adds explicit History found / Not confirmed / Doesn't match / Verified labels; build 70 cannot display all new badges correctly.

Exact-screening release validation (3 November 2026): fresh sandbox searches and their linked result lookups were run with exact matching; completed zero-case Court and FIR outcomes are returned as verified individual checks. Existing employment evidence was reprojected without a new employer vendor call. A second observed FIR completion message, `Process complete.`, is now recognized alongside `Processing done`. Existing possible-match evidence remains unchanged and is excluded from the current exact-search projection.

Runtime commit `80bb1a1c` is deployed to the API and worker. iOS build **71** (mobile source `4ebf17fb`) uploaded successfully through Codemagic; user handles TestFlight distribution. Android debug build 2026110303 built successfully. Validation: 54 focused backend tests, all 53 Signzy tests (overlapping suites), all 112 mobile unit tests, and three compact-screen browser tests passed. No face/liveness or avatar-generation call was performed.
