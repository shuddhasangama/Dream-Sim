# Combined BGV app acceptance

For the m06 sandbox pilot only; existing environment/allowlist and overall approval gates are preserved.

1. Install the new app build, open Verify, and review the compact checklist.
2. For a fresh all-document test, select the fresh DigiLocker sharing disclosure once the existing cooldown ends. Consent explicitly to Aadhaar/PAN sharing and relevant background screening.
3. Complete Aadhaar OTP and document-sharing consent in DigiLocker; return to DhaShu and retrieve details once.
4. Name, DOB/age and document address should show received; a profile-age difference should request review. Court and FIR should begin in the worker without re-entering identity fields.
5. Get Details should retrieve the issued-document listing. If PAN or mobile is missing, only employer should wait. The full PAN/mobile are never returned to the app.
6. Add the declared current employer if available; with complete trusted inputs its check should start automatically. Missing employer must not block Court/FIR.
7. Background reads should update progress without new paid submissions. Search acknowledgements are not clearance; completed legal results remain subject to review. A pending result may need one explicit later recheck; automatic repeated paid polling is off by default.
8. Face remains setup-needed; receiving an Aadhaar photo does not mean liveness or face matching succeeded.
9. Log out/in or reopen the app and confirm saved results persist. Repeated refreshes and consent confirmation must not duplicate requests. No account approval or matching eligibility should change from these sandbox results alone.

The Get Details response supplied is a document list: a PAN identifier may be usable as employer input, but full PAN-card extraction/content and independent PAN-holder validation have not been implemented or tested.

## Release status

Runtime commit `d7e4a4be` is on origin/master. API deployment `6d0406cd-ab18-44d0-b605-c25156e19c2c` and worker deployment `2d07c206-1193-4262-9567-2fad630d5dd8` both report SUCCESS; `/api/v1/health` reports status ok. No variable changes, public-profile changes, new account approvals or live Signzy calls were performed for this release.

Android debug build 2026110302 was built and copied to `outputs/bgv-compact-release/DhaShu-BGV-2026110302.apk` (SHA256 `6DC08B7AC8F840BA87957EBE0DC96AACE76966E0AF48EBA0E00731B4A35FFD0A`). iOS build **70** uploaded successfully to App Store Connect through [Codemagic](https://codemagic.io/app/6aaa35b8366c2d5c4eedc58b/build/6ae9b0d7e83a9019991ca5f7). Apple processing and TestFlight group availability were not inspected because sign-in was required; the user chose to distribute build 70 personally.

Validation: 53 focused backend tests and 53 Signzy tests passed (overlapping suites), all 111 mobile unit tests passed, all 50 browser regression tests passed, web production bundle and Android native build succeeded. Provider tests were mocked. Fresh installed-app consent and live Get Details / downstream vendor results remain to be tested by the user.

## Exact screening and employment labels

The exact-screening release supersedes the older review-on-all-results behaviour above. Use iOS build 71 for the Verified / History found / Not confirmed / Doesn't match badges. Court and FIR submit exact matching; a linked, explicitly completed exact response with zero cases and consistent counters verifies that check. Positive cases require operator review. Pending, malformed or contradictory results never verify. Overall account approval remains separate.

Employment shows the latest employer record with validated dates/duration when current employment cannot be confirmed. It does not infer unemployment or completeness of employment history. This release changes new legal search requests and preserves prior possible-match evidence. Operator review is currently CLI-based; assignment/notification/dashboard are not implemented.

Build 71 upload: https://codemagic.io/app/6aaa35b8366c2d5c4eedc58b/build/6ae9c1c857e81944fbc19522
