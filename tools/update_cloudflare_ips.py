"""Refresh cloudflare_ips.txt from Cloudflare's public lists (sec-ip). Dry run by default.

    python tools/update_cloudflare_ips.py           show what would change
    python tools/update_cloudflare_ips.py --apply   write cloudflare_ips.txt

Reads only the two public pages https://www.cloudflare.com/ips-v4 and /ips-v6 (no
account, no credentials). Every line is validated as a network; the file is never
written empty or with fewer than 10 ranges. Run by a person, then commit the file.
"""
import argparse
import ipaddress
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'cloudflare_ips.txt'
SOURCES = ('https://www.cloudflare.com/ips-v4', 'https://www.cloudflare.com/ips-v6')
HEADER = ['# Cloudflare\'s published edge ranges (https://www.cloudflare.com/ips-v4 and /ips-v6).',
          '# Used by client_ip.py: CF-Connecting-IP is trusted only from these hops.',
          '# Refresh: python tools/update_cloudflare_ips.py (dry run), then --apply, and commit.']


def fetch(url, opener=urlopen):
    with opener(Request(url, headers={'User-Agent': 'dhashu-ip-ranges'}), timeout=15) as response:
        return response.read(64_000).decode('ascii')


def parse(text):
    nets = []
    for line in text.split():
        nets.append(str(ipaddress.ip_network(line.strip())))   # raises on anything that is not a network
    return nets


def current():
    return [l.strip() for l in TARGET.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')]


def render(v4, v6):
    return '\n'.join(HEADER + ['# IPv4', *v4, '# IPv6', *v6]) + '\n'


def main(argv=None, opener=urlopen, out=print):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    v4, v6 = (parse(fetch(url, opener)) for url in SOURCES)
    if len(v4) + len(v6) < 10:
        out('Refusing: Cloudflare returned too few ranges.')
        return 2
    old, new = set(current()), set(v4 + v6)
    out(f'Added: {sorted(new - old) or "none"}')
    out(f'Removed: {sorted(old - new) or "none"}')
    if args.apply and old != new:
        TARGET.write_text(render(v4, v6), encoding='utf-8')
        out(f'Wrote {TARGET.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
