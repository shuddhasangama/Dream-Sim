# Signzy API status and rerun guide

Review date: 29 October 2026 (India time). Source: current local implementation and saved, sanitised sandbox receipts. This does not establish what is deployed on Railway or enabled on the Signzy account. Initial inspection made no provider calls. The user subsequently reran PAN Simple privately; its latest saved receipt is recorded below.

## Inventory

All six provider operations below use POST. Paths are relative to `https://api-preproduction.signzy.app/api/v3` for the local tester.

| Operation | Endpoint | Implementation | Latest saved sandbox result | Next action |
|---|---|---|---|---|
| `employment_history` | `/underwriting/fetch-employment-history` | Client, validation, hidden CLI inputs, encrypted receipts and sanitised counts; no app wiring or automatic comparison | **HTTP 200**, 29 Oct 2026, 22:26:24 IST; 2 records, limitedOutput=false; offline suite 61 passing tests | Confirm sandbox access, required field combinations and request DOB format; run one consented request |
| `pan_simple` | `/pan/simple` | Client, validation, encrypted receipts; optional name/DOB comparison and app pilot wiring | **Blocked: HTTP 403**, 29 Oct 2026, 21:58:43 IST; latest user rerun also returned access_denied | Ask Signzy to identify the access-denial reason and confirm sandbox product entitlement, credentials and any IP restrictions before retrying |
| `pan_extensive` | `/panextensive` | Client, validation and receipts; field matching not implemented | **Blocked: HTTP 403**, 29 Oct 2026, 22:01:56 IST; access_denied | Ask Signzy to confirm PAN Extensive access and investigate the 403 |
| `current_employer` | `/employment-verification/current-employer` | Client, receipts, optional current-employer comparison and app pilot wiring | **HTTP 200**, 28 Oct 2026, 14:03:42 IST; resultCode 200, is_employed=false, date_of_exit_marked=true | Connectivity worked; ask how exit/current-employment flags and source freshness should be interpreted. This is not proof of unemployment |
| `individual_search` | `/individual/search` | Client, receipts and app pilot submission | **HTTP 200**, 28 Oct 2026, 14:49:28 IST; response requires review | Confirm caseId and async lifecycle, filters, DOB format and interpretation; run search before result lookup |
| `individual_result` | `/individual/result` | Client, receipts and CLI lookup using prior encrypted search receipt; not offered as a separate app check | **HTTP 200**, 28 Oct 2026, 15:09:17 IST; cases=[], total=0 | Confirm empty-result meaning and completeness. Not an automatic court clearance |
| `uan_passbook` | `/underwriting/uan-passbook-without-otp` | Client, validation, encrypted receipts and app pilot wiring | **No saved live-test receipt found** | Confirm sandbox availability and entitlement; test with consented UAN. Callback integration remains absent |
| Face Smart / liveness and face match | No confirmed connected endpoint | Offline contract mapper and simulator only | **Not connected to Signzy** | Obtain endpoint, authentication, approved capture/SDK requirements, score semantics and consent/retention contract before implementing transport |

HTTP 200 records successful response receipt, not a verified person. Production credentials, permissions and end-to-end deployment remain unverified. Sandbox evidence never approves overall BGV or unlocks matching.

## Existing evidence identifiers

These are **DhaShu local receipt IDs**, not Signzy request/trace IDs. Use UTC time and endpoint for provider log correlation; obtain provider trace IDs privately if available.

| Operation | Latest receipt ID | Request timestamp recorded in summary (UTC) |
|---|---|---|
| PAN Simple | `e270f66bb64ae7d646c530e1b0736322` | `2026-10-29T16:28:43.534550+00:00` |
| PAN Extensive | `a1980278716feacc88a84ab994f79076` | `2026-10-29T16:31:56.825592+00:00` |
| Current employer | `f8e780296edb7060fed88cd4397171f9` | `2026-10-28T08:33:42.726453+00:00` |
| Court search | `c36ece30cb2ed09507b2cc48e6c3f9d6` | `2026-10-28T09:19:28.921174+00:00` |
| Court result | `0219bd574fa17282c159ee9b7e690714` | `2026-10-28T09:39:17.113137+00:00` |

Summary timestamps are completion/test timestamps, not guaranteed exact provider start times. Private receipts contain start/end times and selected correlation headers. Do not send full private receipts or raw identity/employment data to support.

## Rerun sequence

1. Have Signzy resolve/confirm access and issue approved sandbox fixtures where available.
2. Configure `SIGNZY_ENV=preproduction`, `SIGNZY_PRODUCTION_ENABLED=0`, and the replacement `SIGNZY_TEST_API_KEY` in the local terminal securely. Do not paste keys into chat. `.env.signzy.test.example` is a reference only: the scripts do not load dotenv files automatically. Railway variables do not configure the local terminal.
3. Run each command from the repository root. The existing runner prompts for hidden personal inputs. Use only consented data or provider-approved sandbox fixtures. Each submitted operation may consume credits; there are no automatic retries.

```powershell
python signzy_test.py pan_simple
python signzy_test.py pan_extensive
python signzy_test.py current_employer
python signzy_test.py individual_search
# Substitute the encrypted file printed by THAT court search:
python signzy_test.py individual_result --search-receipt "data/signzy-test-receipts/<search-receipt-id>.windows-dpapi.enc"
python signzy_test.py uan_passbook
```

If `python` is unavailable, the bundled executable used for this review is `C:/Users/Dharesh/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` (invoke with `&` in PowerShell).

Court search requests name/address, defaults matchType to exact and omits DOB. Add `--match-type possible` for possible matches. Employer requests PAN/mobile. Passbook requests UAN, fixes consentFlag=Y and ttl=0, and uses no callback. Do not fall back to production when sandbox fails.

4. Preserve the new `.summary.json` and encrypted private receipt. Update the table with environment, timestamp, HTTP status, interpreted outcome, receipt ID and required support action. Do not overwrite old evidence.
5. If the request times out, or saving fails after submission, check provider logs before repeating: it may already have executed and been billed. HTTP 202 is pending, not verified. For court results, agree the correct polling interval/billing with Signzy before repeated lookups.

Standalone commands do not update app/database evidence. Only PAN Simple/current-employer support optional `--user-id <actual-user-id>` binding in this runner; this requires correct DB configuration and declared values. Avoid this for an initial connectivity rerun. App pilot code exists for four check types, but deployment and worker operation were not verified in this review. Async callbacks, reconciliation and production operations remain incomplete.

## Offline regression command

Review rerun on 29 October 2026: **57 tests passed** across the nine modules below. The bundled Python initially lacked Flask; installing the repository-pinned Flask 3.1.3 resolved the two import errors, and the full rerun passed.

```powershell
python -m unittest test_signzy_client test_signzy_probe test_signzy_receipts test_signzy_verification test_signzy_additional test_signzy_court_result test_bgv_app test_identity_verification test_identity_capture -q
```

This is a mocked/synthetic regression run; it is not a provider connectivity test and consumes no Signzy credits.

## Saved court evidence reread

On 29 October, the existing encrypted court receipts were decrypted locally without a new provider call. Search returned HTTP 200, status=1 and a caseId. Result returned HTTP 200, status=1, total=0 and cases=[]. Both bodies were recorded complete. This confirms the saved response contents, not a fresh search or a provider-confirmed court clearance.

## 30 October update: category checks and FIR preparation

Possible/criminal search: HTTP 200, 30 Oct 10:38:16 IST, receipt 6f92d5e0b4bc1e670f445d33386aec6f.
Possible/civil search: HTTP 200, 30 Oct 10:46:45 IST, receipt 2fb57f068536b60869b4bd5f6bdaf9c9.
Both explicit search-category submissions succeeded; linked result calls remain pending.
FIR search/result are now implemented; live tests pending. Nine provider operations
are implemented in total. Offline suite: 67 tests passed.
