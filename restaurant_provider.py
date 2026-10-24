"""Provider boundary for Phase 4. Only the deterministic simulator is registered.

Live adapters must honour attempt IDs, provide status lookup, and never accept
simulation timestamps. No restaurant credentials or network calls live here.
"""
import math
from typing import Protocol


class Provider(Protocol):
    def search(self, request: dict, radius_km: int) -> list[dict]: ...
    def recheck(self, quote: dict) -> dict: ...
    def reserve(self, quote: dict, attempt_id: str) -> dict: ...
    def status(self, attempt_id: str) -> dict: ...
    def cancel(self, reference: str) -> dict: ...


def distance_km(a, b):
    lat1, lat2 = math.radians(a['lat']), math.radians(b['lat'])
    dl = math.radians(b['lat']-a['lat'])
    dn = math.radians(b['lon']-a['lon'])
    v = math.sin(dl/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dn/2)**2
    return 6371 * 2 * math.asin(min(1, math.sqrt(v)))


class SimulatedProvider:
    name = 'simulation'

    def __init__(self, scenario='success'):
        if scenario not in {'success','empty','unavailable','price_changed','timeout','payment_failed','refund_failed'}:
            raise ValueError('Unknown booking simulation scenario')
        self.scenario = scenario

    def search(self, request, radius_km):
        if self.scenario == 'empty':
            return []
        budget = request['budget_per_person_minor']
        # An open-ended band has no safe upper limit for an automated quote.
        if budget['max'] is None:
            return []
        price = (budget['min'] + budget['max']) // 2
        unit = 10 ** request.get('currency_exponent', 2)
        rows = []
        for area in request['neighbourhoods']:
            for n, km in enumerate((0.4, 1.4, 2.4)):
                point = {'lat': area['lat'] + km / 111.195, 'lon': area['lon']}
                if distance_km(area, point) > radius_km:
                    continue
                rows.append({'id': f"sim:{request['id']}:{area['id']}:{n}",
                    'name': f"Demo restaurant {n+1} — {area['name']}",
                    **point, 'neighbourhood': area['name'], 'cuisines': request['cuisines'],
                    'diets': request['dietary_requirements'], 'available': True,
                    'estimate_per_person_minor': price, 'currency': request['currency'],
                    'currency_exponent': request.get('currency_exponent', 2),
                    'deposit_minor': min(price, 500 * unit), 'food_credit_minor': min(price, 500 * unit),
                    'booking_fee_minor': 0, 'cancellation': 'Fully refundable in this simulation.'})
        return rows

    def recheck(self, quote):
        if self.scenario == 'unavailable':
            return {'available': False}
        if self.scenario == 'price_changed':
            return {'available': True, 'changed': True}
        return {'available': True, 'changed': False}

    def reserve(self, quote, attempt_id):
        if self.scenario == 'timeout':
            return {'status': 'unknown', 'reference': None}
        return self.status(attempt_id)

    def status(self, attempt_id):
        return {'status': 'confirmed', 'reference': 'SIM-'+attempt_id[:16]}

    def cancel(self, reference):
        return {'status': 'cancelled', 'refund': 'failed' if self.scenario == 'refund_failed' else 'processed'}
