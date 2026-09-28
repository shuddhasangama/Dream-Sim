"""Read-only completion evidence for the current pair's week."""
import async_rehearsal
import calendar_dating
import date_alignment
import db
import planning_service


def completed(conn, uid, pair, plan, matches):
    result = {f'match_{m["slot"]}': 'Done' for m in matches if m['action'] in ('interest', 'pass')}
    if not pair:
        return result
    pair = db.fetch_one(conn, 'LockIn', id=pair['id'])
    if not pair:
        return result
    members = (pair['user_a'], pair['user_b'])
    stats = [db.load_json_field(db.fetch_one(conn, 'User', id=u)['stats_json'], {}) for u in members]
    overlap = calendar_dating.compute_overlap(*[planning_service.slots(conn, pair['id'], u) for u in members])
    ready = (bool(overlap) and date_alignment.ready_for_pair(*stats)
             and (not async_rehearsal.enabled() or all(async_rehearsal.intro_complete(conn, u) for u in members)))
    if ready or plan:
        result.update(slots='Completed', calendar_closes='Completed')
    if plan and plan['status'] == 'confirmed':
        result['sign'] = 'Completed'
    # Do not mark a date or Debrief completed merely because time has passed.
    return result
