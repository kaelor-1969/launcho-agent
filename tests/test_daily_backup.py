import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from scripts import daily_backup as backup


class BackupTests(unittest.TestCase):
    def test_failure_phases_are_redacted_and_nonzero(self):
        for phase in ('open', 'backup', 'integrity_check', 'foreign_key_check', 'restore', 'restore_check', 'replace'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as root:
                origin, target, restored = Mock(), Mock(), Mock()
                target.execute.return_value.fetchall.return_value = [('ok',)]
                target.execute.return_value.fetchone.return_value = None
                restored.execute.return_value.fetchall.return_value = [('ok',)]
                restored.execute.return_value.fetchone.return_value = None
                error = RuntimeError('SECRET DB CONTENT /private/token')
                connects = [origin, target, restored]
                if phase == 'open':
                    connects = [error]
                elif phase == 'backup':
                    origin.backup.side_effect = error
                elif phase == 'integrity_check':
                    target.execute.return_value.fetchall.side_effect = error
                elif phase == 'foreign_key_check':
                    target.execute.return_value.fetchone.side_effect = error
                elif phase == 'restore':
                    target.backup.side_effect = error
                elif phase == 'restore_check':
                    restored.execute.side_effect = error
                output = io.StringIO()
                with patch.object(backup.sqlite3, 'connect', side_effect=connects), \
                        patch.object(backup.os, 'replace', side_effect=error if phase == 'replace' else None), \
                        patch.object(backup, 'alert') as alert, contextlib.redirect_stderr(output):
                    self.assertEqual(backup.main(Path(root) / 'source', Path(root) / 'backups'), 1)
                record = json.loads(output.getvalue())
                self.assertEqual(record['phase'], phase)
                self.assertNotIn('SECRET', output.getvalue())
                self.assertNotIn('/private', output.getvalue())
                self.assertEqual(set(alert.call_args.args[0]), {'status', 'phase', 'timestamp'})
                self.assertEqual(list((Path(root) / 'backups').iterdir()), [])

    def test_fourteen_days_across_week_and_dst_boundaries(self):
        # UTC slots are unaffected by the March and October DST transitions.
        for start in (datetime(2026, 3, 23, 2, 17, tzinfo=timezone.utc),
                      datetime(2026, 10, 19, 2, 17, tzinfo=timezone.utc)):
            with tempfile.TemporaryDirectory() as root:
                source = Path(root) / 'source.sqlite3'
                directory = Path(root) / 'backups'
                expected = {}
                with contextlib.closing(sqlite3.connect(source)) as connection, connection:
                    connection.execute('CREATE TABLE marker (day INTEGER)')
                for day in range(14):
                    now = start + timedelta(days=day)
                    with contextlib.closing(sqlite3.connect(source)) as connection, connection:
                        connection.execute('DELETE FROM marker')
                        connection.execute('INSERT INTO marker VALUES (?)', (day,))
                    with patch.object(backup, 'utc_now', return_value=now), contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(backup.main(source, directory), 0)
                    expected[now.weekday()] = day
                    self.assertEqual(len(list(directory.iterdir())), len(expected))
                    for slot, value in expected.items():
                        with contextlib.closing(sqlite3.connect(directory / f'day-{slot}.sqlite3')) as saved:
                            self.assertEqual(saved.execute('SELECT day FROM marker').fetchall(), [(value,)])

    def test_webhook_is_opt_in_and_errors_are_redacted(self):
        payload = {'status': 'failed', 'phase': 'open', 'timestamp': 'test'}
        with patch.dict(backup.os.environ, {}, clear=True), patch.object(backup.urllib.request, 'urlopen') as send:
            backup.alert(payload)
            send.assert_not_called()
        output = io.StringIO()
        with patch.dict(backup.os.environ, {'ALERT_WEBHOOK_URL': 'https://example.invalid/SECRET'}), \
                patch.object(backup.urllib.request, 'urlopen', side_effect=RuntimeError('SECRET')) as send, \
                contextlib.redirect_stderr(output):
            backup.alert(payload)
        self.assertEqual(json.loads(send.call_args.args[0].data), payload)
        self.assertNotIn('SECRET', output.getvalue())

