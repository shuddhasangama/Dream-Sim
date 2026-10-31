# App verification flow

## What ships
The authenticated mobile Verify screen submits the selected check, declarations and
versioned consent. API requests are bearer-only, owner-scoped and rate-limited.
Inputs and complete provider evidence are encrypted with Fernet; public status APIs
return no PAN, UAN, address, legal name, provider documents or raw error messages.
No generic profile/match API receives this private evidence.

The queue commits before calling Signzy. A separate worker prevents the mobile HTTP
request timing out while a check runs. Duplicate active checks and repeated request
IDs cannot trigger duplicate calls. Consent and declarations are immutable snapshots
per attempt; correction means a new consented attempt after the earlier one finishes.
Name/DOB comparison is exact after name whitespace/case normalization. Current employer
requires current-employment evidence. Court and passbook results require review.

Provider failures show Check unavailable, not an incorrect declaration. HTTP 202
stays pending. A worker interruption stays processing, or outcome_unknown if caught;
there is deliberately no automatic retry of uncertain, potentially paid requests.
Support must inspect the provider logs before resolving such attempts. Async callback
contracts and an operations review console remain future work. Raw responses are saved
before comparison. These checks never modify overall User.bgv_status or unlock matching.

## Deploy after review
1. Commit the reviewed Signzy modules plus bgv_app.py, bgv_app_api.py, bgv_worker.py,
   api.py, journey_api.py, db.py, both schemas, tests and mobile Verify screen/main.js.
   Do not stage receipts, keys, node_modules, unrelated files or generated assets.
2. Deploy the API on Railway and run db.init_db with the environment's Python executable.
3. Set these on BOTH the API service and a worker service sharing the SAME database:
   DHASHU_BGV_APP_ENABLED=1
   SIGNZY_ENV=preproduction
   SIGNZY_TEST_API_KEY=<replacement preproduction key>
   SIGNZY_RECEIPT_ENCRYPTION_KEY=<one securely generated Fernet key>
   Keep SIGNZY_PRODUCTION_ENABLED=0. Do not paste keys into chat or source control.
   Generate the Fernet key once in a private terminal with:
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   Back up the key securely; losing/changing it prevents reading saved evidence.
4. Worker start command: python bgv_worker.py
   For a controlled single-request test: python bgv_worker.py --once
   Use /app/.venv/bin/python on Railway if python is not in PATH.
5. Rebuild Android/iOS through Codemagic because a new mobile screen is included.
6. Open Verify from the profile navigation. Submit your own consented test details;
   refresh to see queued, processing and the result. Both the receipt and DB evidence
   remain sandbox-labelled. Provider entitlements (PAN Simple currently denied) must
   be enabled by Signzy; deployment cannot resolve those permissions.

This iteration integrates the installed app. It does not add a web onboarding form,
face/liveness transport, overall BGV approval, retention/deletion policy automation,
or provider-specific async callbacks. Production rollout needs those operational
policies and provider access agreed; keep this pilot in preproduction meanwhile.

## Tests
python -m unittest test_bgv_app test_signzy_client test_signzy_receipts test_signzy_verification test_signzy_additional -q
python -m pytest test_schema_postgres.py test_journey_api.py -q
cd mobile
npm.cmd test
npm.cmd run build
