# Encryption keys: rotation, backup and recovery (sec-keys)

Losing a key means losing the data it encrypts, permanently. Read this section before changing any key.

## The keys

| Variable | Protects | Where it is used |
|---|---|---|
| `SIGNZY_RECEIPT_ENCRYPTION_KEY` | Verification inputs and results, DigiLocker, liveness, face match, avatar selfies, BGV evidence and notes | `bgv_app.Protection` |
| `WAITLIST_ENCRYPTION_KEY` | Waitlist entries | `waitlist_service` |
| `DHASHU_GURU_ENCRYPTION_KEY` | Guru private notes and discussions | `guru_navigator` |
| `DHASHU_IDENTITY_ENCRYPTION_KEY` | Identity capture images | `identity_capture` |
| `ADMIN_TOTP_ENCRYPTION_KEY` | Admin authenticator secrets | `admin_dashboard/security` |
| `DHASHU_DATA_ENCRYPTION_KEY` | Member fields (phone, photo, debrief, exit feedback, gate answers) | `member_crypto` (sec-enc) |

The following are **HMAC keys, not encryption keys**. Rotating one breaks every lookup, so they cannot be rotated with this procedure: `WAITLIST_HASH_KEY` and `DHASHU_BLIND_INDEX_KEY` (sec-enc). Change them only together with a full re-index.

## Settings for each key

```
NAME=<fernet key>                    current key: encrypts and decrypts
NAME_ID=k2                           name of the current key (optional; default "current")
NAME_PREVIOUS=k1:<key>,k0:<key>      older keys: decrypt only (optional)
```

To generate a key, run this on your own machine (never in a shared log):

```
py -3.12 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Rotating a key (no downtime)

1. Generate the new key and choose a new id (for example `k2`).
2. Back up the new key (see the next section) **before** using it.
3. In Railway, set all three settings in a single change and deploy it to every service that uses the key (web, worker, admin):
   - `NAME` = the new key
   - `NAME_ID=k2`
   - `NAME_PREVIOUS=k1:<old key>` (plus any older keys still listed)
4. From then on, new values are encrypted with `k2` and old values still open.
5. Run the dry run: `python tools/reencrypt_keys.py --key NAME`. It shows how many values sit on each key id.
6. Run `python tools/reencrypt_keys.py --key NAME --apply`. This is safe while the app is running, because a row that changed since it was read is skipped.
7. Run the dry run again. Only `k2` should be listed (plus any `unreadable` values; investigate those, never delete them).
8. Remove the old key from `NAME_PREVIOUS` and deploy. **Keep the old key in the backup for 90 days.** Database backups made before step 6 still need it.

## Backup

- Every key and its id is stored in the company password manager, in a vault limited to the owner and one named deputy. The entry records the variable, key id, creation date and retirement date.
- A second copy is kept offline: printed, or on an encrypted USB drive in a safe. This covers the case where the password manager account is lost.
- Never store keys in git, chat, email, tickets, screenshots, `.env` files on shared drives, or CI logs.
- Database backups and key backups are kept apart. Someone who has only one of them can read nothing.

## Recovery

| Situation | What to do |
|---|---|
| A service lost its variable | Restore the key from the password manager under the same id, then redeploy. |
| A key is suspected leaked | Rotate it immediately (steps above), run `--apply`, remove the leaked key, then review access logs. Leaked data cannot be un-leaked, so treat it as an incident (`docs/GO_LIVE_RUNBOOK.md`). |
| Restoring an old database backup | It may need retired keys. Put them back in `NAME_PREVIOUS`, restore, run `--apply`, then remove them again. |
| A key is lost with no backup | The data it protected can't be recovered. Rows show as `unreadable` in the dry run. Members must re-verify; Guru history and waitlist entries for those rows are gone. |

## Manual steps (not done by code)

- Move every key into Railway **sealed** variables (sealed values cannot be read back from the dashboard).
- Create the password-manager vault entries and the offline copy for each key that exists today.
- Set the `NAME_ID` values to match what is recorded in the backup.
