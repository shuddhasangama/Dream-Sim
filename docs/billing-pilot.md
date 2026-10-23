# DhaShu payment pilot

## Delivered and boundaries

The new BillingPurchase / BillingEntitlement ledger is separate from simulated Payment rows.
It supports a browser checkout, Razorpay one-time orders, a monthly Guru subscription,
signed notifications, status reconciliation, full one-time refunds and subscription cancellation.
The default is disabled. Existing testers outside the configured payment cohort retain their
existing simulation. No real credentials are included and no live payment has been tested.

Catalogue prices (integer paise): verification 199900; date_mechanics 99900;
relationship_entry 99900; Guru 19900/month; engagement_marriage 199900 combined.
Prices are per user. Both ceremonies share one entitlement per Couple. The future active-Guru
dependency is catalogue metadata only, not enforced. Verification payment does not mark BGV
as verified. Date mechanics covers availability and agreement; cancellation penalties are not
automatically collected. Verification/combined ceremony access enforcement remains an explicit
future journey integration; purchase and entitlement are available now.

This release intentionally only activates INR 1 pilot pricing. Production prices are stored
and versioned but production checkout is not enabled until tax, store rules and merchant approval
are resolved. `DHASHU_BILLING_PRICES_JSON` overrides catalogue amounts, not pilot charges.
Changing it never reprices an existing quote, order or recurring mandate. Guru subscriptions are
monthly, at INR 1, for up to 12 cycles, and require explicit acceptance. No automatic upgrade to INR 199.

Native bearer sessions cannot launch external digital checkout. Apple IAP / Google Play Billing,
Cashfree, Apple Pay and Bizum adapters are NOT implemented. Gateway checkout supplies supported
cards/UPI methods; do not advertise a particular wallet without merchant/device/country validation.
Opening this page inside a native app is not a substitute for store billing compliance.

## Deploy in sequence

1. Run the tests below and commit the listed billing files plus schema/API bridge changes.
   Push the commit; deploy Railway. Keep billing disabled initially. Schema creation is additive
   through the existing db.init_db startup mechanism (SQLite and PostgreSQL schemas match).
2. Obtain Razorpay test credentials and configure automatic capture. Do not paste credentials in chat.
3. Set Railway variables:

```text
DHASHU_BILLING_MODE=sandbox
DHASHU_BILLING_MARKET=IN
DHASHU_BILLING_TESTERS=test_blr_20260921_f06,test_blr_20260921_m06
DHASHU_BILLING_PRICE_VERSION=india-v1
RAZORPAY_KEY_ID=<rzp_test_...>
RAZORPAY_KEY_SECRET=<test key secret>
RAZORPAY_WEBHOOK_SECRET=<independent random webhook secret>
RAZORPAY_GURU_TEST_PLAN_ID=<plan_...>
```

   AUTH_ENABLED must be enabled and AUTH_PUBLIC_ORIGIN must match the backend browser origin
   exactly (for example https://your-backend.up.railway.app, without a trailing slash).
   Create the Guru plan in the same Razorpay test account:
   INR 1 (100 paise), monthly interval 1, no extras. The service verifies the plan on purchase.
   Any existing eligible user can be added to DHASHU_BILLING_TESTERS; no IDs are hardcoded.
4. Configure the test webhook URL:
   `https://<Railway-or-backend-domain>/billing/webhooks/razorpay`.
   Subscribe to payment.captured, subscription.charged, subscription.cancelled,
   subscription.completed, refund.processed and refund.failed. Use the matching webhook secret.
5. Sign into the actual backend website in a browser, then open `/billing` on that same origin.
   This is not a static GitHub Pages URL. No Codemagic build is needed for this browser pilot.
6. Select the product. Verification/Guru need no reference. Date mechanics and relationship
   entry need an active LockIn ID belonging to the signed-in user. Engagement + Marriage needs
   the user's Couple ID. Review the quote, accept recurrence if applicable, then pay with provider
   sandbox instruments. Refresh to reconcile; app redirects alone never grant access.
7. Confirm the webhook succeeds and both payment and entitlement are recorded. Test one user,
   then the second. A date-mechanics purchase is per user, not a payment for both partners.

## Operational commands (Railway shell)

```sh
python billing_admin.py status --purchase-id <id>
python billing_admin.py reconcile --purchase-id <id>
python billing_admin.py refund --purchase-id <id> --apply
```

Schedule reconciliation for pending purchases if unattended recovery is needed; this release
provides the CLI and browser refresh, not a scheduler. Webhooks normally finish payments even
when the browser closes. Subscription reconciliation checks paid invoices and their billing end;
an active mandate alone grants no access.

If create-order/create-subscription times out without a provider reference, the purchase stays
`reconciling`. Do not create another charge. Locate its receipt/notes in the provider dashboard
and investigate. Automated recovery without a provider ID is intentionally not guessed.
Refund request timeouts also remain requested until investigated. Refund completion and purchase
completion are different states. Subscription refunds should currently be performed through
provider operations; do not use the one-time refund CLI for them.

## Optional live INR 1 pilot — only after sandbox acceptance

Activate merchant account first. Use a small explicit tester cohort, live keys, live webhook secret
and a LIVE monthly INR 1 plan. Set `DHASHU_BILLING_MODE=live_pilot` and
`DHASHU_BILLING_LIVE_ACK=charge-real-money`. This moves real money. Never reuse test plan IDs.
Sandbox entitlements do not unlock live-pilot purchases. The current UI explicitly identifies live
pilot charges. Other countries fail closed until an adapter, currency and price configuration exist.

Rollback: set DHASHU_BILLING_MODE=disabled. This restores existing simulation gates without
deleting the financial ledger. Cancel any LIVE recurring subscriptions at the provider before
disabling; disabling our code does not cancel a mandate. Re-enable to process delayed events.

## Verification

```sh
python -m unittest test_billing_service test_billing_api test_payments test_schema_postgres test_date_cycle_api -q
```

Tests use isolated databases and fake gateway responses. Real provider credentials, settlement,
refund timelines, browser checkout and PostgreSQL deployment still require sandbox acceptance.

Reference: https://razorpay.com/docs/server-integration/python/test-app/
Reference: https://razorpay.com/docs/api/payments/subscriptions/create-plan/
