"""Reserve an operator-invited beta profile. Dry run unless --apply; sends no messages."""
import argparse
import db
from enrollment_service import invite

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email')
    parser.add_argument('--phone')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    conn = db.get_connection()
    try:
        db.init_db(conn)
        print(invite(conn, args.email, args.phone, args.apply))
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        conn.close()

if __name__ == '__main__':
    main()
