"""Curated activity names, reviewed aliases and distinct-member popularity.

The canonical public names are stable matching keys. No unreviewed suggestion
becomes a public catalogue option. Older private custom answers are retained.
"""
import json
import time
import unicodedata
import db
import onboarding
import auth_sessions
from api_contract import ApiError


def key(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def aliases(conn):
    return {**{key(x): x for x in onboarding.ACTIVITIES},
            **{r['id']: r['canonical'] for r in db.fetch_all(conn, 'ActivityAlias')}}


def normalize(skills, mapping):
    result = dict(skills)
    activities = dict(skills.get('activities', {}))
    # An existing canonical answer wins a conflict. Preserve the old answer in
    # an archive rather than silently replacing a user's explicit preference.
    archive = dict(skills.get('activity_alias_archive', {}))
    for name, answer in list(activities.items()):
        target = mapping.get(key(name), name)
        if target != name:
            archive[name] = answer
            activities.setdefault(target, answer)
            activities.pop(name)
    result.update(onboarding.build_skills(activities))
    result['activity_alias_archive'] = archive
    result['custom_activities'] = [x for x in skills.get('custom_activities', []) if x in activities and x not in onboarding.ACTIVITIES]
    # Never infer indifference when merging conflicting answers.
    result['partner_any'] = [x for x in skills.get('partner_any', []) if x in activities]
    return result


def ordered(conn):
    counts = dict.fromkeys(onboarding.ACTIVITIES, 0)
    mapping = aliases(conn)
    for row in db.fetch_all(conn, 'User'):
        skills = normalize(db.load_json_field(row['skills_json'], {}), mapping)
        for name, answer in skills['activities'].items():
            if name in counts and answer != 'no':
                counts[name] += 1
    order = {name: i for i, name in enumerate(onboarding.ACTIVITIES)}
    return sorted(counts, key=lambda x: (-counts[x], order[x]))


def queue(conn, names):
    for name in names:
        identity = key(name)
        if not db.fetch_one(conn, 'ActivitySuggestion', id=identity):
            db.insert_row(conn, 'ActivitySuggestion', dict(id=identity, name=name, state='pending', updated_at=int(time.time())))


def review(conn, name, canonical, actor):
    if not isinstance(name, str) or canonical not in onboarding.ACTIVITIES:
        raise ApiError('validation_error', 'Choose a suggestion and a listed canonical activity.')
    identity = key(name)
    if identity in {key(x) for x in onboarding.ACTIVITIES}:
        raise ApiError('validation_error', 'Curated activities cannot be merged through suggestion review.')
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "User", "ActivityAlias", "ActivitySuggestion" IN SHARE ROW EXCLUSIVE MODE')
        suggestion = db.fetch_one(conn, 'ActivitySuggestion', id=identity)
        if not suggestion:
            raise ApiError('not_found', 'Suggestion not found.', 404)
        db.insert_row(conn, 'ActivityAlias', dict(id=identity, canonical=canonical, reviewed_by=actor, updated_at=int(time.time())))
        mapping = aliases(conn)
        for row in db.fetch_all(conn, 'User'):
            before = db.load_json_field(row['skills_json'], {})
            after = normalize(before, mapping)
            if before != after:
                row['skills_json'] = json.dumps(after, ensure_ascii=False)
                db.insert_row(conn, 'User', row)
        suggestion.update(state='mapped', canonical=canonical, reviewed_by=actor, updated_at=int(time.time()))
        db.insert_row(conn, 'ActivitySuggestion', suggestion)
