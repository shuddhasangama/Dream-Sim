# Modular Signzy testing

Shared server-side client: `signzy/client.py`. Operation modules own request validation,
fixed relative paths and sanitised response interpretation. Registry accepts only named
operations; new APIs require a reviewed module and tests, not arbitrary URLs.

## Available operations
- `employment_history`: POST /api/v3/underwriting/fetch-employment-history, supplied
  request/response contract. Run `python signzy_test.py employment_history`.
  Hidden prompts collect pan, mobile, uan, dob and employeeName; blanks are sent as
  empty strings as in the supplied request. Local validation requires at least one
  PAN/mobile/UAN; Signzy must confirm accepted field combinations and request DOB
  format. No DOB format is inferred from the response. The supplied URL is production;
  the tester uses the same relative path in preproduction without fallback.
  Summary exposes record count and limitedOutput only, never employer/identity data.
  Full response is encrypted; empty/limited history is not proof of unemployment,
  completeness or current employment. No automatic comparison, --user-id support
  or app pilot wiring is added. Live availability/access and billing remain untested.
- `pan_extensive`: POST /api/v3/panextensive; panNumber required, getStatusInfo optional boolean.
  Response examples supplied; live testing deferred. Name and DOB matching stay
  not_evaluated until comparison rules are implemented. HTTP200 means response
  received, not verified.
- `current_employer`: supplied current-employer request/response contract. Employment
  evidence is for review; is_employed=false is not proof of unemployment.

## Environments
Preproduction: https://api-preproduction.signzy.app/api/v3
Production: https://api.signzy.app/api/v3

Separate templates: `.env.signzy.test.example` and `.env.signzy.production.example`.
These are configuration references, not auto-loaded files. Set environment variables
through the shell/deployment service if needed. Test CLI stops if the test key is missing.
Never use the key exposed in chat. Production uses only SIGNZY_PRODUCTION_API_KEY,
requires SIGNZY_ENV=production and SIGNZY_PRODUCTION_ENABLED=1. The CLI refuses
production even with that flag. Actual production credential validity cannot be inferred
locally; use the provider-issued environment-specific key.

## Run in PowerShell or CMD from repository root
```
python signzy_test.py pan_extensive
python signzy_test.py current_employer
```
Configure SIGNZY_TEST_API_KEY once using local environment variables or Railway service
variables. The tester does not prompt for credentials. PAN Extensive prompts only for PAN
and always sends getStatusInfo=true. Entering the PAN submits the request; use only
consented test data. Current employer still needs both PAN and mobile. One billable request
at most. No retries or redirected requests. Local variables and Railway variables are
separate; Railway configuration does not configure your local terminal.

## Complete private receipts
The tester writes two files with the same receipt ID under ignored data/signzy-test-receipts:
- `.summary.json`: allowlisted status fields for sharing. This is our interpretation,
  not the original Signzy response.
- `.windows-dpapi.enc` (Windows default) or `.fernet.enc`: encrypted request inputs,
  complete provider JSON (including unknown fields), original response bytes,
  HTTP status, selected response correlation headers, UTC start/end times, and a
  separately labelled wrapper summary. Request Authorization is not stored.

Windows encryption uses the current Windows account automatically. Keep that account
and its protection keys; copying the file to another computer/account may not allow
decryption. Non-Windows hosts require SIGNZY_RECEIPT_ENCRYPTION_KEY, a Fernet key,
configured securely and retained separately. Railway also needs persistent private
storage before using these files as lasting records. This is a local testing facility,
not the production BGV evidence store.

View a receipt privately using the exact path printed by the tester:
```
python signzy_receipt.py "data/signzy-test-receipts/<receipt-id>.windows-dpapi.enc"
```
This prints personal data to your terminal, without creating a plaintext file. Do not
share that output, screenshots, or private receipts. Share the summary instead.
Provider error bodies are retained too. Timeouts have no response; responses above
2 MB are explicitly marked incomplete. Encryption/writability is checked before the
request. A save failure after sending warns against retrying a potentially billable call.
Old summary-only receipts cannot recover previously discarded provider data.

The legacy signzy_probe.py does not persist full receipts; use signzy_test.py for this.
The x-client-unique-id value follows the supplied example (partners@dhashu.com);
it is not assumed to be an idempotency key. Confirm its production semantics with Signzy.

The old signzy_probe.py command delegates its network call to the same wrapper.
No public HTTP routes, user/account updates, automatic BGV approval, biometric transport,
database migration, background jobs or deployment changes are introduced.
Consent confirmation in the local runner is for operator testing; production needs
stored purpose-specific consent and an authenticated, authorised backend caller.

Validation: python -m unittest test_signzy_client test_signzy_probe test_signzy_receipts -q
All tests use synthetic data and mocked transport, never real credentials or API credits.

## PAN Simple and automatic field evidence
`python signzy_test.py pan_simple` prompts only for PAN, using the existing test key.
The fixed sandbox path is `/api/v3/pan/simple`; no getStatusInfo is sent.

To associate a NEW request with a known database test user:
```
python signzy_test.py pan_simple --user-id <actual-user-id>
python signzy_test.py current_employer --user-id <actual-user-id>
```
This mode prompts for the user's declared legal name and ISO DOB (PAN Simple), or
current employer (employment), before collecting the API inputs. The operator must
use that user's consented data. It creates the additive BgvEvidence table if needed,
then automatically saves encrypted evidence and field outcomes to the configured DB.
Use the same database configuration as the target application. Local runs do not
write to Railway unless explicitly configured for that database.

Declared and provider values are separate inside encrypted protected_details.
fields_json stores only per-field statuses. Each receipt is append-only and unique.
Old evidence is not promoted over new evidence: rows describe individual attempts,
not a mutable overall user badge. Sandbox evidence stays labelled preproduction.
No User.bgv_status, user-entered profile values or matching eligibility is changed.

The backend entry point is signzy.verification.ingest(conn, evidence, store).
A trusted backend caller must bind the authenticated user and a snapshot of their
stored declarations before calling it. Current app display names are generated and
are not a legal-name source. Signup/API route wiring and production consent capture
are still required before this can run unattended for app users. No unauthenticated
public importer is exposed.

For a saved, user-bound receipt, retry database processing without paying again:
```
python signzy_import_receipt.py "<encrypted-receipt-path>"
```
Receipts created before --user-id binding cannot be automatically assigned to a user.
They are still privately viewable. Do not infer ownership from a name or mobile.

Matching rules: valid individual PAN only; names compare with Unicode, case and
whitespace normalization, not fuzzy matching; DOB compares ISO date exactly.
Mismatches/missing declarations are unverified; one matching field is partially
verified; invalid/business/malformed results fail to verify the individual. Historical
employment does not verify a current employer. A technical failure is failed_to_verify,
not evidence of fraud. Full response remains available for review.

Errors: invalid_input, authentication_failed, access_denied, rate_limited,
provider_unavailable, provider_error, credits_unavailable and
network_error_outcome_unknown. Credit classification uses explicit insufficient/
exhausted credit wording; Signzy has not supplied a definitive credit-error contract.
Unknown errors remain generic, with original details encrypted. No automatic retries.

Validation:
python -m unittest test_signzy_client test_signzy_probe test_signzy_receipts test_signzy_verification -q

## Court search and UAN passbook sandbox probes
```
python signzy_test.py individual_search
python signzy_test.py uan_passbook
```
Court search asks for name and address; matchType defaults to `exact` in the CLI.
Use `python signzy_test.py individual_search --match-type possible` to request possible matches.
Add `--case-category criminal` or `--case-category civil` to test each category
explicitly. Each invocation sends one search only, with a separate private receipt.
New search summaries record `match_type` and `case_category` (no personal inputs).
Run both searches with the same consented name/address for a controlled comparison.
Result retrieval remains a separate call using that search's encrypted receipt.
The operation module also accepts optional fatherName, civil/criminal caseCategory,
and petitioner/respondent type. Blank optional values are omitted. DOB is deferred
until Signzy confirms the wire date format. No court response schema was supplied:
responses are preserved privately, with no automatic clearance or adverse finding.

Passbook asks for a consented 12-digit UAN. consentFlag=Y and ttl=0 are fixed in the
CLI. No callback URL or cutoff is sent. The wrapper validates optional cutoff/ttl,
but rejects nonempty callbacks until a secure callback receiver is implemented.
The supplied passbook URL is production; the tester uses the same relative path on
api-preproduction.signzy.app by existing environment configuration. Sandbox availability
and entitlements remain to be confirmed by a real run; it never falls back to production.

Both use the existing API key, shared error classification and encrypted receipts.
HTTP 202 means accepted/pending, not verified. Unknown HTTP 200 response shapes are
marked for contract review. No polling, callback listener or automatic retries are added.
The 45-second client timeout may occur before provider work finishes; check provider
logs before repeating a timed-out request. Neither operation currently permits --user-id:
field-comparison rules must first be defined against real response contracts.

Use signzy_receipt.py with the printed encrypted filename to inspect the full response
privately. Share only the summary/HTTP status and trace ID when troubleshooting access.

## FIR two-step testing

New operations: `fir_search` POST /api/v3/fir/search and `fir_result` POST /api/v3/fir/result.
Run `python signzy_test.py fir_search --match-type possible` (or exact). Hidden
prompts collect consented name, address and optional fatherName. No sample personal
inputs are hardcoded. A separate call uses the resulting encrypted receipt:
`python signzy_test.py fir_result --search-receipt "<FIR-search-private-receipt>"`.
This explicitly maps response searchId to request verifyId, as supplied by the user.
No automatic polling/retries, app wiring, user binding or clearance decisions.
Both calls save complete encrypted evidence and sanitised summaries.
The attached result example reports Processing done and 500 candidates; do not
interpret candidate counts, numeric type, scores, or empty lists as confirmed
identity, guilt or clearance. Confirm state coverage, processing states, result
limits/pagination, role codes, matching scores and lookup billing with Signzy.
Supplied sample is contract material, not evidence of our live FIR test.
Offline regression after this addition: 67 tests passed. Live FIR tests pending.
