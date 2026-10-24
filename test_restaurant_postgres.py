"""Double-submission tests using an isolated local PostgreSQL database."""
import os
import unittest
from unittest import mock
import db
import planning_service
import restaurant_service
import test_booking_postgres
from api_contract import ApiError


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL configured')
class RestaurantPostgresTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_booking_postgres.BookingPostgresTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        flag=mock.patch.dict(os.environ,{'DHASHU_RESTAURANT_MODE':'simulation','DHASHU_RESTAURANT_SCENARIO':'success'})
        flag.start()
        self.addCleanup(flag.stop)
        self.conn=self.fixture.conn
        self.pid=planning_service.confirm(self.conn,'owner','pair','Sat','dinner',lambda *a:'2026-10-24T19:30')['id']
        self.conn.execute('UPDATE "DatePlan" SET status=%s WHERE id=%s',('confirmed',self.pid))

    def test_concurrent_payment_and_refund_have_one_winner(self):
        def act(uid,action,**kw):
            revision=restaurant_service.view(self.conn,uid,self.pid)['revision']
            return restaurant_service.act(self.conn,uid,self.pid,{'action':action,'revision':revision,**kw})
        q=act('owner','search')['options'][0]['quote_id']
        act('owner','approve',quote_id=q)
        state=act('partner','approve',quote_id=q)
        def race(action,revision):
            def change(conn,uid):
                try:
                    return restaurant_service.act(conn,uid,self.pid,{'action':action,'revision':revision})['state']
                except ApiError as exc:
                    return exc.code
            return self.fixture.parallel(change)
        self.assertCountEqual(race('pay',state['revision']),['confirmed','state_conflict'])
        state=restaurant_service.view(self.conn,'owner',self.pid)
        self.assertCountEqual(race('cancel',state['revision']),['cancelled','state_conflict'])
        self.assertEqual(len(db.fetch_all(self.conn,'RestaurantBooking')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'RestaurantEvent')),5)
