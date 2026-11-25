"""Minimal real-time activity; no routes, messages, IPs or raw user agents retained."""
import logging
import threading
import time
import db
import auth_sessions

_recent={}
_lock=threading.Lock()

def interval():
    """perf-lastseen: seconds between "last seen" writes per member (default 300).
    DHASHU_LAST_SEEN_INTERVAL, clamped to 60..3600. Applied in memory (per process)
    and in SQL (across processes/replicas), so a busy member costs at most one
    write per interval instead of one per request."""
    import os
    try:
        value=int(os.environ.get('DHASHU_LAST_SEEN_INTERVAL','300'))
    except ValueError:
        value=300
    return max(60,min(3600,value))

def record(user_id,kind,user_agent):
    now=int(time.time())
    every=interval()
    with _lock:
        if now-_recent.get(user_id,0)<every:return
        if len(_recent)>10000:_recent.clear()
        _recent[user_id]=now
    ua=str(user_agent).lower()
    platform='android' if 'android' in ua else 'ios' if 'iphone' in ua or 'ipad' in ua else 'web' if kind=='web' else 'unknown'
    conn=None
    try:
        conn=db.acquire()
        with auth_sessions.transaction(conn):
            auth_sessions.sql(conn,'INSERT INTO "UserActivity" (user_id,first_seen_at,last_seen_at,platform,auth_kind) VALUES (?,?,?,?,?) ON CONFLICT (user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,platform=excluded.platform,auth_kind=excluded.auth_kind WHERE "UserActivity".last_seen_at<?',
                (user_id,now,now,platform,kind,now-every+1))
    except Exception:
        # Analytics must never block successful member authentication.
        logging.getLogger(__name__).warning('Member activity storage unavailable; authentication continues.')
    finally:
        if conn is not None:db.release(conn)
