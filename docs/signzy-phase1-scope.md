# Signzy Phase 1 progress and launch checklist

Updated **3 November 2026**. This supersedes the earlier 227 scope. Criminal court only; civil is quantity zero. PAN Simple/Extensive and UAN are excluded.

Vendor testing means saved real sandbox evidence. Automated tests use synthetic responses. Installed-app E2E means a fresh app/vendor journey. HTTP 200 alone is not person verification. **New changes are local, not deployed.**

| Product | Data element / purpose | Testing status / implementation | Quote | Quantity | Cost | Phase | App launch pending |
|---|---|---|---:|---:|---:|---|---|
| Current Employer Verification | Current employer evidence | Vendor 200; adapter, comparison, app queue and worker built | 4 | 1 | 4 | 1a | Deployment, flag interpretation, worker and app E2E |
| DigiLocker Create URL | Consent/access link | Vendor 200; prior consent completed; new photo consent/request automated-tested | 3.5 | 1 | 3.5 | 1a | Fresh app OTP and photo-enabled consent |
| DigiLocker get eAadhaar | Name, DOB/age, document address and photo reference | Vendor 200 for prior request; new photo flag and encrypted reference implemented | 3.5 | 1 | 3.5 | 1a | Live photo-enabled retrieval, persistence/restart, URL expiry |
| Individual Court Search - Civil | Civil candidates | Prior vendor 200; excluded from new app submissions | 40 | 0 | 0 | Inactive | Not scheduled |
| Individual Court Result - Civil | Civil results | Excluded from new Phase 1 workflow | 40 | 0 | 0 | Inactive | Not scheduled |
| Individual Court Search - Criminal | Criminal candidates | Vendor 200; app enforces criminal/possible; linked result workflow built and automated-tested | 40 | 1 | 40 | 1b | Fresh app search/result chain |
| Individual Court Result - Criminal | Linked criminal results | Earlier court result 200/zero cases; category-specific completion pending; app retrieval built | 40 | 1 | 40 | 1b | Live criminal result, pending handling and review acceptance |
| Entity Court Search/Result | Entity legal records | Not implemented/tested; quantity zero | 40 | 0 | 0 | 1b, inactive | Not scheduled |
| FIR Search | FIR candidates | Vendor 200; observed result.verifyId envelope reconciled; app/worker chain built and automated-tested | 25 | 1 | 25 | 1b | Fresh linked vendor/app test |
| FIR Result | Linked FIR results | Adapter/app retrieval built; synthetic pending/result tests pass; no successful vendor test recorded | 25 | 1 | 25 | 1b | First live result and review acceptance |
| Liveness Secure / supplied Face Smart endpoint | Liveness and separate face-match outcome | Adapter/CLI and synthetic tests built; app setup placeholder only | 6 | 1 | 6 | 1a | Upload/capture contract, photo URL compatibility, entitlement/price confirmation, device E2E |
| ConsenzAI | Video consent/liveness/optional match | Not implemented/tested | 7 | 0 | 0 | Inactive | Not scheduled |
| Face Match, standalone | Compare face images | Separate product excluded; combined Face Smart adapter reports match separately | 2.5 | 0 | 0 | Inactive | No separate paid call scheduled |
| Face Extraction | Extract document portrait | Not implemented; DigiLocker photo reference used if returned | 3 | 0 | 0 | Inactive | Not scheduled |
| **Total** | **1a: 17; 1b: 130** | **User-supplied prices; currency/tax unspecified** | | | **147** | | |

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
- [ ] Backend/worker release and mobile build release.
- [ ] Fresh installed-app E2E for every active check.
- [ ] Production entitlements, configuration and acceptance.

Latest selected regression: **105 backend tests and 110 mobile tests passed**, plus mobile build and Android sync. Backend count includes schema compatibility tests; no live PostgreSQL deployment was exercised. Tests mocked provider calls; these are not whole-repository counts or vendor acceptance. DigiLocker confirmation now has one retrieval per session and a configurable 30-minute default cooldown. See [release runbook](signzy-phase1-release.md).
