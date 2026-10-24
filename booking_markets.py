"""Phase 1: server-owned country/city/provider routing, with no provider calls."""
import json
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo


def enabled():
    return os.environ.get('DHASHU_BOOKING_COORDINATION_ENABLED', '0') == '1'


def markets():
    path = os.environ.get('DHASHU_BOOKING_MARKETS_FILE')
    data = json.loads(Path(path or Path(__file__).with_name('booking_markets.json')).read_text(encoding='utf-8'))
    seen = set()
    for market in data:
        key = market['id']
        if key in seen or len(market['country']) != 2 or len(market['currency']) != 3:
            raise ValueError('Invalid or duplicate booking market')
        seen.add(key)
        ZoneInfo(market['timezone'])
        bands = market['budget_ranges_minor']
        if not bands:
            raise ValueError('Each market needs budget ranges in its currency minor units')
        for band, limits in bands.items():
            if not isinstance(band, str) or not band or type(limits['min']) is not int or limits['min'] < 0 or (limits['max'] is not None and (type(limits['max']) is not int or limits['max'] <= limits['min'])):
                raise ValueError('Invalid booking budget range')
        places = market['neighbourhoods']
        if not 3 <= len(places) <= 15 or len({p['id'] for p in places}) != len(places):
            raise ValueError('Each market needs 3–15 unique neighbourhoods')
        for p in places:
            if not all(type(p[k]) in (int, float) and math.isfinite(p[k]) for k in ('lat', 'lon')) or not -90 <= p['lat'] <= 90 or not -180 <= p['lon'] <= 180:
                raise ValueError('Invalid neighbourhood coordinates')
        providers = market['providers']
        if not providers or len({p['id'] for p in providers}) != len(providers):
            raise ValueError('Each market needs unique provider routes')
        if any(p['status'] not in ('not_connected', 'sandbox', 'live') for p in providers):
            raise ValueError('Invalid provider status')
    return data


def for_city(city, country=None):
    name = str(city or '').strip().casefold()
    matches = [m for m in markets() if name in {v.casefold() for v in [m['city'], *m.get('aliases', [])]}
               and (not country or m['country'] == country)]
    # Never silently route a duplicated city name to the wrong country.
    return matches[0] if len(matches) == 1 else None


def search_request(snapshot, dateplan_id):
    """Internal phase-4 handoff. IDs and coordinates originate on the server.

    This is a planning request, not a reservation or a promise of availability.
    Simulated day/meal slots must become a real timestamp before provider use.
    """
    return {**snapshot, 'schema_version': 1, 'dateplan_id': dateplan_id, 'party_size': 2,
            'radius_steps_km': [1, 2, 3], 'reservation_status': 'not_requested',
            'requires_real_datetime': True}
