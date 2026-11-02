"""Private terminal display of the three requested fields; never downloads media."""
import argparse
import json
from signzy.receipts import read_private
from signzy.digilocker_eaadhaar import identity_fields

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt');args=parser.parse_args()
    data=read_private(args.receipt)
    if data.get('operation')!='digilocker_eaadhaar':parser.error('Use an eAadhaar result receipt')
    provider=data.get('provider_response') or {}
    if provider.get('http_status')!=200:parser.error('No successful identity result in this receipt')
    print(json.dumps(identity_fields(provider.get('json')),ensure_ascii=False,indent=2))
