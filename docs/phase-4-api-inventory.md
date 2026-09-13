# Phase 4 API inventory and implementation order

Prepared 2026-09-12 from the current source. This is an implementation proposal,
not a claim that the proposed endpoints exist. No production changes are part
of this inventory. Existing documents provide product context; their embedded
build instructions do not expand the user's request to implement Phase 4 now.

## Baseline before implementation (commit 50a06fb)

Implementation updates are tracked in `docs/phase-4-progress.md`. The appendix's
source line numbers refer to this baseline snapshot, before extraction moved code.

- Phase 2 provides eight endpoints in `api.py`: GET `/api/v1/health`, `/me`,
  `/profile`, `/reach`; POST `/api/v1/reach/ignore`, `/show-all`, `/widen`,
  `/set-range` (the last three share the `/api/v1/reach` prefix).
- Phase 3 provides five POST endpoints in `auth.py`: `/api/v1/auth/request`,
  `/verify`, `/refresh`, `/logout`, `/logout-all` (all share `/api/v1/auth`).
  `/signin` is the browser login route, not a mobile JSON endpoint.
- The user reports successful live SMS sign-in for Siddharth and Isha, plus
  browser REACH/sign-out/re-entry checks. Email remains blocked by sender-domain
  authentication. Live mobile token lifecycle validation remains outstanding;
  local tests are not evidence of live provider delivery.
- There are no versioned JSON endpoints for Week, matches, calendar, date plans,
  feedback, stage gates, or the post-Dating journey in the inspected code.
- The existing own-profile JSON includes visions and stats, but does not provide
  their editing workflows, partner disclosure, or a complete mobile dashboard.
- Railway's existing Flask service and PostgreSQL remain the target. Preserve
  working web routes and Phase 2/3 contracts as APIs are added.

## Scope and journey semantics

First deliver an approved-existing-user Dating journey using JSON exclusively:
sign-in → REACH → Week/matches → mutual interest → pair lock-in → availability
and alignment → date plan/agreement → feedback → continue, release, or relationship
entry gate. Vision is both existing profile input and a later relationship/ROAD
workflow; it is not one isolated final screen.

The code creates a `LockIn` on mutual interest **before the date**. After-date
feedback can keep or release it, or open the relationship gate. Do not invent a
second independent "lock-in" action that bypasses this rule. A Couple is created
through the relationship-entry process, not merely by submitting two feedback
decisions.

Then expose the remaining post-Dating functionality for web parity. Secure
new-user registration is an additional workstream: `/signup` and `/onboarding/*`
are simulation-oriented and blocked in secure mode. Their presence is not a
working mobile enrollment API.

## Proposed API surface

All proposed paths below have the `/api/v1` prefix. Braces denote validated
resource identifiers; existing Flask paths retain their angle-bracket notation.
The route-by-route appendix records the original handler and input field clues.
Payload names below are proposals, not frozen contracts.

| Area | Existing web routes | Missing JSON endpoints proposed | Key response / mutation rules |
|---|---|---|---|
| Navigation and progress | `/dashboard`, `/guru`, `/guru/everything` | GET `/dashboard`, `/journey/status`, `/guidance` | Current stage, current pair/date, allowed actions, reasons actions are blocked, next API action; no reliance on HTML links |
| REACH | `/reach` and four actions | Already available | Preserve counts/filters and verify locked-in access rules; no duplicate implementation |
| Week and match review | GET `/week`; POST `/week/act` | GET `/week`, `/matches/{match_id}`; POST `/matches/{match_id}/actions` | Reveal schedule, actual slot count, interest/pass with optional pass reason, window eligibility, disclosure-safe candidate summary |
| Pair lock-in | Internal `_create_lockin`, `_my_active_lockin`; state appears in Week/calendar | GET `/lock-ins/current` | Derived from mutual interest; pair-owned state and allowed next steps; no arbitrary create/pick-partner endpoint |
| Availability | `/calendar`, `/calendar/submit`, `/calendar/confirm`, `/calendar/no-overlap` | GET `/lock-ins/{id}/calendar`; PUT `/lock-ins/{id}/availability`; POST `/lock-ins/{id}/calendar/confirm`, `/calendar/no-overlap` | Own slot list, safe overlap result, alignment/payment requirements; structured `{day, meal_slot}` entries instead of `day|meal` form strings |
| Date alignment | GET/POST `/align` | GET and PUT `/lock-ins/{id}/alignment` | Budget, diet, cuisine and pair readiness; respect disclosure rules |
| Date plan | `/plan`, `/plan/selections`, `/plan/sign`, `/plan/cancel` | GET `/date-plans/{id}`; PUT `/date-plans/{id}/selections`; POST `/date-plans/{id}/sign`, `/date-plans/{id}/cancel` | Actor's selections and signatures, plan status, pair readiness; unify signing with ceremony logic rather than duplicating it |
| Agreement ceremonies | `/ceremony/<kind>`, `/ceremony/<kind>/step` | GET `/ceremonies/{kind}` with validated scope; POST `/ceremonies/{kind}/steps` | Server determines next legal step; signed-name/acknowledgement input; explicit simulation status for face checks |
| Payment prerequisites | `/pay/<purpose>`, `/pay/<purpose>/confirm` | GET `/payments/{purpose}/status`; beta-only POST `/payments/{purpose}/simulate` if simulation remains approved | Scope derived from actor/pair; never describe a simulated payment as a real charge; real checkout/webhook design is separate |
| Date feedback | `/debrief`, `/plan/feedback/flags`, `/plan/feedback`, `/debrief/no-show` | GET `/date-plans/{id}/feedback`; PUT `/date-plans/{id}/feedback/flags`; POST `/date-plans/{id}/feedback/decision`, `/date-plans/{id}/no-show` | Mandatory flags before decision; continue/relationship/pass resolution; protect private partner feedback and make repeat submissions safe |
| After-date hub | `/after-date`, `/expectations`, `/boundaries`, `/vibes` | GET `/after-date`, `/expectations`, `/boundaries`, `/vibes` | Combine unlocked sections for clients; provide question/options metadata and reciprocal-disclosure state |
| Contact sharing | `/escalations`, `/escalations/contact/request`, `/escalations/contact/respond` | GET `/escalations`; POST `/contact-requests`, `/contact-requests/{id}/respond` | Explicit mutual permission and ceremony prerequisites; release only accepted contact channels |
| Home invitations | `/escalations/invite/*` | POST `/invitations`; POST `/invitations/{id}/see-flag`, `/respond`, `/guidance`, `/acknowledge`, `/trusted-contact`, `/revoke` | Preserve expectation disclosure and ordered acknowledgements; consent is not inferred from an invitation |
| Relationship gate | `/gate` and nine POST actions | GET `/stage-gate`; POST `/stage-gate/ask`, `/respond`, `/raise`, `/answer`, `/confirm`, `/decline`, `/exclusivity-ack`, `/consent`, `/enter-relationship` | Conversation, both-party confirmations and prerequisites; final transition atomic with Couple/LockIn state |
| Own stats | `/stats`, `/stats/save`, `/stats/reverify` | GET and PATCH `/profile/stats`; POST `/profile/stats/reverify` | Preserve edit restrictions while a match/date is active, field validation and verification consequences |
| Own Vision | `/vision`, `/vision/add`, `/vision/declare-change` | GET `/vision`; POST `/vision/entries`, `/vision/changes` | Preserve stance/evidence and declaration rules; do not expose raw partner entries |
| Chemistry | `/chemistry`, `/chemistry/activities`, `/chemistry/set` | GET `/chemistry`; PUT `/chemistry/activities`, `/chemistry/answers` | Typed activity/answer input, reciprocal unlock and disclosure restrictions |
| Next-level conversation | `/next-level`, `/next-level/open`, `/next-level/answer` | GET `/next-level`; POST `/next-level/open`, `/next-level/answers` | Both-party participation and server-side unlock state |
| Relationship tools | `/relationship` and six POST actions | GET `/relationship`; POST `/relationship/playbook/items`, `/romance/ideas`, `/differences`, `/differences/{id}/consent`, `/differences/{id}/resolve`, `/expenses/check` | Derive current Couple from session; scoped ownership and preserved consent rules |
| ROAD | `/road`, `/road/routine*`, `/road/obligations*`, `/road/availability*`, `/road/vision*` | GET `/road`; GET/POST/DELETE routine and obligation resources; GET availability, POST/DELETE free slots, POST share; GET/PUT `/road/vision` | Validate intervals, ownership and sharing; `/road` redirect becomes a state/next-step response |
| Later stages | `/journey`, `/married`, `/journey/advance` | GET `/journey`, `/married`; POST `/journey/advance` | Keep existing state-machine gates; reject arbitrary client-selected stages |
| New-user onboarding | `/signup`, `/onboarding/vision`, `/stats`, `/chemistry`, `/finish`, `/restart` under onboarding | Proposed `/enrollment` and `/onboarding/*` JSON workflow; exact contract deferred to identity review | Verify contact ownership before binding an identity; resumable draft, required fields, account collision handling, no simulated login bypass |
| Background verification | `/verify`, `/verify/start`, `/verify/simulate` | GET `/verification`; POST `/verification/start`; no public simulate endpoint | BGV is distinct from email/SMS ownership. Real provider integration is not established by existing simulated BGV |

## Implementation order: seven batches

| Order | Deliverable | Depends on | Exit evidence |
|---|---|---|---|
| 1 | Shared JSON contracts, serializers and journey-status/dashboard | Phase 2/3 foundation | OpenAPI draft, ownership/disclosure rules, explicit errors and allowed actions; anonymous/foreign-user requests rejected |
| 2 | Week, candidate review, interest/pass and current lock-in | 1; explicit server-clock policy | Two actors reach exactly one mutual lock-in; other candidates cleared; closed windows and concurrent submissions tested |
| 3 | Alignment, calendar, plan, payment prerequisites and agreement ceremony | 2; explicit beta simulation policy | Pair selects valid availability, produces one plan and completes each actor's required acknowledgements without HTML |
| 4 | Feedback, cancellation, no-show and repeated-date cycles | 3 | Both actors' outcomes resolve once; continue returns to calendar; pass/no-show releases correctly; retry cannot double-increment dates |
| 5 | After-date, disclosure, invitations, relationship gate, Vision/stats/chemistry | 4 | Private information stays hidden until allowed; gated progression produces the correct Couple state |
| 6 | Relationship tools, ROAD, later stages and full guidance parity | 5 | Each remaining route family has JSON coverage or an explicit documented exclusion |
| 7 | Secure enrollment/BGV boundary and full API-only regression suite | Identity/enrollment design; 1–6 | New-user beta capability is either implemented and tested or explicitly excluded; published endpoint inventory, example requests and two-user E2E results |

Batch 7's enrollment design should begin during batch 1, not at the end. For an
invited-existing-user beta it can be deferred, but that is a scope decision, not
completion of new-user onboarding. Existing SMS-authenticated accounts allow
local Phase 4 work while email deliverability is pending; Phase 3 remains open.

## Engineering findings that affect the plan

1. **Do not just prefix HTML routes.** Most mutations read `request.form` and
   return redirects; reads build template contexts. Extract transport-independent
   services and allowlisted serializers. Both HTML and JSON adapters should call
   those services. Do not call decorated page handlers and wrap their redirect
   bodies in a successful JSON envelope.
2. **Clock and read-side mutations need an explicit design.** `get_clock()` reads
   `data/sim_state.json` and defaults to simulated Monday noon. `/week` can lazily
   generate matches and resolve stale outcomes. Define a durable server-owned
   beta clock/timezone and transition runner before claiming real weekly cadence.
   Keep demo clock advancement out of public APIs. Prefer explicit internal
   reconciliation before read snapshots; do not let repeated client GETs duplicate
   transitions. A real scheduler is additional implementation, not present proof.
3. **Use actual disclosure rules, not complete template dictionaries.** Reuse
   `disclosure.py`, `named_for`, reciprocal unlock rules and consent gates.
   Candidate identity, private feedback, invitation/trusted-contact details and
   account contacts must not leak through nested JSON. The generated display name
   is not proof of real identity.
4. **Concurrency and retry safety are required for pair actions.** Review match
   interest → lock-in, availability replacement, plan confirmation, signatures,
   date resolution and relationship entry as transactions. Use unique constraints
   and/or row locks, a stale-version policy and idempotency keys for retryable POSTs.
   `/plan/feedback` increments date counts and may delete cycle rows: repeated
   submissions and two simultaneous partner decisions need dedicated tests.
5. **Validate more than form parity.** For example, calendar confirmation visibly
   checks valid slot labels and alignment, but the API must also enforce actual
   mutual availability and current plan/state at the transaction boundary. Return
   a conflict for stale/illegal actions rather than silently redirecting.
6. **Simulation dependencies are on the critical path.** Payment confirmation
   writes a simulated successful payment. Ceremony face checks call a simulation
   helper. Background verification also includes a simulator. Identify these as
   beta simulations and restrict who can invoke them; do not imply real payments,
   biometric identity checks or real background checks. Provider replacement is
   separate scope requiring a concrete design.
7. **API identity and browser transport differ.** Inherit bearer session handling
   and cookie same-origin protection. Actor IDs come from the authenticated session;
   resource IDs require membership checks. Preserve 401/403/404 behaviour and
   propose 409 for stale state, 400 for invalid fields, 415 for wrong content type,
   429 for throttling. Extend error mapping deliberately. Keep `no-store`.
8. **Mobile clients need discoverable choices.** Return valid slots, question keys,
   option enums, requirements and blocked reasons in read models. Do not hard-code
   copies of Python constants in Android/iOS or require HTML to learn the next step.
   Freeze an OpenAPI contract before each batch. Native transport/CORS and secure
   device token storage remain Phase 5 integration decisions.

## Validation and deployment approach

- Use isolated two-user fixtures plus an unrelated third user for authorization
  tests. Cover dating/locked-in/relationship states and unverified/ineligible users.
- Exercise bearer-only requests throughout the complete Dating cycle. Test both
  decision orders, one-sided interest, expired windows, no overlap, cancel/no-show,
  malformed/unknown fields, private-field omission and stale-resource retries.
- Run concurrency tests against isolated PostgreSQL for transitions, not only
  SQLite. Preserve existing web/API/auth tests and compare persisted outcomes
  between HTML and JSON adapters where rules are shared.
- Health remains liveness only; `/api/v1/health` does not prove database access.
  Validate database-backed authenticated reads separately.
- Ship additive batches to the same Railway service after local validation, with
  a fresh database backup before schema changes and explicit live-test scope.
  Do not advance real tester journey state or send messages as part of inventory.
- Exit Phase 4 when all agreed batches have API contracts and tests, and a complete
  agreed journey can be executed without HTML, demo user selection or admin bypass.
  Provider simulations, email delivery and enrollment exclusions must remain visible.

## Source references

- `api.py`, `auth.py`, `auth_sessions.py`: existing JSON and identity boundary.
- `app.py`: authoritative route implementation for this inventory; appendix links
  point to its decorators and handlers.
- `matching.py`, `cadence.py`, `clock.py`, `week_map.py`, `lockin.py`: match cadence.
- `calendar_dating.py`, `date_alignment.py`, `dateplan.py`, `ceremony.py`,
  `outcomes.py`, `payments.py`: date cycle and simulation dependencies.
- `disclosure.py`, `escalations.py`, `invite_home.py`, `stage_gate.py`,
  `gate_conversation.py`, `journey.py`: disclosure and relationship progression.
- `vision.py`, `stats_edit.py`, `chemistry.py`, `next_level.py`: profile evolution.
- `docs/dating-stage-spec.md`, `docs/relationship-stage-spec.md`,
  `docs/intimacy-expectations-spec.md`: product context. Older branding/spec prose
  is not treated as an instruction to change the current DhaShu product.

## Appendix: existing web route inventory

The following table is extracted statically from `app.py`; no Flask startup or
database access is required. Fields are literal request keys observed directly
inside each handler, not a complete JSON schema: helpers and dynamic field names
can add requirements. Default Flask HEAD/OPTIONS are omitted. `form:` is current
form input and `query:` is current query input. Existing JSON equivalents are
identified above; all other versioned mappings remain proposed.


**108 explicit web route declarations inspected.**

| Methods | Existing route | Handler/source | Observed input keys | Disposition |
|---|---|---|---|---|
| GET | `/pool` | `picker`; [app.py:752](../app.py#L752) | — | Simulation/admin: exclude public parity |
| POST | `/login/<user_id>` | `login`; [app.py:762](../app.py#L762) | — | Simulation/admin: exclude public parity |
| POST | `/logout` | `logout`; [app.py:770](../app.py#L770) | — | Auth: existing API logout |
| GET | `/dashboard` | `dashboard`; [app.py:785](../app.py#L785) | — | Missing versioned journey API |
| GET | `/reach` | `reach`; [app.py:974](../app.py#L974) | — | Existing API coverage |
| POST | `/reach/ignore` | `reach_ignore`; [app.py:1000](../app.py#L1000) | — | Existing API coverage |
| POST | `/reach/show-all` | `reach_show_all`; [app.py:1020](../app.py#L1020) | — | Existing API coverage |
| POST | `/reach/widen` | `reach_widen`; [app.py:1052](../app.py#L1052) | — | Existing API coverage |
| POST | `/reach/set-range` | `reach_set_range`; [app.py:1069](../app.py#L1069) | — | Existing API coverage |
| GET | `/week` | `week`; [app.py:1350](../app.py#L1350) | — | Missing versioned journey API |
| POST | `/week/act` | `week_act`; [app.py:1435](../app.py#L1435) | form:action, form:match_id, form:pass_reason | Missing versioned journey API |
| GET | `/calendar` | `calendar_view`; [app.py:1483](../app.py#L1483) | — | Missing versioned journey API |
| POST | `/calendar/submit` | `calendar_submit`; [app.py:1513](../app.py#L1513) | form:slot | Missing versioned journey API |
| POST | `/calendar/confirm` | `calendar_confirm`; [app.py:1544](../app.py#L1544) | form:day, form:meal_slot | Missing versioned journey API |
| POST | `/calendar/no-overlap` | `calendar_no_overlap`; [app.py:1598](../app.py#L1598) | form:choice | Missing versioned journey API |
| GET | `/plan` | `plan_view`; [app.py:1624](../app.py#L1624) | query:edit | Missing versioned journey API |
| POST | `/plan/selections` | `plan_selections`; [app.py:1679](../app.py#L1679) | form:dietary, form:dress | Missing versioned journey API |
| POST | `/plan/sign` | `plan_sign`; [app.py:1705](../app.py#L1705) | — | Missing versioned journey API |
| POST | `/plan/feedback/flags` | `plan_feedback_flags`; [app.py:1753](../app.py#L1753) | form:green_flags, form:red_flags | Missing versioned journey API |
| POST | `/plan/feedback` | `plan_feedback`; [app.py:1799](../app.py#L1799) | form:decision, form:reason | Missing versioned journey API |
| GET | `/escalations` | `escalations_view`; [app.py:1878](../app.py#L1878) | — | Missing versioned journey API |
| POST | `/escalations/contact/request` | `escalations_contact_request`; [app.py:1930](../app.py#L1930) | form:channel | Missing versioned journey API |
| POST | `/escalations/contact/respond` | `escalations_contact_respond`; [app.py:1950](../app.py#L1950) | form:request_id, form:response | Missing versioned journey API |
| POST | `/escalations/invite/propose` | `escalations_invite_propose`; [app.py:1974](../app.py#L1974) | form:expectation_flag, form:proposed_datetime | Missing versioned journey API |
| POST | `/escalations/invite/see-flag` | `escalations_invite_see_flag`; [app.py:2003](../app.py#L2003) | form:invite_id | Missing versioned journey API |
| POST | `/escalations/invite/respond` | `escalations_invite_respond`; [app.py:2014](../app.py#L2014) | form:invite_id, form:response | Missing versioned journey API |
| POST | `/escalations/invite/guidance` | `escalations_invite_guidance`; [app.py:2028](../app.py#L2028) | form:invite_id | Missing versioned journey API |
| POST | `/escalations/invite/acknowledge` | `escalations_invite_acknowledge`; [app.py:2044](../app.py#L2044) | form:invite_id | Missing versioned journey API |
| POST | `/escalations/invite/trusted-contact` | `escalations_invite_trusted_contact`; [app.py:2062](../app.py#L2062) | form:invite_id | Missing versioned journey API |
| POST | `/escalations/invite/revoke` | `escalations_invite_revoke`; [app.py:2075](../app.py#L2075) | form:invite_id | Missing versioned journey API |
| GET | `/gate` | `gate_view`; [app.py:2131](../app.py#L2131) | — | Missing versioned journey API |
| POST | `/gate/ask` | `gate_ask`; [app.py:2228](../app.py#L2228) | form:question_key | Missing versioned journey API |
| POST | `/gate/respond` | `gate_respond`; [app.py:2265](../app.py#L2265) | form:answer_text, form:question_key, form:readiness_scale | Missing versioned journey API |
| POST | `/gate/raise` | `gate_raise`; [app.py:2302](../app.py#L2302) | — | Missing versioned journey API |
| POST | `/gate/answer` | `gate_answer`; [app.py:2316](../app.py#L2316) | form:answer_text, form:question_key, form:readiness_scale | Missing versioned journey API |
| POST | `/gate/confirm` | `gate_confirm`; [app.py:2344](../app.py#L2344) | — | Missing versioned journey API |
| POST | `/gate/decline` | `gate_decline`; [app.py:2369](../app.py#L2369) | — | Missing versioned journey API |
| POST | `/gate/exclusivity-ack` | `gate_exclusivity_ack`; [app.py:2383](../app.py#L2383) | — | Missing versioned journey API |
| POST | `/gate/consent` | `gate_consent`; [app.py:2399](../app.py#L2399) | — | Missing versioned journey API |
| POST | `/gate/enter-relationship` | `gate_enter_relationship`; [app.py:2437](../app.py#L2437) | — | Missing versioned journey API |
| GET | `/stats` | `stats_view`; [app.py:2519](../app.py#L2519) | — | Missing versioned journey API |
| POST | `/stats/save` | `stats_save`; [app.py:2556](../app.py#L2556) | — | Missing versioned journey API |
| POST | `/stats/reverify` | `stats_reverify`; [app.py:2656](../app.py#L2656) | form:field | Missing versioned journey API |
| GET | `/vision` | `vision_view`; [app.py:2691](../app.py#L2691) | — | Missing versioned journey API |
| POST | `/vision/add` | `vision_add`; [app.py:2732](../app.py#L2732) | form:detail_text, form:element_key | Missing versioned journey API |
| POST | `/vision/declare-change` | `vision_declare_change`; [app.py:2747](../app.py#L2747) | form:element_key, form:from_value, form:to_value | Missing versioned journey API |
| GET | `/chemistry` | `chemistry_view`; [app.py:2770](../app.py#L2770) | — | Missing versioned journey API |
| POST | `/chemistry/activities` | `chemistry_set_activities`; [app.py:2811](../app.py#L2811) | — | Missing versioned journey API |
| GET | `/boundaries` | `boundaries_view`; [app.py:2838](../app.py#L2838) | — | Missing versioned journey API |
| GET | `/expectations` | `expectations_view`; [app.py:2856](../app.py#L2856) | — | Missing versioned journey API |
| GET | `/vibes` | `vibes_view`; [app.py:2899](../app.py#L2899) | — | Missing versioned journey API |
| POST | `/chemistry/set` | `chemistry_set`; [app.py:2917](../app.py#L2917) | form:back, form:key, form:value | Missing versioned journey API |
| GET | `/next-level` | `next_level_view`; [app.py:2945](../app.py#L2945) | — | Missing versioned journey API |
| POST | `/next-level/open` | `next_level_open`; [app.py:2977](../app.py#L2977) | form:opened_by | Missing versioned journey API |
| POST | `/next-level/answer` | `next_level_answer`; [app.py:2996](../app.py#L2996) | form:answer_text, form:question_key | Missing versioned journey API |
| GET | `/relationship` | `relationship_view`; [app.py:3018](../app.py#L3018) | — | Missing versioned journey API |
| POST | `/relationship/playbook/add-custom` | `relationship_playbook_add_custom`; [app.py:3056](../app.py#L3056) | form:idea | Missing versioned journey API |
| POST | `/relationship/romance/idea` | `relationship_romance_idea`; [app.py:3071](../app.py#L3071) | form:idea | Missing versioned journey API |
| POST | `/relationship/difference/raise` | `relationship_difference_raise`; [app.py:3085](../app.py#L3085) | form:text | Missing versioned journey API |
| POST | `/relationship/difference/consent` | `relationship_difference_consent`; [app.py:3099](../app.py#L3099) | form:difference_id | Missing versioned journey API |
| POST | `/relationship/difference/resolve` | `relationship_difference_resolve`; [app.py:3110](../app.py#L3110) | form:difference_id | Missing versioned journey API |
| POST | `/relationship/expense/check` | `relationship_expense_check`; [app.py:3120](../app.py#L3120) | form:expense_strategy | Missing versioned journey API |
| GET | `/journey` | `journey_view`; [app.py:3140](../app.py#L3140) | — | Missing versioned journey API |
| GET | `/married` | `married_view`; [app.py:3173](../app.py#L3173) | — | Missing versioned journey API |
| POST | `/journey/advance` | `journey_advance`; [app.py:3217](../app.py#L3217) | — | Missing versioned journey API |
| GET | `/road` | `road_view`; [app.py:3248](../app.py#L3248) | — | Missing versioned journey API |
| GET | `/road/routine` | `road_routine`; [app.py:3254](../app.py#L3254) | — | Missing versioned journey API |
| POST | `/road/routine/add` | `road_routine_add`; [app.py:3278](../app.py#L3278) | form:category, form:days, form:end, form:label, form:start | Missing versioned journey API |
| POST | `/road/routine/remove` | `road_routine_remove`; [app.py:3297](../app.py#L3297) | form:block_id | Missing versioned journey API |
| GET | `/road/obligations` | `road_obligations`; [app.py:3309](../app.py#L3309) | — | Missing versioned journey API |
| POST | `/road/obligations/add` | `road_obligations_add`; [app.py:3331](../app.py#L3331) | form:end_date, form:start_date, form:title, form:travel_mode, form:type | Missing versioned journey API |
| POST | `/road/obligations/remove` | `road_obligations_remove`; [app.py:3352](../app.py#L3352) | form:entry_id | Missing versioned journey API |
| GET | `/road/availability` | `road_availability`; [app.py:3361](../app.py#L3361) | — | Missing versioned journey API |
| POST | `/road/availability/add-free` | `road_availability_add_free`; [app.py:3394](../app.py#L3394) | form:days, form:end, form:start | Missing versioned journey API |
| POST | `/road/availability/remove-free` | `road_availability_remove_free`; [app.py:3409](../app.py#L3409) | form:block_id | Missing versioned journey API |
| POST | `/road/availability/share` | `road_availability_share`; [app.py:3421](../app.py#L3421) | form:slot | Missing versioned journey API |
| GET | `/road/vision` | `road_vision`; [app.py:3432](../app.py#L3432) | — | Missing versioned journey API |
| POST | `/road/vision/set` | `road_vision_set`; [app.py:3455](../app.py#L3455) | form:key, form:stance | Missing versioned journey API |
| GET | `/` | `home`; [app.py:3538](../app.py#L3538) | — | Entry/enrollment design |
| GET, POST | `/signup` | `signup`; [app.py:3565](../app.py#L3565) | form:email, form:phone | Entry/enrollment design |
| GET, POST | `/onboarding/vision` | `onboard_vision`; [app.py:3594](../app.py#L3594) | form:intimacy_kinds, form:other_keys, form:preset | Entry/enrollment design |
| GET, POST | `/onboarding/stats` | `onboard_stats`; [app.py:3670](../app.py#L3670) | — | Entry/enrollment design |
| GET, POST | `/onboarding/chemistry` | `onboard_chemistry`; [app.py:3730](../app.py#L3730) | — | Entry/enrollment design |
| GET, POST | `/onboarding/finish` | `onboard_finish`; [app.py:3761](../app.py#L3761) | — | Entry/enrollment design |
| GET | `/verify-contact` | `verify_contact`; [app.py:3857](../app.py#L3857) | — | Simulation/admin: exclude public parity |
| POST | `/verify-contact/send` | `verify_contact_send`; [app.py:3869](../app.py#L3869) | form:channel | Simulation/admin: exclude public parity |
| POST | `/verify-contact/check` | `verify_contact_check`; [app.py:3904](../app.py#L3904) | form:channel, form:code | Simulation/admin: exclude public parity |
| POST | `/onboarding/restart` | `onboard_restart`; [app.py:3934](../app.py#L3934) | — | Entry/enrollment design |
| GET | `/verify` | `verify_view`; [app.py:3976](../app.py#L3976) | — | Missing versioned journey API |
| POST | `/verify/start` | `verify_start`; [app.py:3991](../app.py#L3991) | — | Missing versioned journey API |
| POST | `/verify/simulate` | `verify_simulate`; [app.py:4000](../app.py#L4000) | form:outcome | Simulation/admin: exclude public parity |
| POST | `/demo/advance` | `demo_advance`; [app.py:4021](../app.py#L4021) | form:back, form:step | Simulation/admin: exclude public parity |
| POST | `/demo/partner` | `demo_partner`; [app.py:4032](../app.py#L4032) | — | Simulation/admin: exclude public parity |
| GET | `/pay/<purpose>` | `pay_view`; [app.py:4103](../app.py#L4103) | query:next | Missing versioned journey API |
| POST | `/pay/<purpose>/confirm` | `pay_confirm`; [app.py:4123](../app.py#L4123) | form:next | Missing versioned journey API |
| GET | `/ceremony/<kind>` | `ceremony_view`; [app.py:4260](../app.py#L4260) | query:face, query:unsigned | Missing versioned journey API |
| POST | `/ceremony/<kind>/step` | `ceremony_step`; [app.py:4311](../app.py#L4311) | form:acks, form:signed_name | Missing versioned journey API |
| GET | `/debrief` | `debrief_view`; [app.py:4472](../app.py#L4472) | — | Missing versioned journey API |
| GET, POST | `/align` | `align_view`; [app.py:4513](../app.py#L4513) | form:budget, form:cuisine | Missing versioned journey API |
| POST | `/plan/cancel` | `plan_cancel`; [app.py:4573](../app.py#L4573) | — | Missing versioned journey API |
| POST | `/debrief/no-show` | `debrief_no_show`; [app.py:4623](../app.py#L4623) | — | Missing versioned journey API |
| GET | `/after-date` | `after_date_view`; [app.py:4742](../app.py#L4742) | — | Missing versioned journey API |
| GET | `/guru` | `guru_view`; [app.py:4783](../app.py#L4783) | — | Missing versioned journey API |
| GET | `/guru/everything` | `guru_all_view`; [app.py:4805](../app.py#L4805) | — | Missing versioned journey API |
| GET | `/admin/errors` | `admin_errors`; [app.py:4851](../app.py#L4851) | query:ref | Simulation/admin: exclude public parity |
| GET | `/admin/pairs` | `admin_pairs`; [app.py:4874](../app.py#L4874) | — | Simulation/admin: exclude public parity |
| POST | `/admin/reset-walkthrough` | `admin_reset_walkthrough`; [app.py:4880](../app.py#L4880) | form:partner_id, form:user_id | Simulation/admin: exclude public parity |
| GET, POST | `/admin/reset-week` | `admin_reset_week`; [app.py:4935](../app.py#L4935) | form:action | Simulation/admin: exclude public parity |
