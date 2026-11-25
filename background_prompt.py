"""One-time "Please confirm your background details" prompt (ethnicity-restore fallback).

Members whose ethnicity was erased by the Stats-save bug (fixed in 002b063) and who
cannot be restored from a backup are asked once, in the app, to confirm their
background details. Behind DHASHU_ETHNICITY_PROMPT (default 0 = never shown).

Shown when ALL hold: the setting is on; the member is past onboarding; their
ethnicity is empty; they have not dismissed it. It stops by itself once an ethnicity
is saved (it is then no longer empty), or for good after "Not now" (stats flag
background_prompt_done). Ethnicity stays optional: nothing is ever required.
"""
import os

import db

DONE = 'background_prompt_done'


def enabled():
    return os.environ.get('DHASHU_ETHNICITY_PROMPT', '0') == '1'


def should_show(user):
    if not enabled() or not user or user.get('journey_state') in (None, 'onboarding'):
        return False
    stats = user.get('stats') or {}
    has_ethnicity = isinstance(stats.get('ethnicity'), list) and any(stats['ethnicity'])
    return not has_ethnicity and not stats.get(DONE)


def dismiss(conn, uid):
    import evolution_service
    with evolution_service.transaction(conn, uid):
        row = db.fetch_one(conn, 'User', id=uid)
        stats = db.load_json_field(row['stats_json'], {}) or {}
        if not stats.get(DONE):
            stats[DONE] = True
            row['stats_json'] = db.json_field(stats)
            db.insert_row(conn, 'User', row)


def register(api, get_db):
    from flask import g, jsonify
    from api_contract import json_object

    @api.post('/profile/background-prompt/dismiss')
    def background_prompt_dismiss():
        json_object()
        dismiss(get_db(), g.api_user['user_id'])
        return jsonify(background_prompt=False)
