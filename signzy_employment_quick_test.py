"""One-request employment-history probe. No app/database writes or retries."""
import argparse
import getpass
import json
from signzy.client import Client, Config, BASES
from signzy.employment_history import payload, PATH
from signzy.receipts import ReceiptStore


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment',choices=('preproduction','production'),default='preproduction')
    parser.add_argument('--input',choices=('pan','mobile','uan'),help='Send exactly one identifier')
    args=parser.parse_args()
    print('POST '+BASES[args.environment]+PATH)
    print('No app/database changes. One request; it may consume credits. No automatic retry.')
    token=getpass.getpass('Signzy '+args.environment+' API key (hidden): ').strip()
    field=args.input or input('Choose one input: mobile / pan / uan [mobile]: ').strip().lower() or 'mobile'
    if field not in ('pan','mobile','uan'):
        raise ValueError('Choose mobile, pan or uan.')
    labels={'pan':'PAN','mobile':'Mobile, 10 digits without +91','uan':'UAN, 12 digits'}
    value=getpass.getpass(labels[field]+' (hidden): ').strip()
    if field=='pan':value=value.upper()
    values=payload({field:value})
    config=Config(environment=args.environment,token=token,production_enabled=args.environment=='production')
    client=Client(config)
    store=ReceiptStore(directory='data/signzy-employment-test')
    print('Request fields (personal values hidden):')
    print(json.dumps({k:'[provided]' if v else '' for k,v in values.items()},indent=2))
    print('Use only your own or explicitly consented details.')
    if input('Type SEND for one '+args.environment+' request: ').strip()!='SEND':
        print('Cancelled; nothing sent.');return
    saved=[]
    def evidence_sink(evidence):
        saved.append(store.save(evidence))
        response=evidence.get('provider_response') or {}
        print('HTTP:',response.get('http_status'))
        print('PRIVATE provider response (may contain personal details; redact before sharing):')
        print(json.dumps(response.get('json'),indent=2,ensure_ascii=True))
    result=client.execute('employment_history',values,consent_confirmed=True,evidence_sink=evidence_sink)
    print('Summary:');print(json.dumps(result,indent=2))
    for path in saved:print('Encrypted request/response receipt:',path.resolve())
    if result.get('http_status')==404:
        print('No matching record returned. This does not establish unemployment or API equivalence.')
    if result.get('outcome')=='transport_error_outcome_unknown':
        print('Request outcome unknown. Check Signzy logs before considering another call.')


if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError):
        print('Stopped. If SEND was already entered, check Signzy logs before retrying.')
    except ValueError as exc:
        print('Stopped:',str(exc))
