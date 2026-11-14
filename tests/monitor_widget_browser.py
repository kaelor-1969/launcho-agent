"""Real Chrome, real widget assets, two origins. No backend/AI/business calls."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.monitor_availability import Config, probe_widget
from monitor_fixture import server


@contextmanager
def running(**kwargs):
    httpd = server(**kwargs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{httpd.server_port}'
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


async def main():
    reports = []
    for fault in ('none', 'loader', 'iframe', 'not_ready', 'js_error', 'optional'):
        calls = []
        with running(fault=fault, calls=calls) as service, running(widget_base=service, calls=calls) as host:
            config = Config(service_url=service, host_url=host + '/',
                            loader_url=service + '/widget/loader.js', timeout=4,
                            screenshot_dir='artifacts/monitoring/screenshots')
            outcome = await probe_widget(config)
            assert outcome['ok'] == (fault in ('none', 'optional')), (fault, outcome)
            assert all(method == 'GET' for method, _ in calls), calls
            if outcome['ok']:
                assert outcome['loader'] and outcome['iframe'] and outcome['ui_shell']
                assert outcome['blocked_writes'] >= 1, outcome
                assert outcome['session_verified'] is False
            if fault == 'loader':
                assert not outcome['loader']
            if fault == 'iframe':
                assert outcome['loader'] and not outcome['ui_shell']
            if fault == 'not_ready':
                assert outcome['iframe'] and not outcome['ui_shell']
            if fault == 'js_error':
                assert outcome['widget_js_errors'] >= 1
            if fault == 'optional':
                assert outcome['optional_failures'] >= 1
            reports.append({'fault': fault, 'outcome': outcome, 'outgoing_writes': 0})
            print(json.dumps(reports[-1]), flush=True)
    folder = Path('artifacts/monitoring')
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'browser-results.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print('PASS: six real-browser scenarios; zero outgoing writes')


if __name__ == '__main__':
    asyncio.run(main())
