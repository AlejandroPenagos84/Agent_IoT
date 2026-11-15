import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path

from app.background import AgentRunner, RetentionLoop


class FakeServer:
    def __init__(self):
        self.started = threading.Event()
        self.stopped = False

    def start(self):
        self.started.set()

    def stop(self):
        self.stopped = True


class AgentRunnerTests(unittest.TestCase):
    def test_waits_for_certificates_before_building(self):
        with tempfile.TemporaryDirectory() as tmp:
            cert = Path(tmp) / 'server.crt'
            server = FakeServer()
            built = []
            runner = AgentRunner(
                lambda: built.append(1) or server, wait_for=(str(cert),), poll_seconds=0.05
            )
            runner.start()
            time.sleep(0.2)
            self.assertEqual(built, [])
            cert.write_text('x')
            self.assertTrue(server.started.wait(2))
            self.assertTrue(runner.running)
            runner.stop()
            self.assertTrue(server.stopped)

    def test_stop_while_waiting_never_builds(self):
        built = []
        runner = AgentRunner(lambda: built.append(1), wait_for=('/no/existe',), poll_seconds=0.05)
        runner.start()
        runner.stop()
        self.assertEqual(built, [])
        self.assertFalse(runner.running)

    def test_build_error_keeps_process_alive(self):
        def boom():
            raise ValueError('modelo inválido')

        runner = AgentRunner(boom)
        runner.start()
        runner.stop()
        self.assertFalse(runner.running)


class RetentionLoopTests(unittest.TestCase):
    def test_prunes_old_evidence_and_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'evidence' / '2000-01-01').mkdir(parents=True)
            (root / 'evidence' / date.today().isoformat()).mkdir()
            (root / 'alerts').mkdir()
            (root / 'alerts' / '2000-01-01.jsonl').write_text('{}\n')
            loop = RetentionLoop(root / 'evidence', 30, root / 'alerts', 30)
            self.assertEqual(loop.run_once(), (1, 1))
            self.assertEqual(len(list((root / 'evidence').iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
