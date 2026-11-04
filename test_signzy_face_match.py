import unittest
from signzy import face_match

class FaceMatchTests(unittest.TestCase):
 def payload(self,**extra):return {'firstImage':'https://images.example/selfie.jpg','secondImage':'https://images.example/aadhaar.jpg','threshold':.7,**extra}
 def test_contract(self):
  self.assertEqual(face_match.PATH,'/face/match');self.assertEqual(face_match.payload(self.payload()),self.payload())
  for value in (True,.04,.96,float('nan'),'0.7'):
   with self.assertRaises(ValueError):face_match.payload(self.payload(threshold=value))
 def test_urls_and_mask_scope(self):
  for value in ('http://images.example/a.jpg','data:image/jpeg;base64,test','https://user:pass@images.example/a.jpg'):
   with self.assertRaises(ValueError):face_match.payload(self.payload(firstImage=value))
  with self.assertRaises(ValueError):face_match.payload(self.payload(detectMask=['https://images.example/other.jpg']))
 def test_outcomes_are_not_liveness(self):
  for verified in (True,False):
   s=face_match.summarize(200,{'status':200,'result':{'verified':verified,'matchPercentage':'99.00%','maskDetections':[]}})
   self.assertEqual(s['face_match_passed'],verified);self.assertFalse(s['liveness_checked']);self.assertFalse(s['automatic_verification'])
  self.assertIsNone(face_match.summarize(200,{'status':200,'result':{'verified':True}})['face_match_passed'])
 def test_response_never_exposes_echoed_images(self):
  s=face_match.summarize(403,{'result':{'firstImage':'PRIVATE'}});self.assertNotIn('PRIVATE',str(s));self.assertIsNone(s['face_match_passed'])
