# Phase 4 — restaurant booking simulator

For the latest combined release and platform connector design, see
[restaurant-platform-connectors.md](restaurant-platform-connectors.md). It supersedes the
direct-venue draft; the simulator now searches through the configurable provider registry.

Built on the agreed six-phase plan. Phase 1 (market routing), Phase 2 (payment foundation)
and Phase 3 (pair coordination) retain their names. This implements Phase 4 as a simulation;
Phase 5 connects an actual reservation provider, and Phase 6 is the live end-to-end pilot.

## User flow

Each person chooses **one or two neighbourhoods**, applying to all their availability slots.
The existing calendar finds shared areas, time, cuisine and budget. After confirming the time:

Date plan → Find options → up to three demo restaurants → each partner approves the same quote
→ both sign the existing date playbook → one partner simulates the table deposit
→ simulated reservation confirmation → cancellation/refund if required.

Search uses stored public neighbourhood coordinates, expanding 1 → 2 → 3 km only as needed.
Results must meet the currency, shared cuisine, both dietary needs, per-person budget and
availability constraints. Duplicates are removed and results are ordered by distance, cost, ID.
Both shared areas are searched; no unapproved midpoint or wider radius is substituted.

Quotes expire in 15 minutes. Each search generates new quote identifiers. Different restaurant
choices do not count as mutual approval. Price changes, expiry and unavailability clear approvals.
Payment rechecks the quote first. An uncertain reservation cannot be paid again or cancelled
until its provider status has been checked. Duplicate/stale actions return a refresh conflict.

Deposit, food credit and booking fee are shown separately. Existing DhaShu stage fees remain
separate. The simulator uses fully refundable terms and one payer for the whole table deposit.
No bank account, Razorpay transaction or entitlement is created. Real deposits and split-payer
collection are not enabled. This is intentionally a simulator, not a live reservation product.

## Deployment

Commit/push the Phase 4 files; deploy Railway; initialize the additive tables in Railway:

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2
git add app.py booking_coordination.py booking_markets.py db.py planning_api.py schema.sql schema_postgres.sql restaurant_provider.py restaurant_service.py restaurant_web.py templates/calendar.html templates/plan.html templates/restaurant.html mobile/src/screens/calendar.js mobile/src/screens/plan.js mobile/src/screens/restaurant.js mobile/tests/restaurant.test.js test_restaurant_service.py test_restaurant_postgres.py docs/booking-phase-4.md
git diff --cached --stat
git commit -m "Add Phase 4 restaurant reservation simulator"
git push origin master
```

```sh
/app/.venv/bin/python -c "import db; c=db.get_connection(); db.init_db(c); c.close(); print('Restaurant schema ready')"
```

Variables:

```text
DHASHU_BOOKING_COORDINATION_ENABLED=1
DHASHU_RESTAURANT_MODE=simulation
DHASHU_RESTAURANT_SCENARIO=success
```

Mode defaults to disabled. Only `simulation` enables it; live mode is deliberately unsupported.
These flags affect every eligible user in that environment. Run failure scenarios in a testing
environment, not while other testers are completing their successful flows.

Updated mobile screens require a new Codemagic Android/iOS build. Browser testing is also
available: sign in and follow **Restaurant simulation** from `/plan`. Browser forms use CSRF.
The browser page can be used before distributing new native builds.

## Test matrix

Use f06/m06 or any verified active Dating pair with a Phase 3 snapshot and shared preferences.
For the deposit step, both need to complete the existing date agreement. Refresh/reopen the
date plan, or use **Refresh restaurant status**, to see the other person's most recent action.

| Scenario variable | Expected result |
|---|---|
| `success` | Three options; mutual approval; simulated deposit; SIM reference; cancellation and refund |
| `empty` | No results; no automatic relaxation of preferences |
| `unavailable` | Deposit step stops before payment; search again |
| `price_changed` | Both approvals cleared; new search and approval required |
| `payment_failed` | No reservation submitted; retry after restoring success |
| `timeout` | Uncertain state; only status reconciliation can establish confirmation |
| `refund_failed` | Cancellation recorded, refund failed; restore success and retry refund |

Also test selecting three neighbourhoods (rejected), different restaurant approvals (no payment),
expired quotes, another user's date ID, repeated clicks and cancellations from the other partner.
Keep `success` as the normal setting. A simulator timeout reconciles to confirmed deterministically.

## Architecture and interfaces

- `restaurant_provider.py`: typed provider boundary: search, recheck, reserve, status, cancel;
  deterministic simulation adapter, geodesic radius calculation. No network calls.
- `restaurant_service.py`: actor authorization, quote versions, approval and reservation state
  machine, payment/refund simulation, optimistic revisions and pair/date transaction locking.
- `RestaurantBooking`: current date-scoped aggregate. `RestaurantEvent`: append-only action
  snapshots for diagnostics/history. Both cascade when the parent test date is deleted.
- `GET /api/v1/date-plans/<id>/restaurant`: owned status, options and approvals.
- `POST /api/v1/date-plans/<id>/restaurant/actions`:
  `{action, revision, quote_id?, max_per_person_minor?}`. Actions: search, approve, pay, reconcile, cancel, retry_refund.
- Date-plan JSON includes an additive restaurant field. Browser and native screens share the
  same service. This service module is currently hosted inside the existing Flask deployment,
  not a separately deployed network microservice.

The simulation adapter is explicitly selected instead of pretending the configured Dineout or
direct-venue route is connected. Provider attempt references are stored on the aggregate and
retained in event history. Existing date agreements/venues are not silently rewritten after signing.

## Remaining boundaries before live use (Phase 5/6)

- Provider authorization, real catalogue/check availability, hold/confirmation capabilities,
  cancellation rules and supported payment ordering must be established with the provider.
- Real network calls require a durable job/outbox and provider idempotency/reconciliation;
  they must not be dropped into the simulator's database transaction.
- Connect the real deposit/payment/refund ledger, receipts and verified webhooks. Never trust
  a client success flag. Confirm real currency minor-unit conventions per launch market.
- The app's date timestamps still originate in its simulation calendar. They are displayed
  with market timezone here, but must be validated as real future dates before live bookings.
- Open-ended budget bands request an explicit per-person ceiling before search; both partners
  must approve the resulting quote. A new preference cycle is needed to revise other frozen
  preferences; this simulator does not silently rewrite an agreed date.
- Cancelling a restaurant selection does not cancel the app's date. Date cancellation and
  provider cancellation need coordinated live orchestration; for testing cancel the restaurant
  first. Status/cancellation API remains available to the original pair after the date closes.
- No Home/Guru claim of a real restaurant confirmation is added in this phase.

## Local checks

```powershell
python -m unittest test_restaurant_service test_booking_coordination test_schema_postgres -q
python run_local_postgres_tests.py test_restaurant_postgres.py test_booking_postgres.py test_planning_postgres.py
cd mobile
npm test
npm run build
```

Validation on this build: 58 backend tests and 85 subtests passed, including isolated
PostgreSQL concurrent payment/cancellation tests; 102 mobile tests passed; Vite production
build passed; restaurant panel inspected at 390px with no horizontal overflow.
No Railway data, live restaurant provider or real payment was used in these tests.
