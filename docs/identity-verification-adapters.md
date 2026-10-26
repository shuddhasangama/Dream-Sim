# Face Smart verification foundation

This implements the supplied Signzy Option 2 payload and response contract,
a provider-neutral Request/Result interface and a no-network simulator. It is
not a connected Signzy integration. No endpoint or authentication header is guessed.

## Offline test

```
python identity_verification.py --scenario pass
python identity_verification.py --scenario face_mismatch
python identity_verification.py --scenario liveness_failed
python identity_verification.py --scenario malformed
python identity_verification.py --scenario timeout
python -m unittest test_identity_verification test_identity_capture -q
```

The supplied response with liveness=true and match.verified=false produces
review_required, not approval. Only explicit boolean true for both checks can
produce passed. Malformed/HTTP error responses fail closed. A timeout stays pending.
Scores are not interpreted until Signzy confirms their ranges and policy.

## In-app rehearsal

Deploy backend and rebuild mobile. Existing private identity capture and encryption
must already be configured. For an explicitly allowlisted tester and simulated
clock, additionally set:

```
DHASHU_IDENTITY_VERIFICATION_MODE=simulation
DHASHU_IDENTITY_VERIFICATION_SCENARIO=pass
```

Existing DHASHU_TESTER_NO_OTP / DHASHU_TESTER_USER_IDS controls apply. Do not change
production identity controls merely to run this rehearsal. Save a consented
identity capture; in the Face photo panel choose Test liveness and face-match flow.
Repeat with the server-selected scenarios above. No actual ID image is requested
or compared in simulation. Results are marked simulated and never update BGV,
identity approval, liveness_checked or agreement entitlements. A separately enabled
legacy test-capture approval remains independent of this simulator.

POST /api/v1/identity-capture/verification/simulate accepts only a request_id UUID,
requires authenticated tester access, and returns current identity state. Receipts
are scoped to the current capture and deduplicate repeated request IDs. Expired,
deleted or account-rebound captures cannot run. Sanitised receipts contain no image
URLs, provider messages or credentials. Existing IdentityEvent storage is reused;
no schema migration is needed. Live mode cannot be enabled by an environment flag.

## Remaining integration work once Signzy confirms the contract

* Confirm India endpoint, authentication, input formats, strict-mode/score semantics,
  reference image extraction, retries, billing and provider session identifiers.
* Confirm SDK/capture-path requirements. Our current normalised uploaded JPEG is
  not proof of trusted live camera capture and must not silently become such proof.
* Explicitly consent to biometric/liveness processing and reference-ID use; current
  image-storage consent is not automatically expanded by this change.
* Add owned private reference-document storage and short-lived signed URLs bound
  to the user/capture. Do not accept arbitrary evidence URLs from clients. URL
  validation in the pure mapper checks syntax only; it does not establish ownership.
* Add durable submission attempts, concurrency/idempotency protection, bounded
  outbound calls outside transactions, reconciliation and authenticated callbacks
  if supported. Do not blindly retry timeout submissions.
* Bind results to the exact capture, ID-reference version, account and policy;
  recheck consent/expiry/deletion before approval. Preserve provider request IDs.
* Confirm retention/deletion and accessible fallback review with the provider.
* Keep liveness, face match, ID authenticity and full BGV as distinct outcomes.

Signature styling and passport portrait changes are outside this adapter update.
