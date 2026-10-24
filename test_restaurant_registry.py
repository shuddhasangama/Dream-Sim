import copy
import unittest
from unittest.mock import patch
from api_contract import ApiError
from restaurant_models import SearchRequest, normalize_quote
from restaurant_registry import Router, CAPABILITIES, ADAPTERS, rank, readiness
from restaurant_provider import SimulatedProvider


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.request={'id':'IN-BLR','country':'IN','city':'Bengaluru','currency':'INR','currency_exponent':2,
          'timezone':'Asia/Kolkata','date_time':'2026-11-01T19:30:00+05:30','party_size':2,
          'neighbourhoods':[{'id':'area','name':'Area','lat':12.97,'lon':77.64}],
          'cuisines':['Thai'],'dietary_requirements':['Vegetarian'],
          'budget_per_person_minor':{'min':0,'max':100000},'simulation':True,'user_id':'private','token':'secret'}
        self.raw=SimulatedProvider().search(self.request,1)[0]
        self.settings={'selection_policy':'lowest_total','providers':[
          {'id':'a','label':'A','adapter':'a','enabled':True,'markets':['IN-BLR'],'priority':1},
          {'id':'b','label':'B','adapter':'b','enabled':True,'markets':['IN-BLR'],'priority':2}]}

    def spec(self,cls):
        return {'factory':cls,'simulation':True,'capabilities':CAPABILITIES|{'deposits','refunds','food_credit'}}

    def test_minimum_outbound_data_and_strict_quote_allowlist(self):
        req=SearchRequest.from_snapshot(self.request)
        self.assertNotIn('user_id',req.provider_input())
        self.assertNotIn('token',req.provider_input())
        q=normalize_quote({**self.raw,'secret':'provider token'},req,'a','A','a')
        self.assertNotIn('secret',q)
        self.assertEqual(q['upfront_minor'],50000)
        self.assertEqual(q['estimated_total_minor'],100000) # credit is not counted twice
        prepaid=normalize_quote({**self.raw,'deposit_minor':200000,'food_credit_minor':200000},req,'a','A','a')
        self.assertEqual(prepaid['estimated_total_minor'],200000) # do not assume an unused-credit refund
        for field,value in [('deposit_minor',-1),('booking_fee_minor',None),('lat',float('nan')),('currency','USD')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                normalize_quote({**self.raw,field:value},req,'a','A','a')

    def test_cost_policy_and_verified_cross_provider_deduplication(self):
        req=SearchRequest.from_snapshot(self.request)
        a=normalize_quote(self.raw,req,'a','A','a')|{'distance_km':0.5,'canonical_venue_id':'same-place'}
        b=normalize_quote({**self.raw,'booking_fee_minor':5000},req,'b','B','b')|{'distance_km':0.2,'canonical_venue_id':'same-place'}
        self.assertEqual(Router(self.settings).shortlist([b,a])[0]['provider_id'],'a')
        nearest=copy.deepcopy(self.settings); nearest['selection_policy']='nearest'
        self.assertEqual(Router(nearest).shortlist([a,b])[0]['provider_id'],'b')
        self.assertEqual(len(Router(self.settings).shortlist([a,b])),1)

    def test_partial_outage_and_capability_filtering(self):
        class Broken(SimulatedProvider):
            def search(self,*a): raise TimeoutError('secret must not leak')
        with patch.dict(ADAPTERS,{'a':self.spec(SimulatedProvider),'b':self.spec(Broken)}):
            router=Router(self.settings)
            results=router.search(self.request,1)
            self.assertEqual(len(results),1)
            self.assertEqual(router.failures,{'b':'search_unavailable'})
            self.assertEqual(results[0]['provider_id'],'a')
        spec=self.spec(SimulatedProvider); spec['capabilities']=frozenset({'search'})
        with patch.dict(ADAPTERS,{'a':spec}):
            self.assertEqual(Router(self.settings).search(self.request,1),[])

    def test_provider_is_pinned_after_selection_and_kill_switch_preserves_cancel(self):
        req=SearchRequest.from_snapshot(self.request)
        q=normalize_quote(self.raw,req,'a','A','a')
        with patch.dict(ADAPTERS,{'a':self.spec(SimulatedProvider),'b':self.spec(SimulatedProvider)}):
            settings=copy.deepcopy(self.settings); settings['providers'][0]['enabled']=False
            router=Router(settings)
            with self.assertRaises(ApiError): router.reserve(q,'attempt')
            self.assertEqual(router.status('attempt',q)['status'],'confirmed')
            self.assertEqual(router.cancel('reference',q)['status'],'cancelled')
            settings['providers'][0]['adapter']='b'
            with self.assertRaises(ApiError): Router(settings).status('attempt',q)

    def test_unimplemented_vendor_cannot_be_enabled_by_configuration(self):
        settings={'selection_policy':'lowest_total','providers':[
          {'id':'district','label':'District','adapter':None,'enabled':True,'markets':['IN-BLR'],'priority':1}]}
        router=Router(settings)
        self.assertEqual(router.search(self.request,1),[])
        self.assertEqual(readiness(settings)[0]['reason'],'adapter_required')

    def test_wrong_city_and_non_simulation_adapters_are_not_called(self):
        class Forbidden:
            def __init__(self): raise AssertionError('must not construct adapter')
        settings=copy.deepcopy(self.settings)
        settings['providers'][0]['markets']=['ES-MAD']
        with patch.dict(ADAPTERS,{'a':self.spec(Forbidden),'b':{**self.spec(Forbidden),'simulation':False}}):
            self.assertEqual(Router(settings).search(self.request,1),[])

    def test_explicit_adapter_mapping_omits_unneeded_fields(self):
        from restaurant_mapping import FieldMapper
        mapper=FieldMapper({'location.latitude':'neighbourhoods.0.lat','guests':'party_size','optional':'missing'},
                           {'id':'data.venue','available':'data.available'},('guests',),('id','available'))
        output=mapper.request(SearchRequest.from_snapshot(self.request).provider_input())
        self.assertEqual(output,{'location':{'latitude':12.97},'guests':2})
        self.assertEqual(mapper.response({'data':{'venue':'v1','available':False},'token':'secret'}),{'id':'v1','available':False})
        with self.assertRaises(ValueError): mapper.response({'data':{'venue':'v1'}})

    def test_legacy_invalid_search_data_has_actionable_error(self):
        request={**self.request,'date_time':'not-a-date'}
        with self.assertRaises(ApiError) as result:
            Router(self.settings).search(request,1)
        self.assertEqual(result.exception.status,409)
