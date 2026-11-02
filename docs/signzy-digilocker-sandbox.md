# DigiLocker sandbox test

Source: supplied createUrl/geteAadhaar cURL contracts, 2 November 2026.

The test is two explicit requests: create a consent link, let the person complete
OTP/consent themselves, then fetch identity data by the SAME saved requestId.
No app account, BGV badge, contact verification or matching state is updated.

## Data requested

Create URL requests ADHAR only. getBase64Files, getEAadhaarPdf and getEAadhaarJpeg
are false. Retrieval also disables PDF/JPEG and sets extraDigitalCertificateParams
to the string "false", matching the supplied wire example. Only name, dob and
address are projected by the private field viewer. DOB is retained as returned;
no interpretation or automatic verification is added. Photo/document URLs are
never fetched. Full provider responses are encrypted in the existing receipt store.

## Local Windows commands

Configure SIGNZY_ENV=preproduction and SIGNZY_DIGILOCKER_CALLBACK_BASE to:
https://dream-sim-production.up.railway.app/public/signzy/digilocker/callback

Run from the repository root:

```powershell
python signzy_test.py digilocker_create_url --prompt-key
```

Enter the sandbox key only into the hidden terminal prompt. Enter the service
name registered with Signzy. A unique callback suffix and internal ID are generated.
The private consent URL is displayed ONLY in the operator's terminal; open it and
complete consent personally. Do not use the example requestId from the documentation.

```powershell
python signzy_test.py digilocker_eaadhaar --prompt-key --create-receipt "<encrypted create receipt>"
python signzy_digilocker_fields.py "<encrypted eAadhaar receipt>"
```

The first command asks whether THIS session's consent is complete. The second
prints personal data privately: do not paste its output into chats or logs.
The ordinary summary reports only whether each requested field was received.
Windows receipts use DPAPI unless SIGNZY_RECEIPT_ENCRYPTION_KEY is configured.
Railway/non-Windows receipt writing needs a separately managed persistent key.

## Callback boundary

The callback is a sandbox acknowledgement only, enabled by
SIGNZY_DIGILOCKER_SANDBOX_CALLBACK_ENABLED=1 and SIGNZY_ENV=preproduction.
Its per-session URL suffix is 32 random hexadecimal characters. It does not read,
echo, store or trust notification contents and cannot approve identity or consent.
The explicit authenticated provider retrieval is the source of test evidence.
Production callback verification, user/session binding and app orchestration are
separate future work; do not enable this as an automatic production BGV flow.

No automatic retries or polling. Timeouts can mean the request executed; review
the encrypted receipt/provider logs before another request.
