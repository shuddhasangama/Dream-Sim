# MSG91: SMS codes for sign-up, sign-in and resend

Owner decision (2026-11-27): the client moved from Twilio to **MSG91**. MSG91 is the default
SMS provider (`DHASHU_SMS_PROVIDER` unset = `msg91`). Twilio is never required; it remains
only as an optional fallback (`DHASHU_SMS_PROVIDER=twilio` with the `TWILIO_*` settings).

## One-time MSG91 / DLT setup (owner, outside the code)

1. **DLT registration** (Indian telecom rule for every commercial SMS): register the business
   entity (PE id) on an operator DLT portal (Jio, Vodafone Idea, Airtel, BSNL…), then register
   the **sender id** (header, e.g. 6 letters) and wait for approval.
2. **OTP template on DLT:** register the OTP message text with a variable for the code, category
   "Service Implicit" / OTP, and note the approved **DLT template id**.
3. **MSG91 dashboard → OTP → Templates:** create the OTP template with the same text, choose the
   approved sender id and enter the DLT template id. Copy the MSG91 **template id** (24 hex).
4. **MSG91 dashboard → Authkey:** create an auth key for the server. If you whitelist IPs on it,
   Railway's egress must be allowed (or leave the whitelist off).
5. Top up the account and set a low-balance alert.

The DLT template id and the sender id live on the MSG91 template. The app's SendOTP request
selects them through `MSG91_TEMPLATE_ID`, so they are not separate Railway settings.

## Railway variables (web service only)

| Variable | Where the value comes from |
|---|---|
| `MSG91_AUTH_KEY` | MSG91 → Authkey (sealed variable) |
| `MSG91_TEMPLATE_ID` | MSG91 → OTP → Templates → the template's id (24 hex) |
| `DHASHU_SMS_PROVIDER` | leave unset (defaults to `msg91`) |

`AUTH_ENABLED=1` refuses to start without a valid MSG91 configuration and names the variables
(never their values). Do not put MSG91 values on the worker or admin services.

## How the app uses MSG91

- Sign-up (`/api/v1/auth/signup/request`), sign-in (`/api/v1/auth/request`) and resend (the same
  request again after the 60-second cooldown) send through MSG91 SendOTP: six digits, ten-minute
  expiry, Indian mobile numbers only (+91, 10 digits starting 6–9).
- Verification calls MSG91 verify; only the exact "OTP verified success" reply approves a code.
  A new request replaces the previous code for that number.
- Limits that apply unchanged: 5 codes per number per day, 20 requests per 10 minutes per
  visitor, the hourly global breaker (`DHASHU_OTP_GLOBAL_PER_HOUR`, alert `otp_global_breaker`)
  and the 600 ms timing padding.
- MSG91 calls go through the `msg91` circuit breaker: 5 consecutive outages open it, requests then
  fail fast with a clear "could not send" message and the `otp_provider_down` alert fires.
- No automatic cross-provider retry (no duplicate SMS charges). A pending code always verifies
  with the provider that sent it.

## Check after deploy

In the Railway web shell: `cd /app && PYTHONPATH=/app /app/.venv/bin/python tools/signup_diagnostics.py`
should show `SMS provider: msg91` and `Selected provider configuration format valid: True`
(format only, not delivery). Then sign up with your own number, enter one wrong code (refused),
then the right code; sign out and sign in again; wait 60 s and resend.

All automated tests mock MSG91 (`test_msg91_delivery.py`, `test_msg91_primary.py`). No SMS is sent by tests.
