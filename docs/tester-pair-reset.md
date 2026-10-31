# Reset synthetic pair 06 and distribute updated builds

Local HEAD when reviewed: 3afe52c (26 October 2026). Later Signzy/pilot changes were not committed. This document does not establish what commit is deployed remotely.

The operator CLI `tester_reset_admin.py` returns an existing configured synthetic pair to the start of Dating. It preserves profile declarations, account phone/email, identity/BGV evidence and the shared clock. It removes that pair's selected journey records and assigns reciprocal fixed candidates for the configured start week. It does not reset all signup declarations or revoke logins. Ask both testers to log out before running and log back in afterward.

## Prerequisites

Deploy the reviewed commit to the dedicated Railway test service. Keep the existing valid start week. Include 06 in fixed pairs and both profile IDs in the tester allowlist. Variables, alphabetically:

```text
DHASHU_ACCELERATED_TEST=false
DHASHU_ASYNC_TEST=true
DHASHU_FIXED_TEST_PAIRS=<preserve existing slots and include 06, sorted ascending>
DHASHU_SIMULATED_CLOCK=true
DHASHU_TEST_START_WEEK=<existing valid test week>
DHASHU_TESTER_NO_OTP=true
DHASHU_TESTER_USER_IDS=<preserve existing IDs and include test_blr_20260921_f06,test_blr_20260921_m06, sorted>
```

## Railway service console

```bash
python tester_reset_admin.py --pair 06
# Only after DRY RUN OK and checking the displayed table counts:
python tester_reset_admin.py --pair 06 --apply
```

The first command exercises the complete reset and assignment in a transaction, then rolls it all back. Apply creates a private pre-reset JSON backup under ignored `data/tester-reset-backups/` before deleting rows, then commits atomically. Preserve/download the backup securely if Railway storage is ephemeral. The command refuses local fallback without DATABASE_URL, third-party journey/match involvement, restaurant bookings or billing purchases needing review. On STOP, do not delete records to force progress; inspect the named issue. No external cancellation/refund is performed. SQLite regression tests were run; live PostgreSQL execution has not been verified.

Do not use the older HTML Reset both action for this purpose: it also changes the shared clock.

## App distribution

Pushing a Git commit alone does not update installed apps. Confirm Railway deploys that commit, then build Android and iOS from the same commit in Codemagic and distribute the new APK/TestFlight build. Verify the build number, OTP-free login for allowed synthetic accounts, pair 06's fresh introduction and both members' actions. Signzy verification remains a separately configured pilot; publishing this code does not resolve provider access or enable production BGV.
