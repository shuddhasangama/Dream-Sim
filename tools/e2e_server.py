"""Local backend for browser end-to-end tests (cq-playwright). LOCAL ONLY.

    python tools/e2e_server.py [--port 5055]

Starts the real Flask app on 127.0.0.1 with:
- a fresh SQLite database in a temporary folder (deleted on exit), never
  dhashu_local / dhashu_test / anything remote (DATABASE_URL is removed);
- three seeded synthetic members test_owner, test_partner (a compatible pair) and
  test_stranger, each with a complete profile, verified and in Dating;
- the local harness (loopback sign-in as a seeded member, no OTP, no provider);
- the simulated clock (tests move it through POST /api/v1/simulated-clock);
- providers mocked in this process only: the date-day face check always passes
  (a random 5% simulated failure must not make the journey flaky), no SMS,
  payments, Signzy, OpenAI or Razorpay calls are possible (their settings are
  removed and the app's own off-switches apply).
Refuses to start if any production marker is present.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PRODUCTION_MARKERS = ('RAILWAY_ENVIRONMENT', 'RAILWAY_PROJECT_ID', 'RAILWAY_SERVICE_ID')
REMOVE = ('DATABASE_URL', 'TEST_DATABASE_URL', 'ADMIN_REPORT_DATABASE_URL', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN',
          'TWILIO_VERIFY_SERVICE_SID', 'MSG91_AUTH_KEY', 'OPENAI_API_KEY', 'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET',
          'SIGNZY_API_KEY', 'SIGNZY_ENV', 'SIGNZY_PRODUCTION_ENABLED', 'SENTRY_DSN')
MEMBERS = {'test_owner': 'female', 'test_partner': 'male', 'test_stranger': 'female'}
PHONES = {'test_owner': '+919876500011', 'test_partner': '+919876500012', 'test_stranger': '+919876500013'}


def prepare_environment(tmp):
    for marker in PRODUCTION_MARKERS:
        if os.environ.get(marker):
            raise SystemExit(f'Refusing to start: {marker} is set (this is a local test server).')
    for name in REMOVE:
        os.environ.pop(name, None)
    os.environ.update({
        'DHASHU_LOCAL_HARNESS': '1', 'AUTH_ENABLED': '0', 'DHASHU_SIMULATED_CLOCK': 'true', 'DEMO_MODE': '1',
        'BETA_DATE_SIMULATION_ENABLED': '1', 'PAYMENTS_ENABLED': '0', 'DHASHU_GURU_AI_ENABLED': '0',
        'DHASHU_BILLING_MODE': 'sandbox',   # only so /billing renders; its API is stubbed in the browser test
        'SECRET_KEY': 'e2e-local-only-secret-key-not-for-any-deployment-0001',
        'DHASHU_DB_POOL': '0', 'DHASHU_SCHEMA_INIT': 'once',
    })
    return Path(tmp) / 'e2e.db'


def seed(db_path):
    import db
    import onboarding
    from test_enrollment_api import sections
    conn = db.get_connection(db_path)
    db.init_db(conn)
    for uid, gender in MEMBERS.items():
        data = sections()
        stats = onboarding.validate_stats(data['stats'])['stats']
        stats.update(age=30, height_cm=170, profession=onboarding.STAT_OPTIONS['profession'][0],
                     education=onboarding.STAT_OPTIONS['education'][0],
                     marital_history=onboarding.STAT_OPTIONS['marital_history'][0],
                     languages=[onboarding.STAT_OPTIONS['languages'][0]])
        row = onboarding.build_user_row(uid, 'Bangalore', gender, stats, onboarding.build_visions(**data['vision']),
                                        data['activities'], journey_state='dating', bgv_status='verified')
        row['preferences_json'] = db.json_field({'fixed': {'dealbreakers': []}, 'adjustable': {'distance_km': [0, 5000]}})
        db.insert_row(conn, 'User', row)
        # A sign-in account like a real member's (the date-day face simulation is only
        # offered to members with one). Synthetic numbers; no SMS is ever sent.
        db.insert_row(conn, 'Account', {'id': 'acct_' + uid, 'user_id': uid, 'phone': PHONES[uid], 'auth_enabled': 1,
                                        'verified_phone': 1, 'verification_required': 1, 'created_at': 'e2e'})
    conn.commit()
    conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=5055)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='dhashu-e2e-') as tmp:
        db_path = prepare_environment(tmp)
        import db
        db.DEFAULT_DB_PATH = db_path
        real_get_connection = db.get_connection
        db.get_connection = lambda *a, **k: real_get_connection(db_path)
        seed(db_path)
        from unittest import mock
        mock.patch('dateplan.verify_face', return_value=True).start()
        import app as member_app
        member_app.SIM_STATE_PATH = Path(tmp) / 'sim_state.json'
        member_app.set_clock(member_app.clock_module.SimulationClock.at(1, 'Mon', 12))
        import ceremony, chemistry, guru_dating
        from flask import jsonify

        def e2e_constants():
            # Test server only: the values a scripted journey must send (never in the real app).
            return jsonify(acks={k: list(ceremony.ack_keys(k)) for k in (ceremony.DATE_AGREEMENT, ceremony.RELATIONSHIP_ENTRY, ceremony.STAGE_GATE)},
                           kinds={'date': ceremony.DATE_AGREEMENT, 'relationship_entry': ceremony.RELATIONSHIP_ENTRY, 'stage_gate': ceremony.STAGE_GATE},
                           green_flags=list(guru_dating.GREEN_FLAGS[:2]),
                           chemistry_keys=[*chemistry.MANDATORY_KEYS, *chemistry.INTIMACY_MANDATORY_KEYS])
        member_app.app.add_url_rule('/__e2e/constants', 'e2e_constants', e2e_constants)
        from waitress import serve
        print(f'E2E backend on http://127.0.0.1:{args.port} (temporary SQLite, seeded {", ".join(MEMBERS)})', flush=True)
        serve(member_app.app, host='127.0.0.1', port=args.port, threads=4, _quiet=True)


if __name__ == '__main__':
    main()
