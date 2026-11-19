# MSG91 app signup release

This release changes backend SMS delivery only. No user reset, database migration,
mobile rebuild, or Investor Room changes. Existing passwords/sessions stay valid.

## Publish this isolated release

PowerShell:
```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-msg91-release
 git add auth_delivery.py tools/signup_diagnostics.py test_msg91_delivery.py docs/msg91-signup-deployment.md
 git diff --cached --stat
 git commit -m "Support MSG91 for app signup OTP"
 git push origin HEAD:master
```
If rejected, stop; never force-push. Railway Dream-Sim must track master.

## Railway Dream-Sim service variables

First deploy code with the existing Twilio setting/default. Then add these together
and apply/redeploy:

| Variable | Value |
|---|---|
| DHASHU_SMS_PROVIDER | msg91 |
| MSG91_AUTH_KEY | Your MSG91 Authkey, entered privately in Railway |
| MSG91_TEMPLATE_ID | 6afe818d3d9bb415b50fd153 |

Template ID transcribed from the supplied DhaShuSignup screenshot; compare with
MSG91 Copy Template ID before saving. Do not use a widget token or DLT entity ID.
Keep existing TWILIO_* values for rollback and in-flight Twilio challenges.
Do not put these variables on Postgres, dhashu-admin or bgv-worker.
No custom endpoint, sender ID or separate DLT ID is required by this SendOTP API.
MSG91 account credit, enabled SMS service and any configured IP restrictions must
permit requests from Railway. Successful portal testing alone does not prove this.

## Validate

In the deployed Dream-Sim shell:
```sh
cd /app
PYTHONPATH=/app /app/.venv/bin/python tools/signup_diagnostics.py
```
Expect SMS provider: msg91 and Selected provider configuration format valid: True.
This checks configuration presence/format, not SMS delivery or key validity.
Test Signup in the app with a consented new Indian phone number. Confirm MSG91
SendOTP logs, delivery, wrong-code rejection, then successful code verification and
onboarding. Test existing-user login and resend after the 60-second cooldown.
Never delete users to switch providers. Verify provider rejection/network failure
returns a controlled error and no account is created before verification.

## Behavior / rollback

MSG91 generates six-digit codes with ten-minute expiry. The app's existing rate
limits, five-attempt challenge limit and one-time consumption remain active.
India-only validation requires +91 followed by ten digits starting 6-9.
HTTP 200 alone is not approval; exact verified-success response is required.
No automatic cross-provider retry: avoids duplicate SMS/charges.
Stored provider references route pending challenges to their original provider.
Set DHASHU_SMS_PROVIDER=twilio and redeploy to roll back; retain both providers'
credentials until pending codes expire. No mobile build is required for this switch.

Provider docs: https://docs.msg91.com/otp/sendotp and
https://docs.msg91.com/en/otp/verify-otp

All automated tests use mocked delivery. Live Railway delivery must be checked
after setting secrets; no SMS was sent during implementation.
