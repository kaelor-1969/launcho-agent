"""Controlled HTTP tests; no application imports or external traffic."""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import monitor_availability as monitor


@contextmanager
def receiver(status=200, body=b'{"status":"ok"}', content_type='application/json', delay=0):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            if delay:
                time.sleep(delay)
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Location', '/login')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def config(**kw):
    return monitor.Config(service_url='http://127.0.0.1:8020', host_url='http://127.0.0.1:8022/',
                          loader_url='http://127.0.0.1:8020/widget/loader.js', **kw)


class HealthTests(unittest.TestCase):
    def test_live_and_ready_contracts(self):
        for endpoint, value in [('live', 'ok'), ('ready', 'ready')]:
            with receiver(body=json.dumps({'status': value}).encode()) as (url, calls):
                outcome = asyncio.run(monitor.probe_health(url, endpoint, 2))
                self.assertTrue(outcome['ok'])
                self.assertEqual(calls, ['/health/' + endpoint])

    def test_rejects_status_redirect_html_and_invalid_contract(self):
        scenarios = [({'status': 503}, 'http_status'), ({'status': 302}, 'http_status'),
                     ({'content_type': 'text/html', 'body': b'<html>login</html>'}, 'content_type'),
                     ({'body': b'{invalid'}, 'invalid_json'),
                     ({'body': b'[]'}, 'health_contract'),
                     ({'body': b'{"status":"ready"}'}, 'health_contract'),
                     ({'body': b'x' * 17000}, 'body_too_large')]
        for kwargs, code in scenarios:
            with self.subTest(code=code), receiver(**kwargs) as (url, calls):
                outcome = asyncio.run(monitor.probe_health(url, 'live', 2))
                self.assertFalse(outcome['ok'])
                self.assertEqual(outcome['code'], code)
                self.assertEqual(len(calls), 1)

    def test_timeout_and_connection_refused_are_safe(self):
        with receiver(delay=.25) as (url, _):
            self.assertEqual(asyncio.run(monitor.probe_health(url, 'live', .1))['code'], 'timeout')
        self.assertEqual(asyncio.run(monitor.probe_health(url, 'live', 5))['code'], 'connection')

    def test_configured_timeout_can_exceed_httpx_default(self):
        with receiver(delay=5.1) as (url, _):
            self.assertTrue(asyncio.run(monitor.probe_health(url, 'live', 7))['ok'])

    def test_deep_json_or_parser_recursion_cannot_stop_monitor(self):
        # Python JSON implementations have different nesting limits. This valid
        # JSON array must fail the health contract whether parsing succeeds or not.
        with receiver(body=b'[' * 1100 + b'0' + b']' * 1100) as (url, _):
            outcome = asyncio.run(monitor.probe_health(url, 'live', 2))
            self.assertFalse(outcome['ok'])
            self.assertIn(outcome['code'], ('health_contract', 'invalid_json'))
        with receiver() as (url, _), patch.object(monitor.json, 'loads', side_effect=RecursionError):
            self.assertEqual(asyncio.run(monitor.probe_health(url, 'live', 2))['code'], 'invalid_json')

    def test_config_validation(self):
        for kw in [{'timeout': 0}, {'interval': float('nan')}, {'failure_threshold': True},
                   {'delivery_attempts': 4}, {'browser_channel': 'fake'}]:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                config(**kw)
        for url in ['file:///tmp/x', 'https://user:secret@example.org',
                    'https://example.org/?token=secret', 'https://example.org/#token']:
            with self.assertRaises(ValueError):
                monitor.valid_url(url)


if __name__ == '__main__':
    unittest.main()
