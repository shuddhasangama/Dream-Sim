# DigiLocker signup integration

This is an account-bound sandbox flow for the existing authenticated beta signup
review (Stats step) and Verify screen. It does not create public accounts, replace
the full BGV decision, verify present residence, or unlock matching.

## Flow

1. User accepts versioned consent. POST `/api/v1/verification/digilocker/sessions`
   with `request_id` (UUID), `consent: true`, `consent_version: digilocker-identity-photo-v2`.
2. Backend creates one Signzy `digilocker-v2/createUrl` request. Provider requestId
   and consent URL stay encrypted, bound to the authenticated user and environment.
3. User opens the link in the system browser sheet and completes Aadhaar OTP and
   document sharing on DigiLocker. They return to the app themselves.
4. The checkbox “I completed DigiLocker OTP and consent for this link” triggers
   POST `/api/v1/verification/digilocker/sessions/<local-id>/complete`, body
   `{"consent_completed":true}`. The backend retrieves with its stored provider
   requestId. The checkbox alone never proves provider consent or identity.
5. Successful provider name, DOB and document address are retained encrypted.
   Age is calculated from DOB using the India calendar date at retrieval. A missing
   or invalid DOB and under-18 result require review. New photo consent additionally
   requests JPEG retrieval and retains a supported document-photo URL encrypted on
   the backend for future face matching. Photo URLs are not returned to the app;
   no image bytes are downloaded. PDF and Base64 flags remain false. Old consent
   does not authorize photo retrieval. No Aadhaar number or certificate is retained.

GET `/api/v1/verification/digilocker` resumes the latest session. Bearer account
ownership is mandatory for all three endpoints. Client-supplied provider requestIds
and user IDs are rejected. Responses are private/no-store. The callback remains an
untrusted sandbox acknowledgement; it never updates accounts or authorizes retrieval.

## Configuration and release

Existing `SIGNZY_TEST_API_KEY`, `SIGNZY_ENV=preproduction` and HTTPS
`SIGNZY_DIGILOCKER_CALLBACK_BASE` are used. Also required:

- `SIGNZY_RECEIPT_ENCRYPTION_KEY`: stable Fernet key, generated privately and backed
  up securely. On Railway, local Windows DPAPI receipts cannot protect server data.
  Losing this key makes saved sessions/results unreadable. Do not rotate casually.
- `DHASHU_DIGILOCKER_ENABLED=1`.
- `DHASHU_DIGILOCKER_TESTERS`: comma-separated exact internal User IDs permitted
  to test. Empty list denies everyone.
- `SIGNZY_DIGILOCKER_SANDBOX_CALLBACK_ENABLED=1` for the existing callback route.

Production Signzy operation is deliberately unavailable in this first sandbox
release. A separate production callback/configuration and live acceptance test are
required before broad rollout. Existing generic BGV flags need not be enabled.

Deploy the additive DigiLockerSession schema/backend first, then ship the mobile
build containing `@capacitor/browser`. Run `npm run build` and `npx cap sync android`
in the mobile directory; build/sign/install the app using the existing release
process. Installed apps do not acquire these screens from a Railway-only update.

Consent links expire locally after 30 minutes. Create is limited to three per
account per day. Each consent session permits one retrieval attempt. A configurable
cooldown, DHASHU_DIGILOCKER_COOLDOWN_MINUTES (default 30, allowed 1–1440), is persisted
before the vendor call. Duplicate confirmations and new sessions are blocked during
cooldown, including after app restart. A provider-pending response records an
unsuccessful/not-confirmed attempt, not a failed identity or dishonesty finding.
After cooldown, an unconfirmed attempt may start a fresh consent session; it cannot
reuse the consumed link for another retrieval. The first call may still be billed.
Refreshing status is a local database read, not a vendor request. Network uncertainty and interrupted in-flight calls
require support review; they never auto-create links or replay provider requests.
Refresh status after a lost app response before taking any further action.

## Validation

`python -m unittest test_digilocker_signup test_signzy_digilocker_e2e -q`
uses synthetic provider responses, actual adapters, encryption and database writes.
It covers consent, ownership, same-request retrieval, duplicate protection,
pending/throttling, invalid DOB, expiry, adult boundary, timeout/no replay, and
preservation of overall BGV status. Mobile tests cover rendering and confirmation.

Live acceptance still needs a permitted tester to create a fresh session in the
new app, complete OTP/consent, retrieve their details, restart the app and confirm
the saved result. OTP and consent remain human actions. Previously decrypted CLI
receipts are not imported into an account or treated as this flow's E2E proof.
