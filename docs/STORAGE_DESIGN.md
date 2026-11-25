# Storage design note (cq-storage): moving images out of the database

Status: **proposal, not implemented.** Nothing in this note changes behaviour yet; it describes the target and a safe migration.

## Today

Images and large provider payloads are stored as base64 text inside PostgreSQL rows:

| Data | Where | Encrypted |
|---|---|---|
| Profile photo | `ProfilePhoto.data_url` | yes when `DHASHU_FIELD_ENCRYPTION=1` (sec-enc) |
| Avatar selfie, options, chosen avatar | `AvatarJob.protected_selfie / protected_options / protected_selected` | yes (Signzy receipt key) |
| Face-match images | `FaceImageLease.protected_images`, `FaceMatchJob.protected_*` | yes |
| Identity capture image | `IdentityCapture.image_ciphertext` (expires) | yes (identity key) |
| DigiLocker photo | `DigiLockerSession.protected_photo` | yes |

Up to about 2 MB per image becomes about 2.7 MB of base64. Every read of those rows moves that through the database.

**Costs:**
- Backups and restores grow with every member.
- Row reads and WAL traffic are heavy on the shared PostgreSQL.
- The API returns whole data URLs in JSON, so nothing can be cached by a CDN.
- Body limits must allow 3 MB uploads (c-api-abuse).

## Target

Object storage (S3-compatible: Cloudflare R2 or AWS S3, in an India region) for blobs. PostgreSQL keeps only the reference.

**Database stores:**
- `object_key` (random, opaque: `img/<uuid>`)
- `sha256`
- `content_type`
- `bytes`
- `created_at`
- `expires_at`
- `key_id` (the encryption key that sealed it)

**Encryption:**
- The application encrypts each object before upload, using the same `crypto_keys` key rotation (sec-keys). The provider never sees plaintext images.
- The bucket's own encryption at rest is an extra layer, not the only one.

**Access:**
- The bucket is private, with no public ACLs.
- The API serves an image through a short-lived signed URL (5 minutes), only after the same ownership and consent checks used today.
- Alternatively, the API streams the image itself for sensitive identity images, so no URL ever leaves the server.

**Lifecycle rules:**
- Identity-capture and face-match images expire automatically (matching today's `image_expires_at`).
- Abandoned uploads are deleted after 24 hours.
- Deleted members' objects are removed by the purge job (Adithya/Ramya feat-purge).

**Limits:** uploads go through the API (size and type checks as today) and are re-encoded server-side (Pillow, already used) before storage. No direct-to-bucket uploads from clients.

**Backups:** bucket versioning is on, with 30-day non-current retention. Database backups stay small; restoring a member needs both the database row and the object, and is tested in the restore drill.

## Interface

`blob_store.py` exposes `put(kind, raw) -> ref`, `get(ref) -> raw` and `delete(ref)`, with two implementations:

| Implementation | Used by |
|---|---|
| `DatabaseStore` | Today's behaviour (default) |
| `ObjectStore` | Target; selected by `DHASHU_BLOB_STORE=object` plus bucket settings |

Services call only `blob_store`, so switching backends is a setting, not a code change.

## Migration (no downtime, reversible until the last step)

1. Add the `blob_store` interface and `DatabaseStore`. No behaviour change.
2. **Dual-read:** a reference column next to each blob column. Readers use the reference when present, otherwise the inline value.
3. With `DHASHU_BLOB_STORE=object`, new writes go to object storage.
4. Batch tool `tools/move_blobs.py`:
   - dry run by default;
   - `--apply` uploads existing inline values, verifies them by `sha256`, writes the reference, then clears the inline value;
   - compare-and-set per row, the same pattern as `tools/reencrypt_keys.py`.
5. After a full verification run reports 0 inline values, stop writing inline. A later migration drops the inline columns (forward-only).

**Rollback:** until step 5, setting `DHASHU_BLOB_STORE=database` again and re-running the tool with `--inline` restores inline values.

## Open decisions (owner)

1. **Provider:** Cloudflare R2 (no egress fees, already planned for Cloudflare) or AWS S3 (Mumbai region). Data must stay in India if the DPDP Act guidance requires it.
2. **Serving:** signed URLs for profile photos and avatars, versus streaming only, for everything.
3. **Retention:** how long profile photos are kept after an exit or cool-off; align with feat-delete / feat-purge.

## Estimate

About 3–4 days of development and tests, plus one day for the staging migration and restore drill. The work is independent of the Group 1–5 changes; it should follow perf-backup and feat-purge.
