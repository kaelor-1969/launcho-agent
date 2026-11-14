"""Local monitoring-only fixture: real frontend files, synthetic health, no API.

Run a service on 8020 and a host on 8022 with --widget-base http://127.0.0.1:8020.
Not an application server or a production health implementation.
"""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1] / 'frontend'


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, widget_base='', fault='none', calls=None, **kwargs):
        self.widget_base = widget_base
        self.fault = fault
        self.calls = calls if calls is not None else []
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.calls.append(('GET', urlsplit(self.path).path))
        path = urlsplit(self.path).path
        content_type = 'text/html; charset=utf-8'
        status = 200
        if path.startswith('/health/'):
            content_type = 'application/json'
            body = json.dumps({'status': 'ok' if path == '/health/live' else 'ready'}).encode()
        elif path == '/' and self.widget_base:
            body = ('<!doctype html><meta charset="utf-8"><title>Monitoring fixture</title>'
                    '<h1>Local monitoring fixture — no customer data</h1>'
                    f'<script defer src="{self.widget_base}/widget/loader.js" data-auto-open="false"></script>').encode()
        elif path.startswith('/widget/'):
            file = (ROOT / path.removeprefix('/widget/')).resolve()
            if ROOT not in file.parents or not file.is_file():
                status, body = 404, b''
            elif self.fault == 'loader' and path.endswith('loader.js'):
                status, body = 503, b''
            elif self.fault == 'iframe' and path.endswith('widget.html'):
                status, body = 503, b''
            elif self.fault == 'not_ready' and path.endswith('widget.js'):
                content_type, body = 'text/javascript', b'// no module setup / ready handshake'
            elif self.fault == 'js_error' and path.endswith('widget.js'):
                content_type, body = 'text/javascript', b'throw new Error("fixture error");'
            elif self.fault == 'optional' and path.endswith('.png'):
                status, body = 404, b''
            else:
                body = file.read_bytes()
                content_type = {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html; charset=utf-8'}.get(file.suffix, mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        else:
            status, body = 404, b''
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        self.calls.append(('POST', self.path))
        self.send_response(405)
        self.end_headers()

    def log_message(self, *args):
        pass


def server(port=0, widget_base='', fault='none', calls=None):
    return ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, widget_base=widget_base, fault=fault, calls=calls))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--widget-base', default='')
    args = parser.parse_args()
    with server(args.port, args.widget_base) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
