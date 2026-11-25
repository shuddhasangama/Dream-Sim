# Payments go-live (dec-pay)

Owner decision: **real charges, no free pilot.** All of this branch's work used Razorpay **test mode** only.

## Audit of the flow (2026-11-25)

| Step | Where | State |
|---|---|---|
| Plans / prices | `billing_catalog.PRODUCTS` (+ `DHASHU_BILLING_PRICES_JSON` overrides) | Server-owned, integer paise, market IN. A client can't send an amount (strict schema → 400). |
| Quote | `POST /api/v1/billing/quotes` | Web session + CSRF. Native app sessions are refused (store billing rules). |
| Checkout | `POST …/checkout` → Razorpay order / subscription | The order amount is the saved purchase amount. The provider is called through the `razorpay` circuit breaker; ambiguous failures are never auto-repeated. |
| Success / return | `billing.html` handler → `POST …/refresh` (reconcile with Razorpay) | Access is granted only from the provider's confirmation (reconcile or webhook), never from the browser callback. |
| Failure / cancel | checkout closed → "Use Check payment"; `cancel-subscription` for Guru | Nothing is assumed paid. |
| Webhook | `POST /billing/webhooks/razorpay` | HMAC-SHA256 signature required (unsigned or wrong → 401). Events older than `DHASHU_BILLING_WEBHOOK_MAX_AGE` (48 h) → 400. An exact duplicate is a no-op. |
| Entitlement | `billing_service.entitled` / `legacy_entitled` | In `live` mode every member is checked against real Razorpay entitlements. The simulated `/pay/…/confirm` is refused (403). |
| Receipt | Razorpay sends its own receipt email/SMS; purchase status on `/billing` | A DhaShu-branded receipt is a possible follow-up. |

## Settings

| Variable | Values | Default | Notes |
|---|---|---|---|
| `DHASHU_BILLING_MODE` | `disabled`, `sandbox`, `live_pilot`, `live` | `disabled` | `live` = real charges at catalogue prices for everyone. |
| `PAYMENTS_ENABLED` | `1` / `0` | `1` | The **payment gate**: whether paid features require payment at all. |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | | | Live mode requires `rzp_live_…`. |
| `RAZORPAY_WEBHOOK_SECRET` | 16+ characters | | Must equal the secret in the Razorpay dashboard webhook. |
| `RAZORPAY_GURU_TEST_PLAN_ID` | `plan_…` | | Guru monthly plan; its amount must match the catalogue. |
| `DHASHU_BILLING_WEBHOOK_MAX_AGE` | seconds | 172800 | |

**Startup refusal:** in production (`RAILWAY_ENVIRONMENT_NAME=production`) with billing on, the web process **will not start** unless it has a live key id, the secret and a webhook secret. Test keys and `sandbox` are refused there. The message names the variables, never their values.

## Switching to live (Railway, owner only)

1. Razorpay dashboard → Settings → API Keys → generate **Live** keys. Copy them only into Railway.
2. Razorpay dashboard → Webhooks → add `https://<your API host>/billing/webhooks/razorpay`.
   - Events: `payment.captured`, `refund.processed`, `refund.failed`, `subscription.charged`, `subscription.cancelled`, `subscription.completed`.
   - Set a long random secret.
3. If Guru is sold: create the monthly Guru plan at the catalogue price, then copy the `plan_…` id.
4. Railway → web service → Variables (sealed):
   - `RAZORPAY_KEY_ID=rzp_live_…`
   - `RAZORPAY_KEY_SECRET=…`
   - `RAZORPAY_WEBHOOK_SECRET=…`
   - `RAZORPAY_GURU_TEST_PLAN_ID=plan_…`
   - `DHASHU_BILLING_MODE=live`
   - `PAYMENTS_ENABLED=1`
5. Deploy. If anything is missing, the deploy fails at startup with the variable names; fix and redeploy.

## ₹1 smoke test (before opening to members)

1. Set `DHASHU_BILLING_PRICES_JSON={"verification":100}` (₹1) **temporarily**, and deploy.
2. Sign in on the website with your own account → `/billing` → Verification → **Review price** (shows ₹1.00) → **Pay ₹1.00** → pay with your own UPI or card.
3. The page shows "Purchase: paid" after Check payment; Razorpay dashboard → Payments shows the ₹1 payment captured; Webhooks shows a 200 delivery.
4. Razorpay dashboard → refund the ₹1 → `/billing` → Check payment shows the refund.
5. **Remove** `DHASHU_BILLING_PRICES_JSON` and deploy. Review price now shows the catalogue price.

## Rollback

Set `DHASHU_BILLING_MODE=disabled` (checkout stops at once). Paid entitlements stay in the database.
