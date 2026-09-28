# One assigned partner for synthetic tester journeys

This is an opt-in testing policy, not a change to production matching. It bypasses
compatibility selection for explicit pairs, but never invents mutual interest,
BGV verification, alignment, availability, signatures, attendance or Debrief.

## Deployment

Deploy the backend changes to Railway and rebuild both mobile apps for the
calendar button fix. No database schema migration is needed.

Keep the existing settings:

```text
DHASHU_SIMULATED_CLOCK=true
DHASHU_ASYNC_TEST=true
DHASHU_TESTER_NO_OTP=true
DHASHU_TEST_START_WEEK=39
```

Keep the existing DHASHU_TESTER_USER_IDS list. Add this new variable:

```text
DHASHU_FIXED_TEST_PAIRS=02,04,05,06
```

Each number maps to test_blr_20260921_fNN and test_blr_20260921_mNN.
Values 01 through 10 are supported. Only configure pairs whose account access
is ready. Configuration reserves those profiles against new algorithmic matches;
it does not enable accounts or assign phone numbers.

The September 28 audit supports starting with 02,04,05 and preserving 06.
01 and 03 require review of disabled accounts and saved decisions. 07–10 need
account setup first. Readiness is rechecked against the database on every run.

## Railway Dream-Sim Console (Linux shell, not Windows PowerShell)

First run:

```bash
python test_pairs_admin.py
```

This executes assignment inside a transaction and rolls everything back. Expect
ASSIGNED for ready pairs, PRESERVED for an existing active same-number pair, or
ALREADY for existing fixed assignments. No accounts/contacts are printed.

Only after DRY RUN OK, run:

```bash
python test_pairs_admin.py --apply
python test_pairs_admin.py
```

Apply replaces unacted candidate rows involving the assigned pair in the chosen
week, creates exactly one reciprocal slot-1 candidate, and preserves MatchBatch
markers. It does not delete any recorded decision. Incoming decisions from third
parties also cause a stop. Any failed check rolls back the entire operation. Do
not reset or delete records to overcome STOP; review the named conflict first.
If 02 has an incoming recorded decision, leave it out of configuration and use
04,05,06 until reviewed. No automatic assignment occurs on app entry.

## Tester experience

- Continue as tester without SMS remains the sign-in route.
- The matching contact gate accepts enabled, allowlisted testers only while both
  simulated clock and asynchronous rehearsal and OTP-free tester mode are on.
  Actual verified_phone/verified_email values are not changed.
- A new introduction starts Monday 10:00. The single candidate opens at minute 3
  (Monday 12:00). There are no second or third candidate cards for assigned pairs.
- One person's interest is saved; it never auto-accepts for the partner.
- Once mutual interest creates the assigned active pair, both introductions count
  as complete and availability opens immediately (Wednesday 18:00), without
  rewriting intro start timestamps. Existing same-number active pairs receive
  the same shortcut, with their data preserved.
- Without mutual interest the normal intro reaches availability at minute 12;
  draft slots can be saved. Planning still requires mutual interest.
- Both alignment answers and an overlapping saved slot are needed for Thursday
  planning. Agreement, readiness and Debrief keep the existing action-driven gates.
- The calendar is a schedule, so generic Match 2/3 schedule labels may still be
  visible. They are not additional candidates in this mode.

## Disable / reverse policy

Remove DHASHU_FIXED_TEST_PAIRS and redeploy to stop reservation and the early
intro shortcut. This does NOT undo assignments, resurrect replaced unacted rows,
remove active pairs, or erase decisions/history. Existing MatchBatch snapshots
remain stable; normal matching resumes for subsequently prepared weeks.

Turning off DHASHU_TESTER_NO_OTP or DHASHU_ASYNC_TEST removes the new matching
waiver and restores the normal contact policy. Account-level waivers previously
applied manually (verification_required=0) remain independent and are NOT reset.
No contact flags or account policies are mutated by this implementation.

Validate on physical Android/iOS after installing the new builds. Local browser
tests use preview fixtures, not the live Railway database.
