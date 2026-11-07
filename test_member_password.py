from test_auth import AuthenticationTests
from unittest import mock
import auth_sessions as sessions
import db

class MemberPasswordTests(AuthenticationTests):
    def set_password(self):
        tokens=self.login_mobile()
        response=self.post('password/set',{'password':'a long memorable password'},headers=self.bearer(tokens))
        self.assertEqual(response.status_code,200,response.json)
        return tokens,response.json['data']

    def test_setup_login_reset_revokes_sessions(self):
        old,new=self.set_password()
        self.assertEqual(self.client.get('/api/v1/me',headers=self.bearer(old)).status_code,401)
        response=self.post('password/login',{'identifier':'owner@example.test','password':'a long memorable password'})
        self.assertEqual(response.status_code,200,response.json)
        self.start.reset_mock();self.check.reset_mock()
        self.assertEqual(self.post('password/login',{'identifier':'owner@example.test','password':'wrong'}).status_code,400)
        self.start.assert_not_called();self.check.assert_not_called()
        self.assertNotIn('a long memorable password',db.fetch_one(self.conn,'Account',user_id='owner')['password_hash'])
        self.assertEqual(self.post('password/set',{'password':'another long password'},headers=self.bearer(new)).status_code,403)

    def test_phone_verification_and_tester_cannot_set(self):
        t=sessions.issue(self.conn,'owner')
        self.assertEqual(self.post('password/set',{'password':'a long memorable password'},headers=self.bearer(t)).status_code,403)
        self.set_password()
        self.assertEqual(self.post('password/login',{'identifier':'+919876543210','password':'a long memorable password'}).status_code,400)
        self.conn.execute('UPDATE Account SET verified_phone=1 WHERE user_id=?',('owner',));self.conn.commit()
        self.assertEqual(self.post('password/login',{'identifier':'+919876543210','password':'a long memorable password'}).status_code,200)
        self.conn.execute('UPDATE Account SET auth_enabled=0 WHERE user_id=?',('owner',));self.conn.commit()
        self.assertEqual(self.post('password/login',{'identifier':'owner@example.test','password':'a long memorable password'}).status_code,400)

    def test_expired_grant_short_password_and_throttle(self):
        t=self.login_mobile()
        self.assertEqual(self.post('password/set',{'password':'short'},headers=self.bearer(t)).status_code,400)
        self.conn.execute('UPDATE PasswordGrant SET expires_at=0');self.conn.commit()
        self.assertEqual(self.post('password/set',{'password':'a long memorable password'},headers=self.bearer(t)).status_code,403)
        for _ in range(11):r=self.post('password/login',{'identifier':'missing@example.test','password':'bad'})
        self.assertEqual(r.status_code,429)

    def test_email_enrollment_verified_and_bound_to_session(self):
        _,t=self.set_password()
        with mock.patch.dict('os.environ',{'DHASHU_EMAIL_LOGIN_ENABLED':'1'}):
            r=self.post('email/request',{'email':'new@example.test','password':'a long memorable password'},headers=self.bearer(t))
            self.assertEqual(r.status_code,200,r.json);challenge=r.json['data']['challenge_id']
            other=sessions.issue(self.conn,'other')
            self.assertEqual(self.post('email/verify',{'challenge_id':challenge,'code':'123456'},headers=self.bearer(other)).status_code,400)
            self.assertEqual(self.post('email/verify',{'challenge_id':challenge,'code':'123456'},headers=self.bearer(t)).status_code,200)
            self.assertEqual(self.post('password/login',{'identifier':'new@example.test','password':'a long memorable password'}).status_code,200)
            self.assertEqual(self.post('email/verify',{'challenge_id':challenge,'code':'123456'},headers=self.bearer(t)).status_code,400)
