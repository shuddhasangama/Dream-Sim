# Table reservations: agreed phases 1 and 3

## What is implemented

1. **Booking workflow and architecture:** server-owned country → city → provider configuration;
   currency, timezone, public neighbourhood centres, per-person budget ranges in minor units,
   and a versioned, immutable date-scoped handoff for the later booking service.
3. **Couple and location coordination:** existing calendar plus neighbourhood selections;
   overlap on times, neighbourhoods, cuisine and budget; clear waiting/conflict messages;
   frozen preferences when a time is confirmed. Works for any eligible pair, without test IDs.

Phases 4–6 are not implemented here. No restaurant search, provider API calls, reservations,
deposits, or booking cancellations are performed. Existing payment foundation is unchanged.
The venue reads **Restaurant booking pending**, not a fictitious confirmed restaurant.

## Flow

Active verified Dating pair → each saves cuisine/budget/diet, neighbourhoods and availability
→ server finds shared choices → either confirms a shared time → atomic DatePlan + BookingSnapshot
→ both can review the saved preferences → later Phase 4 searches restaurants.

The existing signing process still applies. Choosing a time does not itself mean both have signed.
No shared neighbourhood/cuisine/budget/time: confirmation is blocked, with the reason shown.
Neither person can choose on behalf of the other. Only shared neighbourhoods are disclosed,
not the partner's full list. We do not collect GPS or home addresses.
New date cycles require neighbourhood choices again. Earlier snapshots are retained.

## Configuration

Default: `DHASHU_BOOKING_COORDINATION_ENABLED=0` (old app builds keep working).

Set `DHASHU_BOOKING_COORDINATION_ENABLED=1` only after the updated app is installed for testers.
This enables the feature for **all** eligible pairs in that environment. Unsupported cities
receive an explicit unavailable message and cannot confirm a new date through this flow.
Existing date plans remain usable without retroactively requiring neighbourhoods.

`booking_markets.json` initially supports Bengaluru/Bangalore, with six approximate public
neighbourhood centres. Review these centres before connecting a real venue search.
To extend, add markets with a unique ID, country code, city/aliases, currency, IANA timezone,
3–15 neighbourhoods, ordered budget bands/ranges and ordered provider routes.
`DHASHU_BOOKING_MARKETS_FILE` optionally points to an absolute JSON configuration path.
There is no automatic fallback to another city or country. Ambiguous aliases fail closed.
City availability in signup/profile choices must also be expanded for a new launch market.
Diet/cuisine choices continue using the existing app catalogue.

Provider statuses are configuration only (`not_connected`, `sandbox`, `live`); changing a
status does not install an adapter or enable network calls. Both initial routes are not connected.

## Interfaces and persistence

- `GET /api/v1/lock-ins/<id>/calendar`: additive `booking` object (null when disabled).
- `PUT /api/v1/lock-ins/<id>/neighbourhoods`: `{scope, revision, neighbourhoods: [id, ...]}`.
  Requires authenticated pair ownership. Rejects unknown places, stale cycle/revision and frozen dates.
- Existing date-confirm endpoint now validates shared preferences when enabled.
- Existing date-plan response includes an additive, readable `booking` summary.
- Browser `/calendar` and `/plan` use the same service as the mobile app.
- `BookingPreference`: pair/week/cycle/actor scoped; optimistic revision.
- `BookingSnapshot`: immutable per date; written in the same transaction as DatePlan.
  Date/pair deletion cascades to these records, preserving existing reset behaviour.

Phase-4 handoff includes date/pair reference, market/currency/timezone, shared centres,
search radius steps `[1,2,3]` km, cuisine, dietary needs, budget range, two guests, provider routes
and selected simulation day/meal. **It explicitly requires a real date/time before provider use.**
The budget is not a charge or a restaurant quote. An open-ended band has `max: null` and needs
an explicit spending limit before any paid reservation. No credentials belong in this JSON.

## Deployment

1. Commit the changes listed in this feature's Git diff, including new modules, JSON, tests
   and this document. Do not add unrelated node_modules, media or local output folders.
2. Push to the branch Railway deploys. Keep the feature flag `0` initially.
3. The existing database initialization creates both additive tables. If your deployment does
   not initialize automatically, run once in the Railway service shell:

   ```sh
   python -c "import db; c=db.get_connection(); db.init_db(c); c.close(); print('Schema ready')"
   ```

4. Build/distribute the updated Android and iOS clients through your existing Codemagic workflow.
   A Railway-only deployment cannot add the neighbourhood UI to already installed native apps.
5. Set `DHASHU_BOOKING_COORDINATION_ENABLED=1` in the testing environment and redeploy/restart.
   No new Razorpay variables or provider credentials are needed.
6. To roll back behaviour, set the flag to `0`. Saved snapshots remain available on date plans.

## Acceptance test with any pair (including f06/m06)

Use a verified active Dating pair in Bengaluru, with no open date plan, at the calendar step.
An already signed/confirmed date remains frozen: use the next date cycle or an existing safe reset.
Existing payment/intro requirements still apply; this feature never grants payment entitlements.

1. First person saves preferences, Indiranagar and a Saturday dinner slot: waiting status.
2. Second chooses Jayanagar and the same slot: no neighbourhood overlap; no confirmation.
3. Second changes to Indiranagar, but uses different cuisine/budget: the appropriate conflict appears.
4. Both choose shared cuisine/budget and time: confirmation becomes available.
5. Confirm: date plan shows agreed areas and restaurant booking pending. Revisiting cannot edit.
6. Third user cannot access the pair. A stale calendar save returns a refresh message.
7. Finish the date through the existing journey and arrange another: new neighbourhood choices
   are required, and the earlier snapshot is unchanged.

Local checks:

```powershell
python -m unittest test_booking_coordination test_booking_markets test_planning_api test_date_cycle_api test_schema_postgres -q
cd mobile
npm test
npm run build
```

Validated locally: 60 backend tests plus 83 subtests, including real disposable PostgreSQL
concurrent saves/confirmations; 100 mobile tests; production Vite build; 390px calendar render
without horizontal overflow. PostgreSQL check command:

```powershell
python run_local_postgres_tests.py test_booking_postgres.py test_planning_postgres.py test_booking_coordination.py test_booking_markets.py test_planning_api.py test_date_cycle_api.py test_schema_postgres.py
```

Live provider behaviour and the deployed Railway/native builds still need environment testing.
