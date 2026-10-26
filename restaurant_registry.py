from restaurant_preferences import matches
"""Pluggable platform registry and deterministic cost-aware selection.

Vendor names in configuration are placeholders, not claims of API access.
Only simulation adapters are executable until reviewed platform connectors and
durable network orchestration are supplied. No automatic post-payment fallback.
"""
import json
import os
from pathlib import Path
from api_contract import ApiError
from restaurant_models import SearchRequest, normalize_quote
from restaurant_provider import SimulatedProvider, distance_km

CAPABILITIES=frozenset({'search','recheck','reserve','status','cancel'})

# Add a reviewed adapter here, not an arbitrary class path supplied by a client.
ADAPTERS={'simulation':{'factory':lambda:SimulatedProvider(os.environ.get('DHASHU_RESTAURANT_SCENARIO','success')),
                        'capabilities':CAPABILITIES|{'deposits','food_credit','refunds'},'simulation':True}}


def config():
    path=os.environ.get('DHASHU_RESTAURANT_PROVIDERS_FILE')
    value=json.loads(Path(path or Path(__file__).with_name('restaurant_providers.json')).read_text(encoding='utf-8'))
    if value.get('selection_policy') not in ('lowest_total','lowest_upfront','nearest'):
        raise ValueError('Unknown restaurant selection policy')
    rows=value['providers']
    if not isinstance(rows,list) or len(rows)>20:
        raise ValueError('Configure at most 20 providers')
    seen=set()
    for row in rows:
        if not isinstance(row.get('id'),str) or not row['id'] or row['id'] in seen:
            raise ValueError('Duplicate or invalid provider ID')
        seen.add(row['id'])
        if not isinstance(row.get('label'),str) or type(row.get('enabled')) is not bool or type(row.get('priority')) is not int:
            raise ValueError('Invalid provider configuration')
        if not isinstance(row.get('markets'),list) or any(not isinstance(m,str) for m in row['markets']):
            raise ValueError('Provider markets must be an array')
        if row.get('adapter') is not None and not isinstance(row['adapter'],str):
            raise ValueError('Invalid adapter key')
    return value


def readiness(settings=None):
    settings=settings or config()
    return [{'id':r['id'],'label':r['label'],'enabled':r['enabled'],
             'configured':r['adapter'] in ADAPTERS,
             'capabilities':sorted(ADAPTERS.get(r['adapter'],{}).get('capabilities',[])),
             'reason': 'disabled' if not r['enabled'] else 'adapter_required' if r['adapter'] not in ADAPTERS else 'simulation_only'}
            for r in settings['providers']]


def rank(q, policy='lowest_total'):
    costs=(q['estimated_total_minor'],q['upfront_minor'],q['distance_km'])
    if policy=='lowest_upfront':
        costs=(q['upfront_minor'],q['estimated_total_minor'],q['distance_km'])
    elif policy=='nearest':
        costs=(q['distance_km'],q['estimated_total_minor'],q['upfront_minor'])
    return (*costs,q.get('provider_priority',100),q['id'])


class Router:
    name='simulation'
    def __init__(self, settings=None):
        self.settings=settings or config()
        self.failures={}
        self.scenario=os.environ.get('DHASHU_RESTAURANT_SCENARIO','success')

    def eligible(self, request):
        result=[]
        for row in self.settings['providers']:
            spec=ADAPTERS.get(row['adapter'])
            if row['enabled'] and (request.market_id in row['markets'] or '*' in row['markets']):
                if not spec or not CAPABILITIES<=spec['capabilities'] or not spec['simulation']:
                    self.failures[row['id']]='adapter_unavailable'
                else:
                    result.append(row)
        return result

    def search(self, snapshot, radius_km):
        try:
            request=SearchRequest.from_snapshot(snapshot)
        except (ValueError,TypeError,KeyError):
            raise ApiError('search_preferences_invalid','This date needs valid shared areas, a spending ceiling and a timezone-aware date before restaurant search.',409)
        options=[]
        for row in self.eligible(request):
            try:
                adapter=ADAPTERS[row['adapter']]['factory']()
                raw=adapter.search(request.provider_input(),radius_km)
                if not isinstance(raw,list) or len(raw)>500:
                    raise ValueError('Invalid provider result size')
                for item in raw:
                    q=normalize_quote(item,request,row['id'],row['label'],row['adapter'])
                    capabilities=ADAPTERS[row['adapter']]['capabilities']
                    if (q['deposit_minor'] and not {'deposits','refunds'}<=capabilities) or (q['food_credit_minor'] and 'food_credit' not in capabilities):
                        raise ValueError('Provider does not support these payment terms')
                    distance=min(distance_km(p,q) for p in request.neighbourhoods)
                    if (not q['available'] or distance>radius_km or not matches(request.cuisines, request.dietary_requirements, q['cuisines'], q['diets'])
                        or not request.minimum<=q['estimate_per_person_minor']<=request.maximum):
                        continue
                    q.update(distance_km=round(distance,2),provider_priority=row['priority'])
                    options.append(q)
            except (TimeoutError,ConnectionError,ValueError,TypeError,KeyError):
                # No raw exceptions/provider bodies: they may contain tokens.
                self.failures[row['id']]='search_unavailable'
        return options

    def shortlist(self, options):
        chosen={}
        for q in sorted(options,key=lambda q:rank(q,self.settings['selection_policy'])):
            key=q.get('canonical_venue_id') or q['id']
            chosen.setdefault(key,q)
        return list(chosen.values())[:3]

    def pinned(self, quote, allow_disabled=False):
        pid=quote.get('provider_id','simulation') # backwards-compatible simulator quotes
        row=next((r for r in self.settings['providers'] if r['id']==pid),None)
        if not row or (not row['enabled'] and not allow_disabled) or row['adapter']!=quote.get('adapter_key','simulation'):
            raise ApiError('provider_unavailable','The selected provider is unavailable. No substitute booking was made.',409)
        spec=ADAPTERS.get(row['adapter'])
        if not spec or not spec['simulation'] or not CAPABILITIES<=spec['capabilities']:
            raise ApiError('provider_unavailable','The selected provider adapter is unavailable.',409)
        return spec['factory']()

    def recheck(self, quote):
        return self.pinned(quote).recheck(quote)

    def reserve(self, quote, attempt_id):
        return self.pinned(quote).reserve(quote,attempt_id)

    def status(self, attempt_id, quote):
        return self.pinned(quote,True).status(attempt_id)

    def cancel(self, reference, quote):
        return self.pinned(quote,True).cancel(reference)
