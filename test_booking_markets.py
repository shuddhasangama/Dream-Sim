import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import booking_markets


class MarketTests(unittest.TestCase):
    def test_city_alias_and_future_country_configuration(self):
        market = booking_markets.for_city('Bangalore')
        self.assertEqual(market['id'], 'IN-BLR')
        future = copy.deepcopy(market)
        future.update(id='ES-MAD', country='ES', city='Madrid', aliases=[], currency='EUR', timezone='Europe/Madrid')
        future['budget_ranges_minor'] = {'EUR 20–40': {'min': 2000, 'max': 4000}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'markets.json'
            path.write_text(json.dumps([market, future]), encoding='utf-8')
            with mock.patch.dict(os.environ, {'DHASHU_BOOKING_MARKETS_FILE':str(path)}):
                self.assertEqual(booking_markets.for_city('Madrid', 'ES')['currency'], 'EUR')
                import date_alignment
                with mock.patch.dict(os.environ, {'DHASHU_BOOKING_COORDINATION_ENABLED':'1'}):
                    self.assertEqual(date_alignment.options_for('budget', 'Madrid'), ['EUR 20–40'])
                self.assertIsNone(booking_markets.for_city('Madrid', 'IN'))
                future['neighbourhoods'][0]['lat'] = 999
                path.write_text(json.dumps([future]), encoding='utf-8')
                with self.assertRaises(ValueError):
                    booking_markets.markets()
