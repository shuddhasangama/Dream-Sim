"""Reset one configured synthetic pair to Dating. Dry run by default; no clock reset."""
import argparse
import json
import os
from pathlib import Path
import secrets
from datetime import datetime, timezone
import db
import auth_sessions
import async_rehearsal
import fixed_test_pairs
import week_service

# Children before parents. Profiles, contacts, BGV/identity evidence, billing
# ledgers, private Guru notes and the shared simulation clock are preserved.
TABLES = [
    'RestaurantEvent', 'BookingSnapshot', 'RehearsalReady', 'RehearsalIntro', 'Signature', 'DateOutcome', 'DateFeedback',
    'DateResolution', 'JourneyAction', 'DateCharge', 'BookingPreference',
    'GateAsk', 'GateResponse', 'GateAnalysis', 'StageGate', 'ContactRequest',
    'HomeInvite', 'NextLevelThread', 'GuruDiscussion', 'Ceremony',
    'ComplianceEvent', 'Payment', 'Availability', 'DatePlan', 'Match',
    'MatchBatch', 'RoadProfile', 'CalendarEntry', 'Playbook', 'Difference',
    'GuruTopic', 'WeeklyReport', 'Exit', 'LockIn', 'Couple',
]


class DryRun(Exception):
    pass


def reset(conn, number, *, apply=False, backup_dir='data/tester-reset-backups'):
    if not 1 <= number <= 10:
        raise ValueError('Pair must be 01 through 10')
    ids = {f'{fixed_test_pairs.PREFIX}{sex}{number:02d}' for sex in ('f', 'm')}
    with week_service.transition(conn):
        users = [dict(db.fetch_one(conn, 'User', id=uid) or {}) for uid in sorted(ids)]
        if any(not u or u['bgv_status'] != 'verified' for u in users):
            raise ValueError('Both existing synthetic profiles must already be simulation-verified')
        if any(fixed_test_pairs.configured().get(uid) not in ids for uid in ids):
            raise ValueError('Enable this fixed pair and asynchronous OTP-free simulation first')
        for uid in ids:
            account = db.fetch_one(conn, 'Account', user_id=uid)
            if not account or not account['auth_enabled'] or not auth_sessions.tester_allowed(uid):
                raise ValueError('Both profiles require enabled, allowlisted tester accounts')
        locks = [dict(r) for r in db.fetch_all(conn, 'LockIn') if ids & {r['user_a'], r['user_b']}]
        couples = [dict(r) for r in db.fetch_all(conn, 'Couple') if ids & {r['partner_a_id'], r['partner_b_id']}]
        for row in locks + couples:
            members = ({row['user_a'], row['user_b']} if 'user_a' in row else
                       {row['partner_a_id'], row['partner_b_id']})
            if members != ids:
                raise ValueError('A selected user has journey history with another profile; preserved')
        lockids, coupleids = {r['id'] for r in locks}, {r['id'] for r in couples}
        planids = {r['id'] for r in db.fetch_all(conn, 'DatePlan') if r['lockin_id'] in lockids}
        scopes = lockids | coupleids | planids
        # Real/provider side effects cannot be undone by deleting local rows.
        if any(r['id'] in planids for r in db.fetch_all(conn, 'RestaurantBooking')):
            raise ValueError('Booking records exist; reconcile bookings before reset')
        if any(r['user_id'] in ids for r in db.fetch_all(conn, 'BillingPurchase')):
            raise ValueError('Billing purchases exist; review entitlements before reset')
        selected = {}
        for table in TABLES:
            selected[table] = []
            for raw in db.fetch_all(conn, table):
                r = dict(raw)
                own = ids & {r.get(k) for k in ('user_id','requester_id','owner_id','candidate_id','user_a','user_b')}
                linked = scopes & {r.get(k) for k in ('pair_id','lockin_id','dateplan_id','couple_id','scope_id')}
                root = ((table == 'LockIn' and r['id'] in lockids) or
                        (table == 'Couple' and r['id'] in coupleids))
                if own or linked or root:
                    if table == 'Match' and {r['user_id'],r['candidate_id']} - ids:
                        raise ValueError('Match rows involve another profile; preserved for review')
                    selected[table].append(r)
        counts = {t:len(rs) for t,rs in selected.items() if rs}
        print(json.dumps({'pair':f'{number:02d}','rows_to_remove':counts,
                          'next_state':'dating','clock':'unchanged'}, indent=2))
        if apply:
            directory = Path(backup_dir)
            directory.mkdir(parents=True, exist_ok=True)
            name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            path = directory / f'pair-{number:02d}-{name}-{secrets.token_hex(4)}.json'
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump({'user_states':users,'removed_rows':selected},f,default=str)
            print('Private pre-reset backup:',path)
        for table,rows in selected.items():
            for row in rows:
                auth_sessions.sql(conn,f'DELETE FROM "{table}" WHERE id = ?', (row['id'],))
        for uid in ids:
            auth_sessions.sql(conn,'UPDATE "User" SET journey_state = ? WHERE id = ?',('dating',uid))
        fixed_test_pairs.assign(conn, sorted(ids)[0], async_rehearsal.start_week())
        if not apply:
            raise DryRun()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair',type=int,required=True)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    if not os.getenv('DATABASE_URL'):
        p.error('Run in Railway console with DATABASE_URL; local fallback is intentionally refused')
    conn=db.get_connection()
    try:
        reset(conn,args.pair,apply=args.apply)
        print('APPLIED: pair reset and reciprocal candidates assigned. Log out and back in.')
    except DryRun:
        print('DRY RUN OK: all changes rolled back; repeat with --apply to reset.')
    except Exception as exc:
        p.exit(1,f'STOP: {type(exc).__name__}: {exc}. Transaction rolled back.\n')
    finally:
        conn.close()


if __name__=='__main__':
    main()
