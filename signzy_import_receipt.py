"""Reprocess an already user-bound private receipt without calling Signzy."""
import argparse
import db
from signzy.receipts import ReceiptStore
from signzy.verification import import_receipt

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    args = parser.parse_args()
    conn = db.get_connection()
    try:
        db.init_db(conn)
        print('Field evidence status:', import_receipt(conn, args.path, ReceiptStore()))
    except Exception:
        raise SystemExit('Import failed. Check receipt binding, encryption access and database schema. No API request made.')
    finally:
        conn.close()
