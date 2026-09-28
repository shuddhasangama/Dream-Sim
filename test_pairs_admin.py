"""Assign configured synthetic pairs. Dry run rolls back the entire transaction."""
import argparse

import async_rehearsal
import db
import fixed_test_pairs
import week_service


class DryRun(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    pairs = fixed_test_pairs.configured()
    if not pairs:
        parser.error('Enable asynchronous simulation and set DHASHU_FIXED_TEST_PAIRS first.')
    conn = db.get_connection()
    try:
        try:
            with week_service.transition(conn):
                for a in sorted(uid for uid in pairs if uid.startswith(fixed_test_pairs.PREFIX + 'f')):
                    print(a, '<->', pairs[a], ':', fixed_test_pairs.assign(conn, a, async_rehearsal.start_week()))
                if not args.apply:
                    raise DryRun()
            print('APPLIED. No accounts, verification flags or recorded decisions changed.')
        except DryRun:
            print('DRY RUN OK: all changes rolled back. Repeat with --apply.')
        except ValueError as exc:
            parser.exit(1, f'STOP: {exc}. Entire operation rolled back.\n')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
