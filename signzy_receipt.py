"""Explicit private viewing: decrypted data goes to your terminal, never a new file."""
import argparse
import base64
import json
from signzy.receipts import read_private

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    args = parser.parse_args()
    try:
        result = read_private(args.path)
        print('PRIVATE PERSONAL DATA: do not share this terminal output or screenshots.')
        # Raw bytes remain in the encrypted receipt; omit duplicated base64 from display.
        if result.get('provider_response'):
            raw = result['provider_response'].pop('body_base64', None)
            if raw and result['provider_response'].get('json') is None:
                result['provider_response']['raw_text'] = base64.b64decode(raw).decode('utf-8', errors='replace')
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception:
        raise SystemExit('Cannot open receipt. Check path and original Windows account or encryption key.')
