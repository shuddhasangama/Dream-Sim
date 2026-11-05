# Verification sandbox payment and identity — 5 November 2026

## Checkout

An account-bound Razorpay Payment Link now precedes DigiLocker in the app. The button says Begin verification · test payment. Copy explicitly distinguishes ₹0 real money deducted from the ₹1 simulated amount shown by Razorpay. The existing configured sandbox credentials are reused; no new credential or Railway variable was added. The old billing tester allowlist is not widened: this separate native-compatible endpoint permits authenticated users only while DHASHU_BILLING_MODE=sandbox and the adapter has an rzp_test_ key. Live mode is blocked; existing native live-purchase restrictions remain.

The existing BillingPurchase/BillingEntitlement ledger records each link. A saved creating/pending/uncertain purchase is reused; ambiguous creation is not replayed. Opening or returning from the link never grants access by itself. On native browser return, the backend fetches the bound link, validates account reference, amount/currency, paid total, captured payment, matching order and refund status before granting the sandbox verification entitlement. Web users can explicitly check confirmation after completing the link. Payment confirmation does not approve BGV or admit the account to matching. The DigiLocker creation service enforces the entitlement server-side in sandbox mode. Existing in-flight consent sessions can finish.

GET /verification/payment is a local ledger read. POST /verification/payment/start creates or reuses checkout. POST /verification/payment/complete reconciles with Razorpay. Status polling does not create payments or charge money. These endpoints require app bearer authentication; clients cannot submit amount, user ID, provider result or a payment success flag.

Existing billing/webhook matching also recognises the link's saved order mapping. Confirmation on browser return remains necessary when no webhook/order mapping has arrived. No additional webhook subscription is required for this sandbox test flow.

## Confirmed identity

Successful adult DigiLocker completion atomically saves the encrypted identity result and updates the account's Stats age, identity session pointer and environment. The legal name and exact DOB stay in the protected DigiLocker record, not raw public Stats. The owner's Stats response exposes the canonical identity to that owner. Manual age edits are rejected once linked to confirmed DOB. Replay of an already-completed consent applies the saved evidence without another vendor call. Failed, pending and underage results do not overwrite profile age.

Own journey/session display names use the confirmed name. A match sees the confirmed name only through the existing name-reveal gate after meeting; masking before that stage remains. Overall BGV status is unchanged. An existing completed session is adopted into its owner’s profile once when that owner opens Verification. This is a local evidence reconciliation, with no bulk production backfill or new Signzy request. Ages are calculated at verification time; this is not a new recurring age-refresh scheduler.

## Validation and live probe

5 November: read-only checks with the configured Railway test credentials returned HTTP 200 for Orders and Payment Links; the account had no saved Payment Link. An isolated local SQLite smoke test then created one real Razorpay sandbox link using the new adapter, opened its hosted page (HTTP 200), fetched its unpaid state and confirmed the gate remained locked. The unused link was cancelled. No production application database writes, submitted payment, SMS or email occurred. A successful user-completed provider checkout still needs device acceptance testing after deployment.

Tests cover captured-payment gating, account separation, repeated-click reuse, uncertain creation, foreign reference rejection, live-mode blocking, encrypted canonical identity, identity-owned age, owner privacy, existing billing/name masking and signup UI. The app browser test simulates a successful provider confirmation; it is not evidence of a real paid transaction. No deployment or native build has been started.

Provider contracts: https://razorpay.com/docs/api/payments/payment-links/create-standard and https://razorpay.com/docs/api/payments/payment-links/fetch-id-standard
