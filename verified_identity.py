"""Canonical identity remains encrypted; only derived age enters matching Stats."""
import json
import db
from bgv_app import Protection


def owner_identity(conn,uid):
    user=db.fetch_one(conn,'User',id=uid)
    stats=json.loads(user.get('stats_json') or '{}') if user else {}
    sid=stats.get('identity_session_id')
    if not sid:return None
    row=db.fetch_one(conn,'DigiLockerSession',id=sid)
    if not row or row['user_id']!=uid or row['state']!='complete' or not row.get('protected_result'):return None
    identity=Protection().open(row['protected_result'])
    return {key:identity[key] for key in ('name','dob','age','age_as_of')}


def apply(conn,uid,sid,identity,environment):
    user=db.fetch_one(conn,'User',id=uid)
    stats=json.loads(user['stats_json'] or '{}')
    stats.update(age=identity['age'],identity_session_id=sid,identity_environment=environment)
    # Name/DOB stay in the protected identity record. Never put them in public Stats.
    user['stats_json']=json.dumps(stats,ensure_ascii=False)
    db.insert_row(conn,'User',user)
