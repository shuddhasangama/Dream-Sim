# Account deletion (feat-delete, feat-purge)

Owner decision: a **30-day grace period**.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `DHASHU_DELETE_GRACE_DAYS` | 30 | Days between the request and the permanent purge (1–365). |
| `DHASHU_SECURITY_RETENTION_DAYS` | 180 | How long `SecurityEvent` and `MemberLockEvent` rows are kept (minimum 7). |

## Flow

1. **Request.** In the app: Settings → Delete account. On the web: `/account/delete`. Confirm with the password or a one-time code sent to the member's own phone.
2. **Immediately:** every session is revoked; the member is hidden from REACH, weekly matching and discovery; a partner sees "No longer available".
3. **Grace period:** signing in shows "Your account is scheduled for deletion on <date>" with **Cancel deletion**. Cancelling restores everything.
4. **After the grace period:** the worker's `account_purge` job deletes everything:
   - The member's own rows are deleted.
   - Shared history (lock-ins, couples, matches) is re-pointed to an anonymous tombstone id, and the member's side of shared text is cleared.
   - Shared Guru discussions are deleted.
   - Payment records keep the amounts and status only.
   - Security and lock events are kept anonymously until retention removes them.
   - One `DeletionRecord` keeps the counts, with no identity.
5. **Retention:** every 5 minutes, the worker removes security records older than the retention period.

**Admin:** owners see pending deletions in `GET /api/reports/deletions` (audited).

**Public page:** `/delete-account` explains all of this, with no sign-in. Use its full URL in the App Store and Google Play "account deletion" fields (manual step).

## Requirements on Railway

The worker service (`bgv_worker`) must be running, or purges and retention never happen.

**Schema:** Alembic `0007_account_deletion`, or the automatic reconcile.
