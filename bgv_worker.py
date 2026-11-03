"""Run alongside the API using the same database and encryption key."""
import argparse
import time
import db
import bgv_app
import bgv_bundle

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    bgv_app.config()
    while True:
        conn = db.get_connection()
        try:
            bgv_bundle.schedule(conn)
            processed = bgv_app.work_one(conn)
        finally:
            conn.close()
        if args.once:
            print('Processed one request.' if processed else 'No queued requests.')
            break
        if not processed:
            time.sleep(5)
