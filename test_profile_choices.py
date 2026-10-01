import base64
import io
import json
from PIL import Image
import db
import profile_choices as choices
from test_week_api import WeekApiTests

class ProfileChoicesTests(WeekApiTests):
    def personal(self,**kw):
        return dict(categories=[],share_health=False,note='',openness='any',open_categories=[],include_undisclosed=True,ethnicity=[],**kw)

    def test_templates_persist_real_pillars_and_explicit_children(self):
        for key in ('grow','two','explore'):
            r=self.request('/profile/vision/template',method='PUT',body={'template':key})
            self.assertEqual(r.status_code,200,r.json)
            row=db.fetch_one(self.conn,'User',id='owner'); stats=json.loads(row['stats_json'])
            self.assertEqual(stats['vision_template'],key)
            goals={g['key'] for g in json.loads(row['vision_json'])}
            self.assertEqual('Kids' in goals,key=='grow')
        self.match('owner','partner');self.set_clock(day='Mon',hour=12)
        r=self.request('/profile/vision/template',method='PUT',body={'template':'two'})
        self.assertEqual(r.status_code,409,r.json)

    def test_health_consent_withdrawal_private_preferences_and_validation(self):
        body=self.personal();body.update(categories=['diabetes'],note='Ask me about it')
        self.assertEqual(self.request('/profile/personal',method='PUT',body=body).status_code,400)
        body['share_health']=True
        r=self.request('/profile/personal',method='PUT',body=body)
        self.assertEqual(r.status_code,200,r.json)
        from generate_users import from_user_row
        u=from_user_row(db.fetch_one(self.conn,'User',id='owner'))
        shown=choices.public_profile(self.conn,u)
        self.assertEqual(shown['health']['categories'],['diabetes'])
        self.assertNotIn('openness',shown)
        self.assertFalse(self.request('/profile/personal',uid='partner').json['data']['health'])
        r=self.request('/profile/personal',method='PUT',body=self.personal())
        self.assertEqual(r.status_code,200,r.json)
        u=from_user_row(db.fetch_one(self.conn,'User',id='owner'))
        self.assertIsNone(choices.public_profile(self.conn,u)['health'])
        body=self.personal();body['ethnicity']=['invalid']
        self.assertEqual(self.request('/profile/personal',method='PUT',body=body).status_code,400)

    def test_photo_sanitized_owned_and_removable(self):
        out=io.BytesIO();Image.new('RGB',(800,800),'red').save(out,'PNG')
        encoded='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
        r=self.request('/profile/photo',method='PUT',body={'photo':encoded})
        self.assertEqual(r.status_code,200,r.json)
        data=r.json['data']['photo'];img=Image.open(io.BytesIO(base64.b64decode(data.split(',')[1])))
        self.assertEqual(img.size,(480,600));self.assertFalse(img.getexif())
        self.assertIsNone(self.request('/profile/personal',uid='partner').json['data']['photo'])
        self.assertEqual(self.request('/profile/photo',method='PUT',body={'photo':'data:text/html;base64,AAA'}).status_code,400)
        self.assertEqual(self.request('/profile/photo',method='PUT',body={'photo':None}).status_code,200)
        self.assertIsNone(db.fetch_one(self.conn,'ProfilePhoto',id='owner'))

    def test_health_matching_unknown_and_multiple_conditions(self):
        a={'preferences':{'health_openness':{'mode':'specific','categories':['diabetes'],'include_undisclosed':False}}}
        b={'stats':{}}
        self.assertFalse(choices.health_fits(a,b))
        b['stats']['health_shared']={'consent':True,'categories':['diabetes']}
        self.assertTrue(choices.health_fits(a,b))
        b['stats']['health_shared']['categories'].append('mobility')
        self.assertFalse(choices.health_fits(a,b))
        b['stats']['health_shared']['consent']=False
        a['preferences']['health_openness']['include_undisclosed']=True
        self.assertTrue(choices.health_fits(a,b))

    def test_children_intention_and_ethnicity_cap(self):
        import matching
        a={'stats':{'kids_intent':'no'},'visions':[{'key':'Intimacy','stance':['Emotional']}]}
        b={'stats':{},'visions':[{'key':'Intimacy','stance':['Emotional']},{'key':'Kids','stance':['Naturally']}]}
        self.assertFalse(matching.visions_compatible(a,b))
        a['stats']['kids_intent']='undecided'
        self.assertTrue(matching.visions_compatible(a,b))
        opts=self.request('/profile/personal').json['data']['ethnicity_options']
        body=self.personal();body['ethnicity']=opts[:2]
        self.assertEqual(self.request('/profile/personal',method='PUT',body=body).status_code,200)
        body['ethnicity']=opts[:3]
        self.assertEqual(self.request('/profile/personal',method='PUT',body=body).status_code,400)
