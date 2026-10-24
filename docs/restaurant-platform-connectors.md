# One restaurant interface, interchangeable platform connectors

This supersedes the unapproved direct-venue draft. That draft and its manual-confirmation
CLI have been removed. Phase 4 simulation remains functional. Phase 5's common platform
interface, routing and mapping are built; live platform adapters are still awaiting approved
documentation/access. Phase 6 automated checks can run now; a real pilot cannot yet be signed off.

## Architecture

Pair/date preferences → canonical search request → eligible platform registry
→ each adapter maps only supported inputs → canonical validated quotes
→ compare availability / cost / distance → both users approve one quote
→ recheck and pin that platform → reserve → status / cancellation on the same platform.

The implementation is modular Python behind the existing authenticated API, in the existing
Flask deployment. It is not a separately deployed network service. Future connector network
IO must use a durable job/outbox outside the current simulator's database transaction.

## Code boundaries

| Module | Responsibility |
|---|---|
| restaurant_models.py | Canonical request, strict quote validation, safe field allowlists |
| restaurant_mapping.py | Explicit adapter-owned input/output field mapping; optional fields omitted |
| restaurant_registry.py | Market/capability eligibility, factories, partial outages, provider pinning and ranking |
| restaurant_providers.json | Provider selection, market coverage, priorities and comparison policy |
| restaurant_provider.py | Provider interface and deterministic simulation adapter |
| restaurant_service.py | Pair authorization, shared approvals, quote versions, reservation state and audit trail |
| restaurant_readiness.py | Read-only report of configured adapters and remaining live-release requirements |

## Provider-neutral information

- Country, city/market, currency/exponent, timezone, date/time, party size.
- One or two shared neighbourhood centres, 1–3km radius, cuisine, both dietary needs,
  explicit per-person budget range.
- Provider venue identifier, optional verified cross-platform venue identifier, available slot,
  provider name, restaurant coordinates, cuisine/diets and cancellation terms.
- Estimated food per person, deposit, food-redeemable credit, booking fee, estimated total
  for two and upfront amount, all in integer currency minor units.
- App quote identifier/version/expiry, approvals, pinned provider/adapter, stable attempt
  identifier, confirmation reference, cancellation and refund state.

User IDs, pair identifiers, verification documents and credentials are not included in search
requests sent to adapters. Booking contact details, if required, must be explicitly introduced
with the actual provider's requirements and appropriate user consent at booking time.

Optional provider features include deposits, food credits and refunds. Search/recheck/reserve/
status/cancel are required for this app's supported flow. Holds/webhooks and additional payment
models must be declared and implemented by their adapter; a config switch cannot create support.

## Cost and availability rules

Only valid, available, correctly denominated options matching both users' requirements enter
the shortlist. Different currencies are never converted or compared silently.

Estimated total for two = max(2 × estimated food per person, food credit) + booking fee + deposit − food credit.
Upfront = deposit + booking fee. A redeemable deposit is not counted twice, and unused prepaid
food credit is not assumed to be refunded. These are estimates,
not guaranteed final restaurant bills; real connectors must establish inclusive taxes/charges.

Policies: `lowest_total` (default), `lowest_upfront`, `nearest`. Ties use configured provider
priority then stable IDs. Search expands from 1 to 2 to 3 km until three distinct options are
available. Cost comparison is within that radius, not a promise of the cheapest restaurant in
the entire city. Venue deduplication across platforms requires a verified canonical venue ID;
similar names alone are insufficient. Different branches must have different canonical IDs.

A provider outage does not hide results from other providers. Invalid responses are excluded;
only safe failure codes are returned. A selected provider is never silently replaced after
approval/payment. Disabling it prevents new requests while allowing status/cancellation through
the same installed adapter. Removing/changing the adapter requires operational migration of
outstanding bookings, not a silent fallback.

## Configuration and extension

Set `DHASHU_RESTAURANT_PROVIDERS_FILE` to a server-owned JSON path to override the included
configuration. Never put tokens in it. The included entries for Swiggy Dineout, District and
EazyDiner are **disabled placeholders with no adapter**, not claims of supported APIs.
The earlier `booking_markets.json` routes describe intended country/city coverage; executable
adapter selection is centrally controlled by `restaurant_providers.json`.

To add a new platform:

1. Obtain approved docs/access: auth, endpoints, mandatory fields, identifiers, rate limits,
   quote lifetime, idempotency, status semantics, cancellation and payment/refund sequencing.
2. Implement the Provider interface in a new adapter module. Use FieldMapper where useful;
   perform documented unit/time/status conversions explicitly. Map responses into the canonical
   model and never pass through unrestricted provider payloads.
3. Register the reviewed factory, actual capabilities and supported markets. A JSON entry alone
   cannot enable an unimplemented adapter. No arbitrary Python imports from configuration.
4. Run mapping/validation tests with recorded, redacted fixtures plus the provider sandbox.
5. Add durable remote orchestration/payment reconciliation before allowing non-simulation IO.
   Current routing deliberately refuses non-simulation adapters. It must not execute HTTP under
   the planning database lock. Connect real deposits to verified payment events, not UI callbacks.
6. Run live-date, dual-approval, unknown-outcome, duplicate-action, cancellation and refund
   acceptance checks, then a small allowlisted pilot. Broader activation follows pilot sign-off.

## Combined code promotion (Phase 4 plus connector framework)

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2
git add app.py booking_coordination.py booking_markets.py booking_markets.json db.py planning_api.py schema.sql schema_postgres.sql restaurant_provider.py restaurant_models.py restaurant_mapping.py restaurant_registry.py restaurant_providers.json restaurant_readiness.py restaurant_service.py restaurant_web.py templates/calendar.html templates/plan.html templates/restaurant.html mobile/src/screens/calendar.js mobile/src/screens/plan.js mobile/src/screens/restaurant.js mobile/tests/restaurant.test.js test_restaurant_service.py test_restaurant_registry.py test_restaurant_postgres.py docs/booking-phase-4.md docs/restaurant-platform-connectors.md
git diff --cached --stat
git commit -m "Add modular restaurant platform routing and booking simulator"
git push origin master
```

Railway shell, after deployment:

```sh
/app/.venv/bin/python -c "import db; c=db.get_connection(); db.init_db(c); c.close(); print('Restaurant schema ready')"
/app/.venv/bin/python restaurant_readiness.py
```

Keep `DHASHU_RESTAURANT_MODE=simulation`, `DHASHU_RESTAURANT_SCENARIO=success`, and
`DHASHU_BOOKING_COORDINATION_ENABLED=1` for testing. Native UI changes need Codemagic builds.
No direct-pilot variables or venue files are used. Do not enable live charging based on this
release: real connectors and end-to-end live acceptance remain pending.

Checks:

```powershell
python -m unittest test_restaurant_registry test_restaurant_service -q
python run_local_postgres_tests.py test_restaurant_postgres.py test_restaurant_service.py test_restaurant_registry.py test_planning_api.py test_schema_postgres.py
cd mobile
npm test
npm run build
```

Validation: the combined backend run passed 58 tests and 89 subtests, including isolated
PostgreSQL race checks. All 102 mobile tests and the production Vite build passed. A separate
invalid-search regression check also covers the actionable 409 response for legacy bad dates.
No live vendor, real reservation or payment was used in these tests.
