"""The client's address for rate limits, abuse checks, audit and logs (sec-ip).

This module is the ONLY place that reads request.remote_addr or a forwarding
header (enforced by test_client_ip.py, which scans the code). Everything else
calls client_ip() (the visitor's key) or socket_peer() (the raw TCP peer, used
only where the real connection matters: the local harness's loopback check).

DHASHU_TRUSTED_PROXY:
  none / unset   local or direct: the socket peer.
  railway        Railway's proxy appends the address it saw to X-Forwarded-For.
                 The visitor is the entry DHASHU_TRUSTED_HOPS from the RIGHT
                 (default 1). The left-most entries are whatever the client sent
                 and are never trusted.
  cloudflare     Cloudflare -> (Railway) -> app. CF-Connecting-IP is used only
                 when the hop that reached the edge (X-Forwarded-For counted from
                 the right as above) is inside Cloudflare's published ranges
                 (cloudflare_ips.txt, refreshed by tools/update_cloudflare_ips.py)
                 OR the request carries X-CF-Origin-Secret equal to
                 DHASHU_CF_ORIGIN_SECRET (set by a Cloudflare request rule).
                 Otherwise it behaves like `railway`.

Keys: IPv4 as-is; IPv6 by its /64 network (one household / one device's
rotating addresses share one key; different /64s never do).

Fallback, never one shared bucket: if the visitor cannot be resolved behind a
proxy (missing or invalid header, too few hops) and the socket peer is a
private/proxy address, the key is 'unresolved:<hash of the request's own
client fingerprint>' and a 'client_ip_unresolved' alert fires (once per window).
A public socket peer (direct connection) is used as-is.

Safety net: note_identity() is called with each phone number asked for a code
and each member signed in; when one key collects more than
DHASHU_SHARED_IP_ALERT (default 30) distinct identities in 10 minutes, a
'shared_ip_bucket' alert fires (a misconfigured proxy, or a real shared NAT).
"""
import hashlib
import hmac
import ipaddress
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger('dhashu.client_ip')

_CF_FILE = Path(__file__).with_name('cloudflare_ips.txt')
_lock = threading.Lock()
_identities = {}          # key -> (window_start, set of identity hashes)
_alerted = {}             # (event, key) -> window_start
WINDOW = 600


def _mode():
    value = os.environ.get('DHASHU_TRUSTED_PROXY', '').strip().lower()
    return value if value in ('railway', 'cloudflare') else 'none'


def _hops():
    try:
        return max(1, min(5, int(os.environ.get('DHASHU_TRUSTED_HOPS', '1'))))
    except ValueError:
        return 1


def parse(value):
    """A valid IP address object, or None."""
    try:
        return ipaddress.ip_address(str(value).strip().strip('[]'))
    except (ValueError, TypeError):
        return None


def key_for(address):
    """Rate-limit key: IPv4 as-is, IPv6 by /64."""
    if address.version == 6:
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f'{address}/64', strict=False))
    return str(address)


_CF_CACHE = None


def cloudflare_networks():
    global _CF_CACHE
    if _CF_CACHE is None:
        nets = []
        for line in _CF_FILE.read_text(encoding='utf-8').splitlines():
            line = line.split('#', 1)[0].strip()
            if line:
                nets.append(ipaddress.ip_network(line))
        _CF_CACHE = nets
    return _CF_CACHE


def from_cloudflare(address):
    return address is not None and any(address in net for net in cloudflare_networks() if net.version == address.version)


def socket_peer(request):
    """The raw TCP peer. Only for checks about the connection itself (local harness)."""
    return request.remote_addr


def _forwarded_hop(request):
    """The address the trusted proxy saw: X-Forwarded-For counted from the right."""
    chain = [part.strip() for part in request.headers.get('X-Forwarded-For', '').split(',') if part.strip()]
    hops = _hops()
    if len(chain) < hops:
        return None
    return parse(chain[-hops])


def _origin_secret_ok(request):
    secret = os.environ.get('DHASHU_CF_ORIGIN_SECRET', '')
    sent = request.headers.get('X-CF-Origin-Secret', '')
    return len(secret) >= 16 and bool(sent) and hmac.compare_digest(sent, secret)


def resolve(request):
    """(address or None, how). how: 'peer' | 'forwarded' | 'cloudflare' | 'unresolved'."""
    mode = _mode()
    peer = parse(socket_peer(request))
    if mode == 'none':
        return peer, 'peer'
    hop = _forwarded_hop(request)
    if mode == 'cloudflare' and (from_cloudflare(hop) or _origin_secret_ok(request)):
        visitor = parse(request.headers.get('CF-Connecting-IP', ''))
        if visitor is not None:
            return visitor, 'cloudflare'
    if hop is not None:
        return hop, 'forwarded'
    if peer is not None and peer.is_global:
        return peer, 'peer'                                  # a direct connection, not via the proxy
    return None, 'unresolved'


def _fingerprint(request):
    parts = [request.headers.get(h, '') for h in ('User-Agent', 'Accept-Language', 'Sec-CH-UA', 'Authorization')]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:16]


def client_ip(request):
    """The visitor's rate-limit / audit key. Never one shared bucket."""
    address, how = resolve(request)
    if address is not None:
        return key_for(address)
    _alert_once('client_ip_unresolved', 'unresolved', mode=_mode())
    return 'unresolved:' + _fingerprint(request)


def _alert_once(event, key, **fields):
    now = time.time()
    with _lock:
        if now - _alerted.get((event, key), 0) < WINDOW:
            return False
        _alerted[(event, key)] = now
    try:
        import alerts
        alerts.emit(event, **fields)
    except Exception:   # noqa: BLE001 — alerting must never break a request
        log.warning('%s', event)
    return True


def note_identity(key, identity):
    """Safety net: many phone numbers / members behind one key -> 'shared_ip_bucket'."""
    try:
        limit = max(2, int(os.environ.get('DHASHU_SHARED_IP_ALERT', '30')))
    except ValueError:
        limit = 30
    digest = hashlib.sha256(str(identity).encode('utf-8')).hexdigest()[:16]
    now = time.time()
    with _lock:
        start, seen = _identities.get(key, (now, set()))
        if now - start >= WINDOW:
            start, seen = now, set()
        seen.add(digest)
        _identities[key] = (start, seen)
        if len(_identities) > 20000:
            for k in [k for k, (s, _) in _identities.items() if now - s >= WINDOW]:
                _identities.pop(k, None)
        count = len(seen)
    if count > limit:
        # the key itself is hashed: an alert never carries an address
        _alert_once('shared_ip_bucket', key, identities=count, window_seconds=WINDOW,
                    client=hashlib.sha256(key.encode()).hexdigest()[:12])


def reset():
    global _CF_CACHE
    with _lock:
        _identities.clear(); _alerted.clear()
    _CF_CACHE = None


def startup_check(environ=None):
    """Warn when running on Railway without a trusted-proxy mode (every member would
    then share the proxy's address). Returns the warning text, or None."""
    env = os.environ if environ is None else environ
    on_railway = any(k.startswith('RAILWAY_') and env.get(k) for k in env)
    if on_railway and env.get('DHASHU_TRUSTED_PROXY', '').strip().lower() not in ('railway', 'cloudflare'):
        message = ('DHASHU_TRUSTED_PROXY is not set on Railway: every visitor would share the proxy address. '
                   'Set DHASHU_TRUSTED_PROXY=railway (or cloudflare). See docs/CLIENT_IP.md.')
        log.warning(message)
        return message
    return None
