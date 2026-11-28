"""Date preferences (client answer 3, 2026-11-27).

Neighbourhood, diet, cuisine and budget are OPTIONAL at signup, and MANDATORY before
a member accepts a match (weekly interest, daily discovery) or plans a date
(availability), with a clear prompt at that point: the refusal is
409 'date_preferences_required', and the app and the web pages open a short
date-preferences form. This is the only exception to "fill all required details".

Stored where signup already stores them (User.stats_json: neighbourhoods, diet,
cuisine, budget), so filling them in here is the same as at signup.
- Neighbourhood is required only where the member's city has a neighbourhood list
  (launch_neighbourhoods.json); elsewhere it cannot be chosen, so it is not asked.
- This form only fills a blank diet. Changing a diet already set stays in the Stats
  editor, which freezes it while a match is live (a candidate screens on it).
"""
from __future__ import annotations

import json

import db
import neighbourhood_catalog
import onboarding
from api_contract import ApiError

FIELDS = ('neighbourhoods', 'diet', 'cuisine', 'budget')
LABELS = {'neighbourhoods': 'Neighbourhood', 'diet': 'Diet', 'cuisine': 'Cuisine', 'budget': 'Budget'}
CODE = 'date_preferences_required'


def _list(value):
    return value if isinstance(value, list) else ([value] if isinstance(value, str) and value.strip() else [])


def options(city):
    return {'neighbourhoods': neighbourhood_catalog.choices(city) if city else [],
            'diet': list(onboarding.STAT_OPTIONS['diet']),
            'cuisine': list(onboarding.STAT_OPTIONS['cuisine']),
            'budget': list(onboarding.STAT_OPTIONS['budget'])}


def missing(stats):
    stats = stats or {}
    gaps = []
    if neighbourhood_catalog.choices(stats.get('city')) if stats.get('city') else []:
        if not _list(stats.get('neighbourhoods')):
            gaps.append('neighbourhoods')
    if not (isinstance(stats.get('diet'), str) and stats['diet'].strip()):
        gaps.append('diet')
    for field in ('cuisine', 'budget'):
        if not _list(stats.get(field)):
            gaps.append(field)
    return gaps


def _stats(conn, uid):
    row = db.fetch_one(conn, 'User', id=uid)
    return db.load_json_field(row['stats_json'], {}) if row else {}


def message(gaps, before):
    return (f'Before you {before}, complete your date preferences: '
            + ', '.join(LABELS[g] for g in gaps) + '.')


def require(conn, uid, before):
    """Raise 409 date_preferences_required when the member's own preferences are incomplete."""
    gaps = missing(_stats(conn, uid))
    if gaps:
        raise ApiError(CODE, message(gaps, before), 409)


def view(conn, uid):
    stats = _stats(conn, uid)
    return {'values': {f: stats.get(f) for f in FIELDS}, 'options': options(stats.get('city')),
            'missing': missing(stats), 'labels': LABELS, 'city': stats.get('city'),
            'diet_locked': bool(isinstance(stats.get('diet'), str) and stats['diet'].strip())}


def save(conn, uid, body):
    """Fill in / update the date preferences. Returns view()."""
    if type(body) is not dict or not body or set(body) - set(FIELDS):
        raise ApiError('validation_error', 'Send neighbourhoods, diet, cuisine and budget only.')
    import evolution_service
    with evolution_service.transaction(conn, uid):
        row = db.fetch_one(conn, 'User', id=uid)
        stats = db.load_json_field(row['stats_json'], {})
        opts = options(stats.get('city'))
        if 'neighbourhoods' in body:
            stats['neighbourhoods'] = neighbourhood_catalog.validate(stats.get('city'), body['neighbourhoods'] or [])
        if 'diet' in body and body['diet'] not in (None, ''):
            if body['diet'] not in opts['diet']:
                raise ApiError('validation_error', 'Choose a listed diet.')
            current = stats.get('diet')
            if isinstance(current, str) and current.strip() and current != body['diet']:
                raise ApiError('validation_error', 'Change your diet in Stats (it is frozen while a match is live).')
            stats['diet'] = body['diet']
        for field in ('cuisine', 'budget'):
            if field in body:
                values = body[field] if body[field] is not None else []
                if type(values) is not list or any(v not in opts[field] for v in values) or len(set(values)) != len(values):
                    raise ApiError('validation_error', f'Choose listed {field} options.')
                if values:
                    stats[field] = values
                else:
                    stats.pop(field, None)
        row['stats_json'] = json.dumps(stats, ensure_ascii=False)
        db.insert_row(conn, 'User', row)
    return view(conn, uid)


def register(api, get_db):
    from flask import g, jsonify
    from api_contract import json_object

    @api.get('/profile/date-preferences')
    def date_preferences_read():
        return jsonify(view(get_db(), g.api_user['user_id']))

    @api.put('/profile/date-preferences')
    def date_preferences_save():
        body = json_object(optional=set(FIELDS))
        return jsonify(save(get_db(), g.api_user['user_id'], body))
