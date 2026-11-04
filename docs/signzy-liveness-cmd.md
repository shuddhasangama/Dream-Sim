# Liveness Secure standalone CMD test

This tester calls only Signzy preproduction. It does not write to the app database, replace m06's selfie/avatar, grant BGV approval, or deploy anything. It does not call OpenAI. Each command sends at most one Signzy request; there is no polling or automatic retry.

## 1. Open Windows Command Prompt

```bat
cd /d C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2
set "SIGNZY_ENV=preproduction"
python signzy_liveness_test.py create --prompt-key
```

Enter your own consented **Aadhaar portrait HTTPS URL**, then your sandbox API key at the hidden prompts. Do not use an avatar, a local file path, a document-page screenshot or the DigiLocker consent URL. The URL must serve the photo to Signzy without a login and remain accessible through capture. Its required lifetime is not yet confirmed. The runner never uploads a photo to an arbitrary hosting service or downloads the returned capturedImage.

If your existing encrypted eAadhaar receipt contains the Signzy-hosted portrait URL, avoid copying it manually:

```bat
python signzy_liveness_test.py create --prompt-key --aadhaar-receipt "C:\full\path\to\your-receipt.windows-dpapi.enc"
```

Replace the example path with your own receipt. An expired or missing vendor photo URL will need to be resolved before a valid comparison; this tester does not rerun DigiLocker automatically. Windows DPAPI receipts require the original Windows account. Fernet receipts require their original SIGNZY_RECEIPT_ENCRYPTION_KEY; do not change an existing encryption key.

Review the printed request and type YES to send. Default threshold is **0.6** and piiDeletionTTL is **6 months**, following the supplied Signzy example. The supported retention choices remain unconfirmed; `--retention "value"` can test a different Signzy-supported value. String switches are preserved exactly as supplied. The syntax error in the pasted TTL field is corrected.

Callback and redirect fields are **omitted by default** for a manual getData test. They are not known to be optional: if Signzy requires them, its validation response is saved and shown. No fabricated callback receiver is used. To supply real endpoints:

```bat
python signzy_liveness_test.py create --prompt-key --new-session --callback-url "https://your-receiver.example/liveness" --redirect-url "https://dhashu.com/"
```

The example receiver is a placeholder, not a deployed endpoint. Do not send that example verbatim. This phase does not test webhook authentication/delivery. Manual getData does not depend on receiving a webhook.

## 2. Complete hosted capture

Open the **private capture URL** printed by createUrl on the device you want to test. Permit Signzy camera access and complete its capture/review steps. Keep that link and token private. Leaving or redirecting from that page is not evidence of success.

## 3. Fetch the result from CMD

```bat
python signzy_liveness_test.py get --prompt-key
```

This loads the exact token from the most recent local create attempt's encrypted receipt; no token copy/paste is required. Enter the same sandbox key and type YES. You may deliberately execute get before capture to observe Signzy's actual pending response. Repeat **get**, not create, to inspect the same session later. Whether each retrieval is billable remains unconfirmed, so there is no automatic polling.

The result shows liveness, face match percentage, provider overall status, and additional checks separately. Combined passed is true only when all supplied required checks are explicitly true, isUsed is 1, and a valid score is present. Missing/changed shapes remain unconfirmed; liveness true with face match false never passes. A missing or mismatched returned token/consumer ID is flagged for review. No sandbox result changes app approval.

## Receipts and diagnostics

Full request and response are encrypted under `data\signzy-liveness-test`. The terminal redacts private URLs/identifiers by default, except the capture URL that you need to open. Authorization is never printed or stored in receipts.

For full private request/response in your own terminal:

```bat
python signzy_receipt.py "C:\full\path\to\the-printed-receipt.windows-dpapi.enc"
```

Alternatively add `--show-private` to a create/get command; do not share screenshots or terminal output containing tokens or photo URLs. Inspect an existing receipt rather than re-calling an API solely to see its response.

Another create call is blocked by default after a local attempt. Only use `create --new-session` when you intentionally want another potentially charged session after reviewing the previous attempt. A timeout may mean Signzy already created a session; do not blindly recreate it.

## Validated locally

Mocked transport tests cover direct/wrapped create responses, encrypted token handoff, pending/failed/incomplete checks, all-positive results, mismatched sessions, cancellation, production rejection, and a timeout with one request and no retry. Live sandbox acceptance, callback requirements, camera/device behavior, image URL reachability, expiry and billing remain to be tested with your own image. App integration follows this test; the existing app Face Match flow is unchanged.
