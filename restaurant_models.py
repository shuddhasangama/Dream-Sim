"""Canonical, provider-neutral search and quote validation. Amounts are minor units."""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import math
from restaurant_preferences import identifiers, CUISINES, DIETS


@dataclass(frozen=True)
class SearchRequest:
    market_id: str
    country: str
    city: str
    currency: str
    currency_exponent: int
    timezone: str
    date_time: str
    party_size: int
    neighbourhoods: tuple
    cuisines: tuple
    dietary_requirements: tuple
    minimum: int
    maximum: int
    simulation: bool

    @classmethod
    def from_snapshot(cls, value):
        bounds=value['budget_per_person_minor']
        if type(bounds['min']) is not int or type(bounds['max']) is not int or not 0 <= bounds['min'] < bounds['max']:
            raise ValueError('An explicit valid budget range is required')
        ZoneInfo(value['timezone'])
        stamp=datetime.fromisoformat(value['date_time'])
        if stamp.tzinfo is None:
            raise ValueError('Provider searches require a timezone-aware timestamp')
        places=value['neighbourhoods']
        if not 1<=len(places)<=2:
            raise ValueError('Choose one or two shared neighbourhoods')
        for place in places:
            coordinates(place)
        return cls(value['id'],value['country'],value['city'],value['currency'],value.get('currency_exponent',2),
                   value['timezone'],stamp.isoformat(),2,tuple(dict(p) for p in places),tuple(value['cuisines']),
                   tuple(value['dietary_requirements']),bounds['min'],bounds['max'],value.get('simulation') is True)

    def provider_input(self):
        # Deliberately excludes pair/user IDs, identity records, tokens, and any
        # other app-only fields from the original snapshot.
        return {'id':self.market_id,'country':self.country,'city':self.city,'currency':self.currency,
                'currency_exponent':self.currency_exponent,'timezone':self.timezone,'date_time':self.date_time,
                'party_size':self.party_size,'neighbourhoods':[dict(p) for p in self.neighbourhoods],
                'cuisines':sorted(identifiers(self.cuisines, CUISINES)),
                'dietary_requirements':sorted(identifiers(self.dietary_requirements, DIETS) - {'unrestricted'}),
                'budget_per_person_minor':{'min':self.minimum,'max':self.maximum},'simulation':self.simulation}


def coordinates(value):
    for key,limit in (('lat',90),('lon',180)):
        if type(value.get(key)) not in (int,float) or not math.isfinite(value[key]) or abs(value[key])>limit:
            raise ValueError('Invalid coordinates')


def normalize_quote(raw, request, provider_id, label, adapter_key):
    coordinates(raw)
    text=('id','name','neighbourhood','currency','cancellation')
    for key in text:
        if not isinstance(raw.get(key),str) or not raw[key] or len(raw[key])>1000:
            raise ValueError('Invalid quote text')
    for key in ('cuisines','diets'):
        if not isinstance(raw.get(key),list) or any(not isinstance(v,str) or len(v)>100 for v in raw[key]):
            raise ValueError('Invalid dietary/cuisine list')
    amounts=('estimate_per_person_minor','deposit_minor','food_credit_minor','booking_fee_minor')
    for key in amounts:
        if type(raw.get(key)) is not int or not 0<=raw[key]<=1000000000:
            raise ValueError('Unknown or invalid quote amount')
    if raw['food_credit_minor']>raw['deposit_minor']:
        raise ValueError('Food credit cannot exceed the prepaid deposit')
    if type(raw.get('available')) is not bool or raw['currency']!=request.currency or raw.get('currency_exponent',2)!=request.currency_exponent:
        raise ValueError('Quote availability or currency mismatch')
    # Strict allowlist: arbitrary provider metadata and credentials never reach clients.
    q={k:raw[k] for k in (*text,*amounts,'lat','lon','cuisines','diets','available')}
    # Adapters return canonical IDs (legacy DhaShu labels are also accepted).
    for key, vocabulary in (('cuisines', CUISINES), ('diets', DIETS)):
        labels = {value: label for label, value in vocabulary.items()}
        q[key] = [labels[value] for value in sorted(identifiers(q[key], vocabulary) - {'unrestricted'})]
    q.update(id=provider_id+':'+raw['id'],provider_venue_id=raw['id'],provider_id=provider_id,
             provider_label=label,adapter_key=adapter_key,currency_exponent=request.currency_exponent,
             upfront_minor=raw['deposit_minor']+raw['booking_fee_minor'],
             # Redeemable food credit is prepaid food, not an additional expense.
             estimated_total_minor=max(request.party_size*raw['estimate_per_person_minor'],raw['food_credit_minor'])+raw['booking_fee_minor']+raw['deposit_minor']-raw['food_credit_minor'])
    # Cross-provider venue IDs are used only when an adapter supplies a verified
    # mapping. Never merge venues merely because their names look alike.
    if isinstance(raw.get('canonical_venue_id'),str) and 0<len(raw['canonical_venue_id'])<=200:
        q['canonical_venue_id']=raw['canonical_venue_id']
    return q
