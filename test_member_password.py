from test_auth import AuthenticationTests
import auth_sessions as sessions
import db
from unittest import mock

class MemberPasswordTests(AuthenticationTests):
    def set_password(self,password='TwelveChars!'):
        tokens=self.login_mobile()
        response=self.post('password/set',{'password':password},headers=self.bearer(tokens))
        self.assertEqual(response.status_code,200,response.json)
        return tokens,response.json['data']

    def test_twelve_character_minimum_and_phone_login(self):
        tokens=self.login_mobile()
        self.assertEqual(self.post('password/set',{'password':'elevenchars'},headers=self.bearer(tokens)).status_code,400)
        r=self.post('password/set',{'password':'TwelveChars!'},headers=self.bearer(tokens))
        self.assertEqual(r.status_code,200,r.json)
        self.start.reset_mock();self.check.reset_mock()
        r=self.post('password/login',{'identifier':'+919876543210','password':'TwelveChars!'})
        self.assertEqual(r.status_code,200,r.json)
        self.start.assert_not_called();self.check.assert_not_called()
        self.assertEqual(self.client.get('/api/v1/me',headers=self.bearer(tokens)).status_code,401)
        self.assertNotIn('TwelveChars!',db.fetch_one(self.conn,'Account',user_id='owner')['password_hash'])
        self.assertEqual(self.post('password/set',{'password':'AnotherPass!'},headers=self.bearer(r.json['data'])).status_code,403)

    def test_email_authentication_and_enrollment_removed(self):
        _,tokens=self.set_password()
        self.conn.execute('UPDATE Account SET verified_email=1 WHERE user_id=?',('owner',));self.conn.commit()
        self.start.reset_mock()
        self.assertEqual(self.post('password/login',{'identifier':'owner@example.test','password':'TwelveChars!'}).status_code,400)
        self.assertEqual(self.post('request',{'channel':'email','destination':'owner@example.test'}).status_code,400)
        self.assertEqual(self.post('email/request',{'email':'new@example.test','password':'TwelveChars!'},headers=self.bearer(tokens)).status_code,404)
        self.start.assert_not_called()

    def test_reset_phone_only_revokes_old_sessions_even_with_stored_email(self):
        _,old=self.set_password()
        self.conn.execute('UPDATE Account SET verified_email=1 WHERE user_id=?',('owner',));self.conn.commit()
        self.conn.execute('DELETE FROM AuthThrottle');self.conn.commit()
        proof=self.login_mobile()
        self.assertEqual(self.post('password/set',{'password':'NewPassword!'},headers=self.bearer(proof)).status_code,200)
        self.assertEqual(self.client.get('/api/v1/me',headers=self.bearer(old)).status_code,401)
        self.assertEqual(self.post('password/login',{'identifier':'+919876543210','password':'TwelveChars!'}).status_code,400)
        self.assertEqual(self.post('password/login',{'identifier':'+919876543210','password':'NewPassword!'}).status_code,200)

    def test_testers_expiry_and_disabled_accounts(self):
        t=sessions.issue(self.conn,'owner')
        self.assertEqual(self.post('password/set',{'password':'TwelveChars!'},headers=self.bearer(t)).status_code,403)
        proof=self.login_mobile()
        self.conn.execute('UPDATE PasswordGrant SET expires_at=0');self.conn.commit()
        self.assertEqual(self.post('password/set',{'password':'TwelveChars!'},headers=self.bearer(proof)).status_code,403)
        self.conn.execute('UPDATE Account SET auth_enabled=0 WHERE user_id=?',('owner',));self.conn.commit()
        self.assertEqual(self.post('password/login',{'identifier':'+919876543210','password':'TwelveChars!'}).status_code,400)

    def test_password_login_throttled(self):
        for _ in range(11):r=self.post('password/login',{'identifier':'+15550000000','password':'bad'})
        self.assertEqual(r.status_code,429)
