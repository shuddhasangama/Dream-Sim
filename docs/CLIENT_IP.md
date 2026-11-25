# Client IP behind Railway and Cloudflare (sec-ip)

Every per-visitor limit (OTP send/check, refresh, password, tester, waitlist, admin login, abuse guard), audit row and log uses `client_ip.client_ip(request)`. That module is the **only** code allowed to read `request.remote_addr` or a forwarding header; a test scans the repository for it.

**Why it matters:** behind Railway's proxy, `remote_addr` is the proxy, so every member used to share one bucket (for example, 20 OTP requests per 10 minutes for the whole app).

## Settings

| Variable | Values | Default | Meaning |
|---|---|---|---|
| `DHASHU_TRUSTED_PROXY` | `railway`, `cloudflare`, unset | unset (local) | Which proxy chain to trust. |
| `DHASHU_TRUSTED_HOPS` | 1–5 | 1 | How many trusted proxies append to `X-Forwarded-For`; the visitor is that many entries from the **right**. |
| `DHASHU_CF_ORIGIN_SECRET` | 16+ characters | unset | Optional. If Cloudflare adds `X-CF-Origin-Secret: <value>`, `CF-Connecting-IP` is trusted even when the hop isn't in the bundled ranges. |
| `DHASHU_SHARED_IP_ALERT` | number | 30 | Distinct numbers or members behind one key in 10 minutes before the `shared_ip_bucket` alert. |

**Keys:**
- IPv4 addresses are used as they are; IPv6 addresses are keyed by their /64.
- If the visitor can't be resolved behind the proxy, the key is a per-visitor fingerprint (`unresolved:…`, never the proxy address) and the `client_ip_unresolved` alert fires.
- On startup, the app logs a warning if Railway variables are present but `DHASHU_TRUSTED_PROXY` isn't set.

## Railway only (no Cloudflare)

1. Railway → the **web** service → Variables: set `DHASHU_TRUSTED_PROXY=railway`. Leave `DHASHU_TRUSTED_HOPS` unset (Railway adds one hop).
2. Do the same on the **admin** service (its login throttle uses the same key).
3. Deploy, then run the post-deploy check below.

## Cloudflare in front of Railway

1. Cloudflare → DNS: the API host is **proxied** (orange cloud), pointing at the Railway domain.
2. Cloudflare → Rules → Transform Rules → *Modify request header* → add a static header `X-CF-Origin-Secret` with a long random value.
3. Railway → web (and admin) → Variables:
   - `DHASHU_TRUSTED_PROXY=cloudflare`
   - `DHASHU_CF_ORIGIN_SECRET=<the same value>`
   - `DHASHU_TRUSTED_HOPS=1`
4. Deploy, then run the post-deploy check.
5. Every quarter, refresh the bundled ranges: run `python tools/update_cloudflare_ips.py` (dry run shows the diff), then `--apply`, and commit `cloudflare_ips.txt`.

## Post-deploy check (5 minutes)

1. From your phone on mobile data **and** from a laptop on Wi-Fi, open the app and request a sign-in code.
2. Railway → web → Logs: the request log line for each shows a **different** client key, and neither is a `100.64.x.x` or `10.x` address.
3. The logs contain no `DHASHU_TRUSTED_PROXY is not set` warning and no `client_ip_unresolved` alert.
4. Ask a colleague on another network to request a code at the same time: neither of you gets "Please wait before requesting another code".
5. If a `shared_ip_bucket` alert fires in the first hour, check the setting; a real shared network (an office) is fine.

**Rollback:** unset `DHASHU_TRUSTED_PROXY`. This returns to the socket peer, the old behaviour.
