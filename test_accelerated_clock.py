"""Boundary, restart, multi-pair and production isolation tests."""
from datetime import datetime, timedelta, timezone
from unittest import TestCase, mock
import accelerated_clock as accelerated
import clock

START = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
ENV = {'DHASHU_SIMULATED_CLOCK': 'true', 'DHASHU_ACCELERATED_TEST': 'true',
       'DHASHU_TEST_START_UTC': START.isoformat(), 'DHASHU_TEST_START_WEEK': '38'}


class AcceleratedClockTests(TestCase):
    def setUp(self):
        patch = mock.patch.dict('os.environ', ENV)
        patch.start(); self.addCleanup(patch.stop)

    def read(self, seconds, plans=()):
        return accelerated.read(plans, START + timedelta(seconds=seconds))

    def test_all_boundaries_and_stop(self):
        expected = [('Mon',10),('Mon',12),('Tue',12),('Wed',12),('Wed',18),
                    ('Thu',12),('Thu',18),('Thu',18),('Thu',18),('Sun',21),('Mon',12)]
        for index, (day,hour) in enumerate(expected):
            with self.subTest(index=index):
                current = self.read(index*180)
                self.assertEqual(current, clock.SimulationClock.at(38 + (index==10), day, hour))
                if index: self.assertLessEqual(self.read(index*180-1), current)
        self.assertEqual(self.read(-10), self.read(0))
        self.assertEqual(self.read(999999), self.read(1800))

    def test_latest_pair_date_rounding_and_debrief(self):
        plans = [{'datetime':'2026-09-25T09:00:00'}, {'datetime':'2026-09-27T19:30:00'}]
        self.assertEqual(self.read(21*60, plans), clock.SimulationClock.at(38,'Sun',20))
        self.assertEqual(self.read(24*60, plans), clock.SimulationClock.at(38,'Sun',21))
        # Order/status changes and process restarts cannot change the time.
        self.assertEqual(self.read(24*60, list(reversed(plans))), self.read(24*60, plans))
        self.assertEqual(self.read(21*60, [{'datetime':'2026-09-25T09:00'}]), clock.SimulationClock.at(38,'Fri',9))

    def test_does_not_use_other_weeks(self):
        self.assertEqual(self.read(21*60, [{'datetime':'2026-09-18T19:30'}]), clock.SimulationClock.at(38,'Thu',18))

    def test_flags_fail_closed_in_real_time_mode(self):
        self.assertTrue(accelerated.enabled())
        with mock.patch.dict('os.environ', {'DHASHU_SIMULATED_CLOCK':'false'}):
            self.assertFalse(accelerated.enabled())
            self.assertIsNone(accelerated.metadata())

    def test_invalid_start_is_not_silently_restarted(self):
        for value in ('bad', '2026-09-22T12:00:00'):
            with mock.patch.dict('os.environ', {'DHASHU_TEST_START_UTC':value}):
                with self.assertRaises(ValueError): accelerated.read()

    def test_metadata_countdown_and_completion(self):
        self.assertEqual(accelerated.metadata(START)['next_jump_in_seconds'],180)
        self.assertEqual(accelerated.metadata(START-timedelta(seconds=60))['starts_in_seconds'],60)
        self.assertTrue(accelerated.metadata(START+timedelta(minutes=30))['finished'])
