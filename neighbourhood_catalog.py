"""Curated UI choices, independent of launch activation and booking providers."""
import json
from pathlib import Path
import launch_cities
from api_contract import ApiError

def catalogue():
    return json.loads(Path(__file__).with_name('launch_neighbourhoods.json').read_text(encoding='utf8'))

def choices(city):
    market = launch_cities.find(city)
    return catalogue().get(market['name'], []) if market else []

def validate(city, values):
    allowed = {p['id'] for p in choices(city)}
    if not isinstance(values, list) or len(values)>3 or any(not isinstance(v,str) or v not in allowed for v in values) or len(set(values))!=len(values):
        raise ApiError('validation_error', 'Choose up to three listed neighbourhoods in your city.')
    return values
