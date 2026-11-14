"""Owned real FastAPI/mock processes, safe browser and synthetic alert receiver."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import monitor_availability as m
from monitor_fixture import server
from test_monitor_delivery import webhook


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def start(module, port, env, logs):
    log_path = logs / f'{port}-startup.log'
    with log_path.open('wb') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', module,
                                    '--host', '127.0.0.1', '--port', str(port), '--no-access-log'],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        with httpx.Client(trust_env=False) as client:
            deadline = time.monotonic() + 30
            # A responding root proves only liveness. Establish real readiness
            # before a scenario asserts that the restarted agent is healthy.
            readiness_path = '/health/ready' if module == 'app.main:app' else '/'
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Owned fixture process exited; inspect private startup log.')
                try:
                    if ('Uvicorn running on' in log_path.read_text(encoding='utf-8', errors='replace') and
                            client.get(f'http://127.0.0.1:{port}{readiness_path}', timeout=5).status_code == 200 and process.poll() is None):
                        return process
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
        raise RuntimeError('Owned fixture process did not become ready.')
    except BaseException:
        stop(process)
        raise


async def drill():
    folder = ROOT / 'artifacts/monitoring'
    folder.mkdir(parents=True, exist_ok=True)
    reports = []
    mock = agent = None
    host = None
    host_thread = None
    with tempfile.TemporaryDirectory(prefix='launcho-monitor-') as temp:
        agent_port, mock_port = free_port(), free_port()
        while mock_port == agent_port:
            mock_port = free_port()
        service, mock_url = f'http://127.0.0.1:{agent_port}', f'http://127.0.0.1:{mock_port}'
        host = server(widget_base=service)
        host_url = f'http://127.0.0.1:{host.server_port}'
        host_thread = threading.Thread(target=host.serve_forever, daemon=True)
        host_thread.start()
        env = dict(os.environ)
        env.update(AI_API_KEY=' ', AI_MODEL_NAME=' ', AI_BASE_URL='https://example.invalid/v1',
                   LAUNCHO_API_KEY=' ', LAUNCHO_API_URL=' ', LAUNCHO_MOCK_URL=mock_url,
                   LAUNCHO_ENV='development', LAUNCHO_WIDGET_ORIGIN=service,
                   LAUNCHO_FRAME_ANCESTORS=host_url, LAUNCHO_CORS_ORIGINS=host_url,
                   LAUNCHO_SESSION_DB=str(Path(temp) / 'sessions.sqlite3'),
                   LAUNCHO_MOCK_DRAFT_DB=str(Path(temp) / 'drafts.sqlite3'))
        c = m.Config(service_url=service, host_url=host_url + '/',
                     loader_url=service + '/widget/loader.js', timeout=4,
                     failure_threshold=2, recovery_threshold=2,
                     state_file=str(Path(temp) / 'monitor.json'))
        try:
            mock = start('app.mock_launcho:app', mock_port, env, folder)
            agent = start('app.main:app', agent_port, env, folder)
            with webhook() as (hook_url, calls), patch.dict(os.environ, {
                    'LAUNCHO_MONITOR_WEBHOOK': hook_url, 'LAUNCHO_MONITOR_WEBHOOK_TOKEN': ''}):
                sender = m.Sender(c, dry_run=False)
                state = m.State(c)

                async def sample(label, expected_healthy, expected_count):
                    nonlocal state
                    outcome = await m.cycle(c, state, sender)
                    assert outcome == expected_healthy, label
                    assert len(calls) == expected_count, (label, len(calls), expected_count)
                    # Monitor restart from its own private state after EVERY cycle.
                    state = m.State(c)
                    reports.append({'scenario': label, 'healthy': outcome, 'alert_count': len(calls)})

                await sample('healthy_real_backend_and_widget', True, 0)
                stop(agent)
                agent = None
                await sample('transient_below_threshold', False, 0)
                agent = start('app.main:app', agent_port, env, folder)
                await sample('transient_cleared', True, 0)
                stop(agent)
                agent = None
                await sample('persistent_first_failure', False, 0)
                await sample('persistent_open_three_checks', False, 3)
                await sample('ongoing_outage_no_duplicates_after_restart', False, 3)
                agent = start('app.main:app', agent_port, env, folder)
                await sample('first_recovery_not_yet_confirmed', True, 3)
                await sample('confirmed_recovery_three_checks', True, 6)
                await sample('healthy_no_duplicate_recoveries', True, 6)
                assert sorted((x['payload']['check'], x['payload']['type']) for x in calls) == sorted(
                    (check, event) for check in ('live', 'ready', 'widget') for event in ('outage', 'recovery'))
                assert len({x['payload']['id'] for x in calls}) == 6
                assert all(x['payload']['label'] == 'local-example' for x in calls)
                # Widget-only regression with real service still healthy: swap only
                # the fixture host's loader tag, never modify the application.
                original = host.RequestHandlerClass
                from functools import partial
                from monitor_fixture import Handler
                host.RequestHandlerClass = partial(Handler, widget_base=service + '/missing')
                await sample('widget_only_failure_below_threshold', False, 6)
                await sample('widget_only_outage_health_still_ok', False, 7)
                last = calls[-1]['payload']
                assert last['check'] == 'widget' and last['type'] == 'outage'
                assert last['checks']['live']['ok'] and last['checks']['ready']['ok']
                host.RequestHandlerClass = original
                await sample('widget_first_recovery', True, 7)
                await sample('widget_confirmed_recovery', True, 8)
                # Channel failure while polling continues: one separate receiver
                # always rejects. Three checks => at most two attempts each.
                with webhook((503,)) as (bad_hook, rejected), patch.dict(os.environ, {'LAUNCHO_MONITOR_WEBHOOK': bad_hook}):
                    bad_sender = m.Sender(c, dry_run=False)
                    stop(agent)
                    agent = None
                    await m.cycle(c, state, bad_sender)
                    await m.cycle(c, state, bad_sender)
                    assert len(rejected) == 6
                    state = m.State(c)
                    await m.cycle(c, state, bad_sender)
                    assert len(rejected) == 6
                    reports.append({'scenario': 'channel_failure_polling_continues_restart_no_replay',
                                    'failed_attempts': 6, 'transitions': 3})
                # CLI channel test sends precisely one labelled test payload.
                cfg = Path(temp) / 'config.json'
                cfg.write_text(json.dumps(c.__dict__), encoding='utf-8')
                cli_env = dict(os.environ)
                cli_env['LAUNCHO_MONITOR_WEBHOOK'] = hook_url
                cli = await asyncio.create_subprocess_exec(sys.executable, 'scripts/monitor_availability.py',
                    '--config', str(cfg), '--send', '--test-alert', cwd=ROOT, env=cli_env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await cli.communicate()
                assert cli.returncode == 0
                assert len(calls) == 9 and calls[-1]['payload']['test'] is True
                assert 'آزمایشی' in calls[-1]['payload']['summary']
                reports.append({'scenario': 'cli_labelled_channel_test', 'messages': 1})
        finally:
            stop(agent)
            stop(mock)
            host.shutdown()
            host.server_close()
            host_thread.join()
    (folder / 'drill-results.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print(json.dumps({'event': 'drill_pass', 'scenarios': reports, 'owned_processes_stopped': True}), flush=True)


if __name__ == '__main__':
    asyncio.run(drill())
