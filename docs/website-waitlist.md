# Website-to-database waitlist deployment

This release saves the waitlist and optional story answers, adds manual launch
controls and private statistics. It does not change Stats/REACH/date planning,
create app accounts, verify contacts, automatically invite users or activate matching.
Those later integrations use separate status dimensions as agreed.

## Files
Backend: waitlist_service.py, waitlist_api.py, waitlist_admin.py,
waitlist_markets.json, app.py, db.py, schema.sql, schema_postgres.sql.
Website overlay: website-waitlist/home.html, assets/story.js, assets/waitlist.js.
The overlay was based on the live website retrieved during this task. Copy ONLY
these three files to the existing website repository, retaining other assets,
index.html and the domain configuration. Do not replace the whole site repository.

## 1. Railway backend
Deploy the reviewed backend files and initialise the additive schema:
/app/.venv/bin/python -c "import db; c=db.get_connection(); db.init_db(c); c.close()"

Set:
DHASHU_WAITLIST_ENABLED=1
WAITLIST_ALLOWED_ORIGINS=https://dhashu.com,https://www.dhashu.com
WAITLIST_ENCRYPTION_KEY=<Fernet key generated once and backed up privately>
WAITLIST_HASH_KEY=<independent random secret, at least 32 characters>

Use the existing persistent database, not ephemeral SQLite storage. Keep these keys
server-side. Changing the hash key breaks deduplication; changing the encryption key
without migration makes previous records unreadable. Generate keys privately; do not
commit them. The website API URL is in assets/waitlist.js.

## 2. Website
Deploy the three overlay files AFTER the API is enabled. Existing email delivery via
FormSubmit is removed: records now go to the database, and no email notifications are
sent by this release. Automatic notification delivery can be added with an outbox later.
No Codemagic rebuild is required for these website-only changes.

## 3. Test
Submit your own test entry at dhashu.com. Refresh or submit again with the same email:
the original entry must remain unchanged and the same generic acknowledgement appears.
Select up to three neighbourhoods in Bengaluru. Other listed cities currently have no
configured neighbourhoods; selecting them is still allowed. Other-city/country interest
is stored as a free-text location, not automatic access to a matching market.
Story answers use sessionStorage in the same tab until the user submits; they are sent
only if the user selects the optional sharing checkbox. Abandoned answers are not saved
centrally. Existing historical story answers cannot be recovered.

Run privately in the backend environment:
python waitlist_admin.py stats
python waitlist_admin.py launch IN-BLR preparing --actor Dharesh
python waitlist_admin.py launch IN-BLR open --actor Dharesh
python waitlist_admin.py status <entry-id> invited --actor Dharesh

The last command records an operator action; send an invitation separately only after
review. Opening a city never invites anyone or changes matching eligibility.

## Limits and follow-up
- Registration email is not confirmed: metrics must not be labelled verified users.
- No public read/export/list endpoint exists. Stats commands are private to operators.
- Same-email repeats cannot overwrite data. Contact-confirmed editing/account linking
  is not implemented; do not merge users by names or blindly link an unconfirmed email.
- Launch state and waitlist status are independent of app account/matching status.
- For now one city and up to three neighbourhoods; no cross-city matching.
- Rate limits use Flask remote_addr, not untrusted forwarded headers. Confirm Railway's
  trusted-proxy configuration before a campaign; shared proxy IPs can share the limit.
  Add a verified anti-bot challenge before large paid campaigns. Origin checks alone
  do not stop scripted submissions.
- No deletion or notification automation yet. Handle data-rights requests through a
  controlled operator process; agree retention before collecting at scale.

Tests: python -m unittest test_waitlist -q
Schema parity: python -m pytest test_schema_postgres.py -q
