"""A blocked avatar provider must not prevent a Court/FIR worker iteration."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import TestCase
from unittest.mock import MagicMock,patch
import bgv_worker as worker

class ParallelAvatarTests(TestCase):
    def test_legal_checks_continue_with_independent_connection_during_generation(self):
        started=Event();release=Event();connections=[]
        def connection():
            conn=MagicMock();connections.append(conn);return conn
        def generate(conn):
            started.set()
            if not release.wait(3):raise AssertionError('Test did not release provider')
            return True
        with patch.object(worker.db,'get_connection',side_effect=connection),patch.object(worker.avatar_service,'work_one',side_effect=generate),patch.object(worker.face_image_lease,'purge'),patch.object(worker.bgv_bundle,'schedule'),patch.object(worker.liveness_secure_service,'work_one',return_value=False),patch.object(worker.face_match_service,'work_one',return_value=False),patch.object(worker.bgv_app,'work_one',return_value=True) as legal:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(worker.avatar_step)
                try:
                    self.assertTrue(started.wait(1))
                    self.assertTrue(worker.bgv_step())
                    self.assertFalse(future.done())
                    self.assertEqual(legal.call_count,1)
                    self.assertIsNot(connections[0],connections[1])
                finally:release.set()
                self.assertTrue(future.result(timeout=2))
        for conn in connections:conn.close.assert_called_once()
