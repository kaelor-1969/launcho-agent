"""Real CLI and loopback receiver; synthetic config, no app or database imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_monitor_availability import config
from test_monitor_delivery import webhook


ROOT = Path(__file__).resolve().parents[1]


class MonitorCliTests(unittest.TestCase):
    def run_cli(self, folder, url, *flags):
        state = Path(folder) / 'monitor.json'
        cfg = Path(folder) / 'config.json'
        cfg.write_text(json.dumps(config(state_file=str(state), timeout=2).__dict__), encoding='utf-8')
        # Exclude inherited application credentials, DB paths and webhook secrets.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('LAUNCHO_', 'AI_', 'PYTHON'))}
        env.update(PYTHONUTF8='1', LAUNCHO_MONITOR_WEBHOOK=url,
                   LAUNCHO_MONITOR_WEBHOOK_TOKEN='synthetic-cli-token')
        completed = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/monitor_availability.py'),
             '--config', str(cfg), '--test-alert', *flags],
            cwd=ROOT, env=env, capture_output=True, encoding='utf-8', timeout=20,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(completed.stderr, '')
        self.assertNotIn(url, completed.stdout)
        self.assertNotIn('synthetic-cli-token', completed.stdout)
        self.assertFalse(state.exists(), 'channel test must not create incident state')
        self.assertFalse(Path(str(state) + '.lock').exists())
        return completed, [json.loads(line) for line in completed.stdout.splitlines()]

    def test_default_dry_run_makes_no_request(self):
        with tempfile.TemporaryDirectory() as folder, webhook() as (url, calls):
            completed, logs = self.run_cli(folder, url)
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(calls, [])
            self.assertEqual([item['event'] for item in logs], ['alert_dry_run'])
            self.assertTrue(logs[0]['payload']['test'])

    def test_send_one_labelled_test_and_release_lock(self):
        with tempfile.TemporaryDirectory() as folder, webhook() as (url, calls):
            completed, logs = self.run_cli(folder, url, '--send')
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(len(calls), 1)
            payload = calls[0]['payload']
            self.assertEqual((payload['type'], payload['check'], payload['label']),
                             ('test', 'channel', 'local-example'))
            self.assertIs(payload['test'], True)
            self.assertEqual(calls[0]['authorization'], 'Bearer synthetic-cli-token')
            self.assertEqual(logs[0]['event'], 'alert_delivered')
            self.assertEqual(logs[0]['event_id'], payload['id'])

    def test_failed_receiver_has_bounded_retries_and_failure_exit(self):
        with tempfile.TemporaryDirectory() as folder, webhook((503,)) as (url, calls):
            completed, logs = self.run_cli(folder, url, '--send')
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]['payload'], calls[1]['payload'])
            self.assertEqual(logs[0]['event'], 'alert_delivery_failed')
            self.assertEqual(logs[0]['attempts'], 2)

    def test_invalid_destination_exits_without_network_or_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            completed, logs = self.run_cli(folder, 'invalid-synthetic-destination', '--send')
            self.assertEqual(completed.returncode, 2)
            self.assertEqual([item['event'] for item in logs], ['monitor_error'])


if __name__ == '__main__':
    unittest.main()
