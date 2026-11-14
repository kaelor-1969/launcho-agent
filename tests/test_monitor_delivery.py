import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import monitor_availability as m
from test_monitor_availability import config


@contextmanager
def webhook(statuses=(200,), delay=0):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'payload': data, 'authorization': self.headers.get('Authorization')})
            if delay:
                time.sleep(delay)
            self.send_response(statuses[min(len(calls) - 1, len(statuses) - 1)])
            self.send_header('Location', '/must-not-follow')
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/hook?secret=fixture-only', calls
    finally:
        server.shutdown()
        server.server_close()
        t.join()


class DeliveryTests(unittest.TestCase):
    payload = {'id': 'fixture-event', 'test': True, 'type': 'test',
               'summary': 'آزمایشی', 'check': 'channel'}

    def test_dry_run_never_sends_or_exposes_environment(self):
        with patch.dict(os.environ, {'LAUNCHO_MONITOR_WEBHOOK': 'secret-invalid-url',
                                     'LAUNCHO_MONITOR_WEBHOOK_TOKEN': 'fixture-token'}), patch.object(m, 'emit') as log:
            self.assertTrue(asyncio.run(m.Sender(config()).send(self.payload)))
            self.assertNotIn('secret-invalid-url', str(log.call_args_list))
            self.assertNotIn('fixture-token', str(log.call_args_list))

    def test_payload_token_and_retry_keep_same_event_id(self):
        with webhook((503, 200)) as (url, calls), patch.dict(os.environ, {
                'LAUNCHO_MONITOR_WEBHOOK': url, 'LAUNCHO_MONITOR_WEBHOOK_TOKEN': 'fixture-token'}), patch.object(m, 'emit') as log:
            self.assertTrue(asyncio.run(m.Sender(config(), dry_run=False).send(self.payload)))
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]['payload'], self.payload)
            self.assertEqual(calls[1]['payload'], self.payload)
            self.assertEqual(calls[0]['authorization'], 'Bearer fixture-token')
            self.assertNotIn('fixture-token', str(log.call_args_list))
            self.assertNotIn('secret=', str(log.call_args_list))

    def test_failed_and_redirect_delivery_are_bounded(self):
        for status in (503, 302):
            with webhook((status,)) as (url, calls), patch.dict(os.environ, {'LAUNCHO_MONITOR_WEBHOOK': url}), patch.object(m, 'emit'):
                self.assertFalse(asyncio.run(m.Sender(config(), dry_run=False).send(self.payload)))
                self.assertEqual(len(calls), 2)

    def test_live_config_requires_url_https_and_safe_token(self):
        for url in ('', 'not-url', 'http://example.org/webhook', 'https://user:secret@example.org'):
            with patch.dict(os.environ, {'LAUNCHO_MONITOR_WEBHOOK': url}), self.assertRaises(ValueError):
                m.Sender(config(), dry_run=False)
        with patch.dict(os.environ, {'LAUNCHO_MONITOR_WEBHOOK_TOKEN': 'bad\r\nheader'}), self.assertRaises(ValueError):
            m.Sender(config())

    def test_timeout_and_refused_connection_return_false(self):
        with webhook(delay=.4) as (url, calls), patch.dict(os.environ, {'LAUNCHO_MONITOR_WEBHOOK': url}), patch.object(m, 'emit'):
            self.assertFalse(asyncio.run(m.Sender(config(timeout=.15, delivery_attempts=1), dry_run=False).send(self.payload)))
            self.assertLessEqual(len(calls), 1)
        with patch.dict(os.environ, {'LAUNCHO_MONITOR_WEBHOOK': url}), patch.object(m, 'emit'):
            self.assertFalse(asyncio.run(m.Sender(config(timeout=3, delivery_attempts=1), dry_run=False).send(self.payload)))


if __name__ == '__main__':
    unittest.main()
