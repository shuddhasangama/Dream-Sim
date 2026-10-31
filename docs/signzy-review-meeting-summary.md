# Signzy testing review - 30 October 2026

**Nine API operations implemented; six exercised in sandbox. Four returned HTTP 200, two are blocked by HTTP 403, and three await live testing.** Counts refer to distinct API operations, not repeated attempts.

| API | Status | Evidence / next step |
|---|---|---|
| Current employer | Successful response - HTTP 200 | Employment summary received on 28 Oct; confirm interpretation of employment/exit flags. |
| Court search | Successful response - HTTP 200 | Explicit possible + criminal and possible + civil searches both returned HTTP 200 on 30 Oct. Result lookups for these new searches remain pending. |
| Court result | Successful response - HTTP 200 | Earlier 28 Oct lookup returned zero cases. Result retrieval for both new searches remains pending. |
| PAN Simple | Access blocked - HTTP 403 | Repeated failures, including 29 Oct rerun. Signzy to investigate access/entitlement. |
| PAN Extensive | Access blocked - HTTP 403 | 29 Oct test failed. Signzy to investigate access/entitlement. |
| UAN passbook without OTP | Live test pending | Implementation ready for sandbox test; confirm access and approved test data. |
| Past employment history | Successful response - HTTP 200 | 29 Oct test returned 2 employment records; limitedOutput=false. No automatic verification conclusion. |

**Additional validation:** 67 offline regression tests passed after adding employment history. Face/liveness has a tested offline foundation but no connected Signzy transport; it is outside the nine API operations above.

**Requested outcomes from Signzy:** resolve both PAN 403 errors; confirm UAN sandbox access and fixtures; explain exact/possible matching and court completion/empty-result semantics; clarify employer flags and billing for retries/result lookups. Agree an owner and resolution date.

HTTP 200 demonstrates a successful API response, not completed person verification or production readiness. No new network requests were made to prepare this summary. Source: saved local sandbox receipts from 28-30 October 2026.

FIR search and FIR result: implemented from supplied contract; live tests pending. Attached example is not our live test evidence.
