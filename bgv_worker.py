"""Run alongside the API using the same database and encryption key."""
import argparse
import time
import db
import bgv_app
import bgv_bundle
import avatar_service
import face_image_lease
import face_match_service
import liveness_secure_service
import provider_jobs
import digilocker_signup  # noqa: F401 — registers the digilocker_create job kind
import guru_navigator  # noqa: F401 — registers the guru_reply job kind (DHASHU_ASYNC_GURU)

def avatar_step():
    """Own connection: a slow image call must not block legal/identity checks."""
    conn=db.acquire()
    try:return avatar_service.work_one(conn)
    finally:db.release(conn)


def bgv_step(once=False):
    conn=db.acquire()
    try:
        face_image_lease.purge(conn)
        bgv_bundle.schedule(conn)
        processed=liveness_secure_service.work_one(conn)
        processed=face_match_service.work_one(conn) or processed
        if once:processed=avatar_service.work_one(conn) or processed
        processed=provider_jobs.work_one(conn) or processed   # perf-worker: background provider calls
        return bgv_app.work_one(conn) or processed
    finally:db.release(conn)


def avatar_loop(stop):
    import logging
    while not stop.is_set():
        try:processed=avatar_step()
        except Exception as error:
            logging.error('Avatar worker iteration failed: %s',type(error).__name__)
            processed=False
        if not processed:stop.wait(5)


def run(once=False):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    bgv_app.config()
    if once:
        print('Processed one request.' if bgv_step(once=True) else 'No queued requests.')
        return
    stop=Event()
    install_shutdown(stop)
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='avatar') as pool:
        pool.submit(avatar_loop,stop)
        try:
            loop(stop)
        finally:stop.set()


def loop(stop, step=None, idle=5):
    """Main worker loop. Exits between iterations once `stop` is set, so a deploy's
    SIGTERM never interrupts a claimed job midway (c-resilience graceful shutdown)."""
    step=step or bgv_step
    next_check=0.0
    while not stop.is_set():
        if time.monotonic()>=next_check:   # mon-alerts: stuck verification work, every 5 minutes
            next_check=time.monotonic()+300
            check_stuck()
        try:
            processed=step()
        except Exception as error:
            import logging
            logging.error('BGV worker iteration failed: %s',type(error).__name__)
            processed=False
        if not processed:stop.wait(idle)


def check_stuck():
    import alerts
    conn=None
    try:
        conn=db.acquire()
        alerts.check_stuck_jobs(conn)
    except Exception as error:
        import logging
        logging.error('Stuck-job check failed: %s',type(error).__name__)
    finally:
        db.release(conn)


def install_shutdown(stop):
    """SIGTERM/SIGINT ask the loop to finish its current iteration and exit."""
    import signal
    def handle(signum, frame):
        print('Worker stopping after the current iteration.', flush=True)
        stop.set()
    for name in ('SIGTERM','SIGINT'):
        if hasattr(signal,name):
            signal.signal(getattr(signal,name),handle)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    run(once=parser.parse_args().once)
