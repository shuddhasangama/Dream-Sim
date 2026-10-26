import unittest
from identity_verification import Request, SignzySmart, Simulator


class ContractTests(unittest.TestCase):
    def test_request_mapping(self):
        payload=SignzySmart.payload(Request('https://example.invalid/a?secret=x','https://example.invalid/b'))
        self.assertEqual(set(payload),{'livenessImage','faceMatchImage','livenessStrictMode','faceMatchThreshold'})
        self.assertTrue(payload['livenessStrictMode'])

    def test_supplied_successful_request_with_mismatch_is_not_approved(self):
        r=SignzySmart.parse({'code':'S001','reason':'REQUEST_SUCCESSFUL','result':{
            'input':{'livenessImage':'private-url'},'liveness':{'liveness':True},
            'match':{'verified':False,'matchPercentage':'2.00%'}}})
        self.assertEqual(r.state,'review_required')
        self.assertFalse(r.match_passed)
        self.assertNotIn('private-url',str(r))

    def test_both_checks_required_and_malformed_fails_closed(self):
        for a,b in [(True,True),(True,False),(False,True),(False,False),('true',True),(None,True)]:
            r=SignzySmart.parse({'code':'S001','reason':'REQUEST_SUCCESSFUL','result':{
                'liveness':{'liveness':a},'match':{'verified':b}}})
            self.assertEqual(r.state=='passed',a is True and b is True)
        for body in ({},[],None,{'code':'S001','reason':'REQUEST_SUCCESSFUL','result':[]}):
            self.assertNotEqual(SignzySmart.parse(body).state,'passed')

    def test_simulation_and_validation(self):
        req=Request('https://example.invalid/a','https://example.invalid/b')
        self.assertEqual(Simulator('timeout').verify(req).state,'pending')
        self.assertEqual(Simulator('liveness_failed').verify(req).state,'retry_required')
        for url in ['http://example.invalid/a','https://user:password@example.invalid/a']:
            with self.assertRaises(ValueError):
                SignzySmart.payload(Request(url,req.reference_url))
