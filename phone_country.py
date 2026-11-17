"""Phone rollout policy shared with the mobile country selector."""
import json
from pathlib import Path
COUNTRIES = json.loads(Path(__file__).with_name('phone_countries.json').read_text(encoding='utf-8'))
def allowed(value):
    return any(c['enabled'] and value.startswith('+' + c['dial'])
               and len(value[1 + len(c['dial']):]) in c['lengths'] for c in COUNTRIES)
