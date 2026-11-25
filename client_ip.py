"""The client's IP address for rate limits and abuse checks (sec-cf).

Headers such as CF-Connecting-IP or X-Forwarded-For can be sent by anyone, so
they are trusted ONLY when the deployment says a trusted proxy sets them:

    DHASHU_TRUSTED_PROXY=cloudflare   use CF-Connecting-IP (only when it is a valid IP)
    (unset / anything else)           use the socket peer (request.remote_addr)

Never used for the local harness, which must see the real loopback peer.
Adithya's sec-ip work extends this single function rather than adding another.
"""
import ipaddress
import os


def _valid(value):
    try:
        return str(ipaddress.ip_address(value.strip()))
    except (ValueError, AttributeError):
        return None


def client_ip(request):
    if os.environ.get('DHASHU_TRUSTED_PROXY', '').strip().lower() == 'cloudflare':
        forwarded = _valid(request.headers.get('CF-Connecting-IP', ''))
        if forwarded:
            return forwarded
    return request.remote_addr or 'unknown'
