import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.services.session_store import SessionStore

spec = importlib.util.spec_from_file_location(
    'monitor_backend', Path(__file__).resolve().parents[1] / 'scripts/monitor_backend.py')
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def test_backup_preserves_session_authentication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = SessionStore(root / 'sessions.sqlite3')
            sid, token = store.create()
            backup = monitor.backup_and_verify(root / 'sessions.sqlite3', root / 'backups')
            self.assertEqual(SessionStore(backup).get(sid, token)['id'], sid)

    def test_missing_source_is_not_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(FileNotFoundError):
                monitor.backup_and_verify(root / 'missing.sqlite3', root / 'backups')
            self.assertFalse((root / 'missing.sqlite3').exists())

    def test_health_failure_returns_failure_but_still_backs_up(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            SessionStore(root / 'sessions.sqlite3')
            args = ['monitor', '--url', 'http://127.0.0.1:1', '--db',
                    str(root / 'sessions.sqlite3'), '--backup-dir', str(root / 'backups'), '--once']
            with patch('sys.argv', args), patch.object(monitor, 'probe', side_effect=OSError), patch('builtins.print'):
                self.assertEqual(monitor.main(), 1)
            self.assertEqual(len(list((root / 'backups').glob('*.sqlite3'))), 1)
