import os
os.environ.setdefault('AI_API_KEY', 'test-placeholder')
os.environ.setdefault('AI_MODEL_NAME', 'test-model')

from pathlib import Path
import subprocess
import sys
import tempfile
import socket
import unittest
from unittest.mock import patch

import httpx
from app.core.runtime import RuntimePolicy
from app.main import app, policy
from app.services.session_store import SessionStore, CoreError
from check_demo import launch_server, wait_for_server


class StorageOperations(unittest.TestCase):
    def test_startup_failure_preserves_diagnostic_log(self):
        with tempfile.TemporaryDirectory() as temp:
            process = launch_server('missing_launcho_test_module:app', 0, dict(os.environ), Path(temp))
            try:
                process.wait(timeout=15)
                with httpx.Client(trust_env=False) as client:
                    with self.assertRaisesRegex(RuntimeError, 'Log:'):
                        wait_for_server(client, 'http://127.0.0.1:1', process)
                self.assertIn('missing_launcho_test_module', process.log_path.read_text(encoding='utf8'))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_occupied_port_fails_without_stopping_listener(self):
        with tempfile.TemporaryDirectory() as temp, socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            other_port = 1 if port != 1 else 2
            result = subprocess.run([sys.executable, 'tests/check_demo.py', '--backend-only',
                                     '--agent-port', str(port), '--mock-port', str(other_port),
                                     '--log-dir', temp], capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unavailable', result.stderr)
            self.assertEqual(listener.getsockname()[1], port)

    def test_online_backup_restore_and_cascading_retention(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            store = SessionStore(path / 'source.sqlite3')
            sid, token = store.create()
            with store.transaction() as db:
                db.execute('INSERT INTO shown_local_offers VALUES (?)', (sid,))
            store.backup(path / 'backup.sqlite3')
            with self.assertRaises(ValueError):
                store.backup(path / 'backup.sqlite3')
            result = subprocess.run([sys.executable, 'scripts/session_admin.py', 'restore',
                                     '--db', str(path / 'restored.sqlite3'), '--file', str(path / 'backup.sqlite3')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            restored = SessionStore(path / 'restored.sqlite3')
            self.assertEqual(restored.get(sid, token)['id'], sid)
            with restored.transaction() as db:
                db.execute('UPDATE sessions SET expires=0')
            self.assertEqual(restored.cleanup(), 1)
            with restored.transaction() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM shown_local_offers').fetchone()[0], 0)
            self.assertEqual(store.get(sid, token)['id'], sid)

    def test_production_rejects_mock_and_missing_configuration(self):
        with patch.dict(os.environ, {'LAUNCHO_ENV': 'production'}, clear=True):
            with self.assertRaises(RuntimeError):
                RuntimePolicy()
        with patch.dict(os.environ, {'LAUNCHO_ENV': 'production', 'LAUNCHO_FRAME_ANCESTORS': 'https://launcho.ir',
                                     'LAUNCHO_MOCK_URL': 'http://127.0.0.1:8001'}, clear=True):
            with self.assertRaises(RuntimeError):
                RuntimePolicy()

    def test_rate_window_and_origin_validation(self):
        with patch.dict(os.environ, {'LAUNCHO_REQUESTS_PER_MINUTE': '1'}):
            runtime = RuntimePolicy()
        with patch('app.core.runtime.time.monotonic', return_value=100):
            self.assertTrue(runtime.admit('peer'))
            self.assertFalse(runtime.admit('peer'))
        with patch('app.core.runtime.time.monotonic', return_value=161):
            self.assertTrue(runtime.admit('peer'))
        with patch.dict(os.environ, {'LAUNCHO_CORS_ORIGINS': 'https://example.com/path'}):
            with self.assertRaises(RuntimeError):
                RuntimePolicy()


class OperationalEndpoints(unittest.IsolatedAsyncioTestCase):
    async def test_headers_body_limit_rate_and_readiness_failure(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            result = await client.get('/health/live')
            self.assertEqual(result.status_code, 200)
            self.assertIn('frame-ancestors', result.headers['content-security-policy'])
            result = await client.post('/api/chat', content=b'x' * (policy.max_body + 1))
            self.assertEqual(result.status_code, 413)
            with patch.object(policy, 'admit', return_value=False):
                result = await client.post('/api/sessions')
            self.assertEqual(result.status_code, 429)
            self.assertEqual(result.headers['cache-control'], 'no-store')
            with patch('app.main.get_core', side_effect=RuntimeError('private-details')):
                result = await client.get('/health/ready')
            self.assertEqual(result.status_code, 503)
            self.assertNotIn('private-details', result.text)
