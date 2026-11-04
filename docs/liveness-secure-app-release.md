# Hosted Liveness Secure app integration — 4 November 2026

The operator's standalone sandbox test returned HTTP 200 for createUrl and getData, liveness true, face verified true at 99%, provider status true, additional checks true and one face. The tested provider Aadhaar URL and the captured-selfie URL use supported Signzy file hosts. Callback/redirect omission was accepted in that test. No manual receipt is automatically attached to an app account.

## App behavior

Verify → Live face verification → consent → Start face verification. The backend snapshots the authenticated user's latest completed DigiLocker portrait URL and queues one createUrl call. A worker calls Signzy with the tested threshold 0.6, English, additional checks, camera switching, reviewImage, and piiDeletionTTL six months. Consent states this vendor retention. No generated avatar or PAN portrait is sent as identity evidence.

The app polls only its own status endpoint while waiting for a link, then opens the allowlisted Signzy capture page using the native browser. Closing that browser triggers one authenticated result request for the recorded flow ID. It queues getData; a return or redirect never grants success. If the app restarts, reopen the same capture link or use “I’ve finished · Check result.” Backgrounding without closing the browser may require this fallback. A token/consumer-ID mismatch, unknown shape or uncertain transport outcome cannot pass.

Liveness, face-match percentage and additional-check status remain distinct. Provider overall status, liveness, face match and additional checks must all be explicitly true for the combined check to pass. Contradictory face-covered/multiple-face/failed-check flags do not pass. Sandbox results do not alter User.bgv_status, grant matching access, complete other BGV checks, or block dating/relationship/Guru testing.

After a successful hosted check, DhaShu downloads the original captured selfie once from an allowlisted Signzy file URL, without redirects, into encrypted private storage. If this download fails, the identity check remains successful; avatar capture can still use the existing native-camera flow. Before an avatar run is reserved, Your AI avatar can show the Signzy selfie for review. OpenAI processing still requires the separate avatar consent and user submission. No OpenAI call or AvatarJob is created by a liveness check. Existing avatar choices, selected images and once-only generation allowances remain unchanged.

## Persistence and cost controls

An additive LivenessSession row is bound to the authenticated user and DigiLocker session. Creation and retrieval are atomically claimed and committed before external IO. Repeated start/complete submissions reuse the same reservation. Uncertain outcomes and stale claims are not automatically replayed. Incomplete capture allows at most three result fetches with a one-minute cooldown; there is no billable polling loop. The capture has a local 24-hour limit, not a claim about the vendor's token expiry. No new link is silently created after failure, expiry or deletion.

API keys stay on the server. Tokens, capture URLs, input URLs, evidence and original selfies are encrypted with the existing stable BGV encryption key. The capture URL is exposed only to its owner while capture is pending. Originals and private provider evidence are removed after 30 days; concise check summaries remain. Accepted avatars follow the existing separate retention rule. Avatar deletion clears hosted face evidence but retains the reservation. Neither deletion nor expiration resets paid allowances.

## Compatibility and release

New endpoints: GET/POST /api/v1/profile/liveness and POST /api/v1/profile/liveness/complete. The old /profile/face-match endpoints and legacy worker remain compatible with installed builds. The updated client uses the hosted endpoints and can fall back to legacy reads if a server does not have them. Web development preview remains simulated; production browser login is not added here.

Set DHASHU_LIVENESS_SECURE_ENABLED=1 on Dream-Sim and bgv-worker. Existing SIGNZY_ENV=preproduction, SIGNZY_TEST_API_KEY and stable SIGNZY_RECEIPT_ENCRYPTION_KEY are reused. No new key, image-upload service, callback receiver or OpenAI setting is needed. Deploy the API/schema before the worker. This adds no retrospective paid calls: users start the hosted capture themselves after consent. Install the new native build for the hosted UI; build 76 retains its old flow.

Automated tests cover SQLite and real PostgreSQL persistence; owner isolation; duplicate creation/retrieval; pending cooldown/caps; mismatched sessions; failure/timeout; private-selfie reuse; no automatic OpenAI call; expiry/deletion; native-browser return via a mocked plugin; explicit fallback and existing app regressions. Real iPhone/Android Signzy camera permissions, browser-return behavior and provider results require acceptance on the new device build.
