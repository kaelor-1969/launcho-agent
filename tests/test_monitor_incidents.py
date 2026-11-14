import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import monitor_availability as m
from test_monitor_availability import config


class IncidentTests(unittest.TestCase):
    def test_transient_persistent_recovery_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            c = config(state_file=str(Path(folder) / 'state.json'))
            s = m.State(c)
            good, bad = m.result(True, 'ok'), m.result(False, 'timeout')
            events = []
            # transient failure clears; three consecutive failures open once;
            # single healthy sample cannot recover; two successive samples do.
            sequence = [bad, good, bad, bad, bad, bad, good, bad, good, good, good]
            for item in sequence:
                event = s.observe('live', item)
                if event:
                    events.append(event)
                s.save()
                s = m.State(c)  # restart after EVERY observation
            self.assertEqual(events, ['outage', 'recovery'])
            self.assertFalse(s.data['checks']['live']['down'])

    def test_target_change_and_corrupt_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            c = config(state_file=str(Path(folder) / 'state.json'))
            s = m.State(c)
            s.save()
            with self.assertRaises(ValueError):
                m.State(replace(c, host_url='http://127.0.0.1:9000/'))
            Path(c.state_file).write_text('{invalid', encoding='utf-8')
            with self.assertRaises(ValueError):
                m.State(c)

    def test_widget_incident_is_independent_and_delivery_failure_does_not_replay(self):
        async def scenario(c):
            state = m.State(c)
            sender = AsyncMock()
            sender.send.return_value = False
            widget = AsyncMock(return_value=m.result(False, 'ui_shell_timeout'))
            health = AsyncMock(return_value=m.result(True, 'ok'))
            with patch.object(m, 'probe_health', health), patch.object(m, 'emit'):
                for _ in range(5):
                    await m.cycle(c, state, sender, widget)
                    state = m.State(c)
                self.assertEqual(sender.send.await_count, 1)
                payload = sender.send.call_args.args[0]
                self.assertEqual(payload['check'], 'widget')
                self.assertEqual(payload['type'], 'outage')
                self.assertTrue(payload['checks']['live']['ok'])
                self.assertEqual(payload['code'], 'ui_shell_timeout')
                self.assertIn('time', payload)
                widget.return_value = m.result(True, 'ok')
                for _ in range(3):
                    await m.cycle(c, state, sender, widget)
                self.assertEqual(sender.send.await_count, 2)
                self.assertEqual(sender.send.call_args.args[0]['type'], 'recovery')
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(scenario(config(state_file=str(Path(folder) / 'state.json'))))

    def test_exclusive_lock_rejects_second_instance(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as folder:
            c = config(state_file=str(Path(folder) / 'state.json'))
            cfg = Path(folder) / 'config.json'
            cfg.write_text(json.dumps(c.__dict__), encoding='utf-8')
            Path(c.state_file + '.lock').write_text('owned test lock', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                asyncio.run(m.run(Namespace(config=str(cfg), send=False, test_alert=False, once=True)))
            self.assertEqual(Path(c.state_file + '.lock').read_text(), 'owned test lock')

    def test_persistence_failure_prevents_delivery(self):
        async def scenario(c):
            s = m.State(c)
            sender = AsyncMock()
            with patch.object(m, 'probe_health', AsyncMock(return_value=m.result(False, 'timeout'))), \
                    patch.object(m, 'emit'), patch.object(m.os, 'replace', side_effect=OSError):
                with self.assertRaises(OSError):
                    await m.cycle(c, s, sender, AsyncMock(return_value=m.result(True, 'ok')))
            sender.send.assert_not_awaited()
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(scenario(config(state_file=str(Path(folder) / 'state.json'), failure_threshold=1)))


if __name__ == '__main__':
    unittest.main()
