# Face Match app pilot — 4 November 2026

Uses Signzy preproduction `/face/match` at diagnostic threshold 0.5. Passive liveness remains not checked; Smart Verification is not invoked. No dating, relationship, Guru, overall BGV or eligibility rules change.

## Tester steps

1. Install the new app build.
2. Complete DigiLocker with Aadhaar photo sharing in Verify. A current, completed owner-bound session with an unexpired cached portrait is required. Existing DigiLocker sandbox allowlists/case assignments are unchanged; accounts without access can continue other journeys while awaiting identity setup.
3. Home → Your AI avatar: capture the latest selfie, consent to avatar generation and submit its one two-option run. This locks the selfie source. An existing submitted avatar run can reuse its still-valid original selfie; another avatar generation is neither required nor allowed.
4. In Your AI avatar or Verify, find Selfie → Aadhaar. Read the separate Signzy consent and tap Compare selfie with Aadhaar.
5. Refresh face status. Observe Face matched / Does not match / Queued / Support review, the returned percentage, and Liveness not checked. These statuses do not approve an account or block the other test flows.

## Backend boundaries

`FaceMatchJob.id` permanently reserves one sandbox comparison per user. The saved original selfie and original cached Aadhaar portrait are snapshotted encrypted with source hash/session and consent. Generated avatars never enter this request. Avatar source replacement is already blocked after avatar submission, preventing a face result from silently moving to a different selfie.

The worker commits an atomic claim before IO, creates a five-minute opaque private image lease, submits once with `detectMask: [selfie URL]`, seals the response, and revokes/wipes the lease in finally. Empty mask lists are rejected by the vendor and adapter. Expired sources, missing Aadhaar, other-user sessions and duplicate requests cannot trigger calls. Timeouts/errors/worker interruption become unknown and cannot be replayed automatically. Removing avatar images also withdraws face snapshots/results and revokes leases while retaining the once-only ledger.

The result API exposes summary/percentage only to the authenticated owner. Public avatars remain Verification pending because liveness is not established. Existing manual CLI test results are not imported as app approvals. No new Signzy credential is needed. Enable `DHASHU_FACE_MATCH_ENABLED=1` on API and bgv-worker; reuse the existing sandbox key and stable encryption key. Deploy the API/additive table before the worker.

The face adapter/result projection is separate from avatar generation. Smart Verification can later add a separate liveness outcome after its contract/access are tested; existing face-only results must not be relabeled as liveness passes or automatically retriggered.

The two observed manual sandbox scores (99% identity pair, 98% avatar pair) are not threshold calibration or anonymity evidence. Confirm whether sandbox outputs are computed or fixtures before production decisions.
