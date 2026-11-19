"""Read-only signup audit. No SMS, credentials or contact details printed."""
import os
from collections import Counter
import db
import auth_delivery
import auth_sessions

conn=db.get_connection()
try:
    users=db.fetch_all(conn,'User');accounts=db.fetch_all(conn,'Account')
    print('Users:',len(users),'Accounts:',len(accounts))
    print('Journey states:',dict(Counter(r['journey_state'] for r in users)))
    print('Disabled accounts:',sum(not r.get('auth_enabled') for r in accounts))
    print('SMS provider:',auth_delivery.provider())
    print('Selected provider configuration format valid:',auth_delivery.configured())
    for name in ('MSG91_AUTH_KEY','MSG91_TEMPLATE_ID') if auth_delivery.provider() == 'msg91' else ('TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN','TWILIO_VERIFY_SERVICE_SID'):
        print(name, 'SET' if os.environ.get(name) else 'MISSING')
    for name in ('DHASHU_SIMULATED_CLOCK','DHASHU_ASYNC_TEST','DHASHU_TESTER_NO_OTP','DEMO_MODE'):
        print(name, os.environ.get(name,'NOT SET'))
    print('Fixed test-pair configuration present:',bool(os.environ.get('DHASHU_FIXED_TEST_PAIRS')))
    rows=auth_sessions.sql(conn, 'SELECT provider_sid,account_id FROM "AuthChallenge" WHERE expires_at >= ?', (auth_sessions.now()-86400,)).fetchall()
    print('Recent challenges:',len(rows))
    print('With provider acceptance:',sum(bool(r['provider_sid']) for r in rows))
    print('Without linked account:',sum(not r['account_id'] for r in rows))
    print('A missing provider SID alone cannot distinguish an unrecognised login from delivery failure.')
    print('Check Dream-Sim logs for OTP delivery unavailable and its numeric provider_code.')
    print('READ ONLY: no records changed; no SMS sent.')
finally:
    conn.close()
