"""Frontend-only local preview. No AI, session or draft API is exposed."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / 'frontend'


class WidgetHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.startswith('/widget/'):
            path = path[len('/widget'):]
        return super().translate_path(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1',args.port), partial(WidgetHandler,directory=str(FRONTEND)))
    print(f'Demo only: http://127.0.0.1:{server.server_port}/widget/demo.html', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
