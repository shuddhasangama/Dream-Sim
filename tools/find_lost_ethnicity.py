"""Find (and optionally restore) member ethnicity erased by the Stats-save bug.

Bug (fixed in 002b063): from 2026-11-17, saving ANY Stats change from Home or REACH
sent ethnicity: null and erased the member's ethnicity. This tool compares a BACKUP
database (taken before the loss) with a TARGET database (the current one).

    python tools/find_lost_ethnicity.py --backup BACKUP --target TARGET           # dry run
    python tools/find_lost_ethnicity.py --backup BACKUP --target TARGET --apply   # restore

BACKUP / TARGET: a PostgreSQL URL or a SQLite file path.

A member is a candidate when ethnicity is NON-EMPTY in the backup and EMPTY in the
target, and (by default) the member was active on or after --since (2026-11-17),
i.e. could have saved Stats while the bug was live. --all-members drops that filter.

Dry run (default): prints the counts and the member ids only. No personal data
(never an ethnicity value, name, phone or email) is printed.
--apply: restores the backup value ONLY where the target value is still empty at
the moment of writing (compare-and-set on the whole stats row), one transaction
per member. A member who has since re-entered or changed it is never overwritten.

Safety: refuses any non-local database host (Railway or anything else that is not
localhost / 127.0.0.1 / ::1 / a local SQLite file) unless --i-confirm-production is
given. Never runs automatically: nothing in the app or worker calls it.
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1', ''}


def is_local(target):
    if not target.startswith(('postgres://', 'postgresql://')):
        return True                                                      # a SQLite file on this machine
    host = (urlparse(target).hostname or '').lower()
    return host in LOCAL_HOSTS


def describe(target):
    if not target.startswith(('postgres://', 'postgresql://')):
        return 'sqlite:' + Path(target).name
    parsed = urlparse(target)
    return f'{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip("/")}'


class Database:
    def __init__(self, target):
        self.postgres = target.startswith(('postgres://', 'postgresql://'))
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            self.conn = psycopg.connect(target, row_factory=dict_row)
        else:
            if not Path(target).exists():
                raise SystemExit(f'No such SQLite file: {target}')
            self.conn = sqlite3.connect(target)
            self.conn.row_factory = sqlite3.Row
        self.p = '%s' if self.postgres else '?'

    def rows(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql.replace('?', self.p), args).fetchall()]

    def close(self):
        self.conn.close()


def ethnicity(stats_json):
    try:
        value = (json.loads(stats_json or '{}') or {}).get('ethnicity')
    except (ValueError, TypeError):
        return []
    return [v for v in value if isinstance(v, str) and v] if isinstance(value, list) else []


def active_since(db, since_epoch):
    try:
        return {r['user_id'] for r in db.rows('SELECT user_id FROM "UserActivity" WHERE last_seen_at >= ?', (since_epoch,))}
    except Exception:   # noqa: BLE001 — no activity table: cannot tell, so nobody qualifies
        if db.postgres:
            db.conn.rollback()
        return set()


def find(backup, target, since_epoch=None):
    before = {r['id']: ethnicity(r['stats_json']) for r in backup.rows('SELECT id, stats_json FROM "User"')}
    now = {r['id']: ethnicity(r['stats_json']) for r in target.rows('SELECT id, stats_json FROM "User"')}
    lost = sorted(uid for uid, value in before.items() if value and uid in now and not now[uid])
    if since_epoch is not None:
        recent = active_since(target, since_epoch)
        lost = [uid for uid in lost if uid in recent]
    return lost, before


def restore(target, uid, value):
    """Compare-and-set: write only if the stored row still has no ethnicity."""
    row = target.rows('SELECT stats_json FROM "User" WHERE id = ?', (uid,))
    if not row or ethnicity(row[0]['stats_json']):
        return False
    stats = json.loads(row[0]['stats_json'] or '{}')
    stats['ethnicity'] = list(value)
    cur = target.conn.execute(('UPDATE "User" SET stats_json = ? WHERE id = ? AND stats_json = ?').replace('?', target.p),
                              (json.dumps(stats), uid, row[0]['stats_json']))
    target.conn.commit()
    return (cur.rowcount or 0) == 1


def main(argv=None, out=print):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--since', default='2026-11-17', help='only members active on/after this date (YYYY-MM-DD, UTC)')
    parser.add_argument('--all-members', action='store_true', help='do not filter by recent activity')
    parser.add_argument('--apply', action='store_true', help='restore (default: dry run)')
    parser.add_argument('--i-confirm-production', action='store_true',
                        help='allow a non-local database host (owner only, after a backup)')
    args = parser.parse_args(argv)
    for name in ('backup', 'target'):
        value = getattr(args, name)
        if not is_local(value) and not args.i_confirm_production:
            out(f'Refusing: --{name} is not a local database ({describe(value)}). '
                'Add --i-confirm-production only when the owner has approved a run against it.')
            return 2
    since_epoch = None if args.all_members else int(datetime.strptime(args.since, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
    out(f'Backup: {describe(args.backup)}   Target: {describe(args.target)}   '
        f'Mode: {"APPLY" if args.apply else "dry run"}   Filter: {"all members" if since_epoch is None else "active since " + args.since}')
    backup, target = Database(args.backup), Database(args.target)
    try:
        lost, before = find(backup, target, since_epoch)
        out(f'Members with ethnicity in the backup but empty now: {len(lost)}')
        for uid in lost:
            out(f'  {uid}')
        if args.apply:
            restored = sum(1 for uid in lost if restore(target, uid, before[uid]))
            out(f'Restored: {restored}   Skipped (no longer empty): {len(lost) - restored}')
    finally:
        backup.close(); target.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
