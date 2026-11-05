"""Run the fresh-account API flow against an isolated local PostgreSQL schema."""
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
import db,auth_delivery
from test_segment_efg_routes import app_module
from test_auth_postgres import PostgresAuthenticationTests as PgBase
from test_self_signup import SelfSignupTests as Flows

@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'),'No isolated PostgreSQL configured')
class FreshSignupPostgresTests(unittest.TestCase):
    connect=PgBase.connect
    cleanup=PgBase.cleanup
    signup=Flows.signup
    stats=Flows.stats
    test_no_account_until_approved_otp_and_contact_resume_not_duplicate=Flows.test_no_account_until_approved_otp_and_contact_resume_not_duplicate
    test_three_cities_only_auto_plan_and_saved_resume=Flows.test_three_cities_only_auto_plan_and_saved_resume
    test_optional_claims_health_consent_and_religion_cap=Flows.test_optional_claims_health_consent_and_religion_cap
    test_matching_admission_requires_current_bound_evidence_not_otp_or_claims=Flows.test_matching_admission_requires_current_bound_evidence_not_otp_or_claims
    def setUp(self):
        PgBase.setUp(self)
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        for p in [patch.object(db,'get_connection',lambda *a,**kw:self.connect()),patch.object(app_module,'SIM_STATE_PATH',Path(temp.name)/'clock.json'),patch.dict(app_module.app.config,{'AUTH_ENABLED':True}),patch.dict(os.environ,{'SIGNZY_ENV':'preproduction','DHASHU_BILLING_MODE':'disabled','SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DHASHU_SIMULATED_CLOCK':'true','PAYMENTS_ENABLED':'0'}),patch.object(auth_delivery,'configured',return_value=True),patch.object(auth_delivery,'start',side_effect=lambda *args:'VE'+uuid.uuid4().hex),patch.object(auth_delivery,'check',return_value=True)]:
            p.start();self.addCleanup(p.stop)
        self.client=app_module.app.test_client()
