# Private identity capture and agreement signatures

## What this release adds

- Home → **Private identity check**, and the identity step within agreements.
- Native Android/iOS camera capture with review, retake and explicit upload consent. Photos are not saved to the gallery by this flow. A browser uses the file-picker fallback; neither path proves liveness.
- A normalized JPEG (metadata removed, whole image preserved, maximum 1200 × 1200) encrypted with Fernet in the database's private `IdentityCapture` table. It is never returned in profile, match or identity-status APIs. The public profile portrait remains separate.
- Captured → submitted → provider-approved/rejected status. Capture does not approve an identity. The app cannot submit approval results.
- A provider-approved identity check can be reused for 365 days, without repeating capture for each date. Changing the account phone/email, deleting the capture or expiry stops reuse. This check does not change the account's overall BGV badge or its other verification fields.
- Per-agreement typed electronic signatures, exact terms frozen at acknowledgement, explicitly selected terms, real UTC signing time, account/session provenance and SHA-256 checksums. Retry cannot replace a signature. The simulated week is not the evidence timestamp.
- OTP-free tester signatures/captures are explicitly labelled `tester_without_otp` in the evidence. Such a session does not establish ownership of the phone number.

This is not facial recognition, liveness testing, document-to-face matching or a certificate-backed digital-signature service. A typed acknowledgement is supported; a handwritten signature pad is not part of this release. Checksums detect accidental changes; they are not a qualified signature or independent timestamp authority. No legal validity claim is made.

There is no automatic vendor API call or webhook until the BGV firm's actual integration is available. Export and recording the provider's result are explicit operator actions. Do not record `verified` just to progress a rehearsal: use the existing simulation mode for that.

## Deploy in this order

1. On your Windows computer, from the repository, run checks and commit the change. No user/pair reset is needed.

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2
python -m pip install -r requirements.txt
python -m pytest -q
cd mobile
npm ci
npm test
npm run build
npx cap sync android
cd ..
git diff --check
git add after_date_api.py after_date_service.py api.py app.py ceremony.py codemagic.yaml db.py docs/openapi-phase4.json docs/identity-capture-and-signatures.md drift-check.sql identity_admin.py identity_capture.py planning_api.py planning_service.py requirements.txt schema.sql schema_postgres.sql test_identity_capture.py test_db_reconcile.py
git add mobile/package.json mobile/package-lock.json mobile/android/app/capacitor.build.gradle mobile/android/capacitor.settings.gradle mobile/scripts/configure-ios-privacy.py mobile/src/main.js mobile/src/nav.js mobile/src/preview.js mobile/src/screens/ceremony.js mobile/src/screens/home.js mobile/src/screens/identity.js mobile/tests/identity.test.js mobile/e2e/identity.spec.js
git diff --cached --stat
git commit -m "Add private identity capture and agreement signature evidence"
git push origin master
```

The commands deliberately omit the local `mobile/android/.idea/` directory. Stop if tests or the whitespace check fail.

2. Let Railway deploy the pushed commit. Keep `DHASHU_IDENTITY_CAPTURE_ENABLED=0` (or absent) for now. Existing beta face simulation continues. Run in the **Dream-Sim Railway service console**, not local PowerShell:

```bash
python -c "import db; c=db.get_connection(); db.init_db(c); print(db.reconcile_columns(c)); c.close()"
```

The schema change is additive. Existing signatures are not backfilled with invented historical evidence. Existing completed agreements are preserved.

3. Build **android-play** and **ios-testflight** from that same commit in Codemagic, distribute the builds and install them. Both platforms need a new version: the camera plugin and capture UI are packaged in the app. The iOS workflow applies camera/photo privacy descriptions after generating its project. No additional Android storage permissions are requested. Camera permission is requested only when taking a photo.

4. Generate one encryption key locally, after installing Python requirements:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Save this key in your password manager and Railway **Dream-Sim → Variables**, as `DHASHU_IDENTITY_ENCRYPTION_KEY`. Keep the same key across deployments; changing or losing it prevents decryption of existing images. Do not commit it or send it in chat. Restrict database and Railway access. Database backups can retain encrypted deleted images according to your backup policy.

5. Configure a daily scheduled maintenance command using the same database environment:

```bash
python identity_admin.py purge --apply
```

This deletes image ciphertext older than 30 days; identity outcome metadata and agreement records remain. Expired pending images are immediately unusable even before this command runs. **The code does not create a Railway cron job for you.** Schedule the command before enabling collection; deletion otherwise only happens when it is run manually. Exports and provider copies have their own retention and must be removed separately.

6. Set Railway `DHASHU_IDENTITY_CAPTURE_ENABLED=1` and redeploy only after updated apps are installed and the manual BGV handoff is ready. Leave all other simulation, clock, tester and pairing variables unchanged.

**This switch affects all users of this backend:** unfinished agreements now wait for a recorded provider approval. It intentionally disables the fake face success, even if `BETA_DATE_SIMULATION_ENABLED=1`. Older installed clients cannot capture photos and must be updated. Completed beta agreements remain completed; this does not retroactively authenticate them. Legacy HTML signing routes direct users to the updated app when this mode is on.

For a rehearsal without waiting for BGV, keep `DHASHU_IDENTITY_CAPTURE_ENABLED=0`. Do not enable real collection solely to accelerate tester progression.

## Manual BGV handoff

These commands are for the Railway application console, with a real capture created by the user. Replace the example user ID and placeholder capture ID/reference. A ZIP is a private temporary export, not an upload to the provider.

```bash
python identity_admin.py status --user-id test_blr_20260921_f06
```

Use its `capture_id` below. Export to a private location outside the repository and any public/media folder:

```bash
python identity_admin.py export --user-id test_blr_20260921_f06 --capture-id CAPTURE_ID --output /tmp/identity-review.zip --apply
```

The ZIP contains only `identity.jpg` and a manifest (capture ID, consent text/version, account ID, authentication method, timestamps and image checksum). It is **not encrypted**, so transfer it only through the provider's approved secure upload channel and delete your export afterwards. Do not email it by default, add it to Git or serve it from the app. The CLI refuses to overwrite an existing export.

After actually submitting to the firm, record the firm's name and submission reference:

```bash
python identity_admin.py submitted --user-id test_blr_20260921_f06 --capture-id CAPTURE_ID --provider "ACTUAL_VENDOR_NAME" --reference "SUBMISSION_REFERENCE" --apply
```

Only after receiving the firm's identity-authentication result:

```bash
python identity_admin.py result --user-id test_blr_20260921_f06 --capture-id CAPTURE_ID --provider "ACTUAL_VENDOR_NAME" --reference "RESULT_REFERENCE" --result verified --apply
```

Use `--result rejected` for a negative result. The capture ID, current account contacts and provider must match. Deleted, replaced, expired or unsubmitted captures cannot receive approval. Nothing here independently validates the firm's report: the operator must check it. There is deliberately no client-accessible approval endpoint.

Without `--apply`, mutation commands are previews and make no changes. `status` is read-only. The account's full BGV status remains unchanged.

The user then opens **Identity check → Refresh verification status**. In an unfinished agreement they choose **Use my approved identity check**. Their partner must still sign independently.

## Rollback and validation

Set `DHASHU_IDENTITY_CAPTURE_ENABLED=0` and redeploy to return unfinished agreements to the existing beta face behavior. Leave tables and the encryption key intact. This disables the stronger gate; use it for testing, not to claim provider approval. Stored images can still be deleted through the API and purged by the maintenance command.

Verify on physical iPhone and Android before collecting real user images:

1. Permission denied/cancelled → no upload; retake works; no gallery copy is created by the app.
2. Review image; consent is unchecked; only Save uploads. Check `captured`, with no verified badge from the upload.
3. A pending identity cannot complete the agreement, even with beta simulation enabled.
4. Approved check → complete this person's agreement; the partner's state remains independent.
5. Reopen/retry → signature timestamp and terms remain unchanged. An updated agreement needs a new agreement scope, not an overwrite.
6. Delete or change the assigned phone → future agreements cannot reuse the old check. A late vendor result for the old capture is refused.
7. Public match/profile responses contain no identity image or private receipt. Daily purge removes expired ciphertext.

Validation completed locally: **1,447 Python tests passed, 30 skipped; 88 mobile unit tests passed; 38 Playwright tests passed; production web build and Android `assembleDebug` succeeded.** The schema drift test now accepts digits in column names, needed by the SHA-256 evidence columns.

Automated tests cover the API, SQLite/schema parity, signature snapshots, provider handoff and browser capture interaction with a mocked camera. They do not test a real BGV service or physical camera. Production PostgreSQL, the iOS build and store distribution must be checked during rollout.

The existing asset-generation development dependency tree reports npm audit findings; the camera plugin is not listed among them. No unrelated dependency upgrades are included here.

Native permission reference: [Capacitor Camera documentation](https://github.com/ionic-team/capacitor-plugins/tree/main/camera).


## Temporary capture-only tester approval

Set `DHASHU_IDENTITY_TEST_AUTO_APPROVE=1` alongside
`DHASHU_IDENTITY_CAPTURE_ENABLED=1`. This requires a simulated clock, an enabled
account, and the existing OTP-free tester allowlist (`DHASHU_TESTER_NO_OTP=true`
and `DHASHU_TESTER_USER_IDS`). After consenting and saving a valid private image,
the Face tab offers Continue without provider approval. Existing unexpired
captures also qualify. Install the updated Android/iOS build to see this button.

The image remains captured/submitted, not provider-verified. Agreement evidence
records `face_method=test_capture` and its capture ID; BGV flags are unchanged.
Deletion, expiry, rejection, contact reassignment or disabling the flag prevents
reuse for new agreements. Completed agreements remain historical records.
Set the new flag to `0` to restore provider approval requirements. No schema
migration or journey reset is necessary.
