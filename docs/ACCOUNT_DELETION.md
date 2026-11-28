# Account deletion (feat-delete, feat-purge)

Owner decision: a **30-day grace period**.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `DHASHU_DELETE_GRACE_DAYS` | 30 | Days between the request and the permanent purge (1–365). |
| `DHASHU_SECURITY_RETENTION_DAYS` | 180 | How long `SecurityEvent` and `MemberLockEvent` rows are kept (minimum 7). |
| `DHASHU_DELETED_RETENTION_DAYS` | 730 | How long the deleted member's contact hash and exit type are kept after the purge (1–3650; 730 = 2 years). |

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
   - One `DeletedContactRetention` row keeps **only** a keyed hash of the member's phone (or of the email when there is no phone) and the **exit type**. Owner decision, 27 Nov 2026.
5. **Retention:** every 5 minutes, the worker removes security records older than their retention period, and deleted-contact records whose 2 years (`DHASHU_DELETED_RETENTION_DAYS`) are over.

## What is kept after the purge, and why it is a hash

| Kept | Not kept |
|---|---|
| A keyed hash (HMAC-SHA256) of the phone, or of the email when there is no phone | The phone or email itself, the name, the member id, anything else |
| Exit type: `good_exit` or `bad_exit` | Why: only the result of the rule below |
| When it was purged and when the record will be deleted | |

- **Exit type:**
  - `bad_exit` means an owner had locked the account, or the member had a `report`, `violation` or `no_show` compliance event.
  - Every other deletion is a `good_exit`.
- **Why a hash and not encryption:**
  - The only use of this record is an exact-match question: "has this phone or email left before, and how?"
  - A keyed hash answers that when an owner types the contact in. It can never be turned back into a phone number or email, so nobody can read two years of ex-members' contacts, even with database and key access.
  - Encryption would keep them readable, and the purpose does not need that (data minimisation).
- **Key:**
  - The hash uses `DHASHU_BLIND_INDEX_KEY` when it is set (at least 32 characters), otherwise the app `SECRET_KEY`. The row records which one was used.
  - Rotating that key makes older records unfindable. They are still deleted on time.
- **Who can see it:**
  - Owners only, in the admin dashboard: `POST /api/deleted-contacts/lookup` with `{"contact": "+91..."}`.
  - The answer is the exit type and dates only. The contact is never stored, logged or echoed back, and every lookup is written to the admin audit log.
  - Members have no route to it.

**Admin:** owners see pending deletions in `GET /api/reports/deletions` (audited).

**Public page:** `/delete-account` explains all of this, with no sign-in. Use its full URL in the App Store and Google Play "account deletion" fields (manual step).

## Requirements on Railway

The worker service (`bgv_worker`) must be running, or purges and retention never happen.

**Schema:** Alembic `0007_account_deletion` and `0008_deleted_contact_retention`, or the automatic reconcile.
