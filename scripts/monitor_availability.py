"""Read-only service/UI-shell monitoring, independent of application DB/backups."""
import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

import httpx


def utc():
    return datetime.now(timezone.utc).isoformat()


def emit(event, **fields):
    print(json.dumps({'time': utc(), 'event': event, **fields}), flush=True)


def valid_url(value, secret=False):
    try:
        u = urlsplit(value)
        if (u.scheme not in ('http', 'https') or not u.hostname or u.username or
                u.password or u.fragment or (u.query and not secret) or
                any(c.isspace() for c in value)):
            raise ValueError
        _ = u.port
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Expected an absolute HTTP(S) URL without credentials/fragment; target queries are forbidden.') from None
    return value.rstrip('/')


def origin(url):
    u = urlsplit(url)
    return f'{u.scheme}://{u.netloc}'


@dataclass(frozen=True)
class Config:
    service_url: str
    host_url: str
    loader_url: str
    label: str = 'local-example'
    interval: float = 60
    timeout: float = 10
    failure_threshold: int = 3
    recovery_threshold: int = 2
    delivery_attempts: int = 2
    state_file: str = 'artifacts/monitoring/state.json'
    browser_channel: str = 'chrome'
    screenshot_dir: str = ''

    def __post_init__(self):
        for name in ('service_url', 'host_url', 'loader_url'):
            valid_url(getattr(self, name))
        if urlsplit(self.service_url).path not in ('', '/'):
            raise ValueError('service_url must be an origin.')
        if not self.loader_url.endswith('/widget/loader.js'):
            raise ValueError('loader_url must end in /widget/loader.js.')
        if self.label not in ('local-example', 'external-host'):
            raise ValueError('label must be local-example or external-host.')
        for name in ('interval', 'timeout'):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 < v <= 3600:
                raise ValueError(f'{name} must be a finite number in (0, 3600].')
        for name in ('failure_threshold', 'recovery_threshold', 'delivery_attempts'):
            v = getattr(self, name)
            if type(v) is not int or not 1 <= v <= 100:
                raise ValueError(f'{name} must be an integer in [1, 100].')
        if self.delivery_attempts > 3:
            raise ValueError('delivery_attempts is limited to 3.')
        if self.browser_channel not in ('chrome', 'msedge', 'chromium'):
            raise ValueError('browser_channel must be chrome, msedge or chromium.')
        if not isinstance(self.state_file, str) or not self.state_file:
            raise ValueError('state_file is required.')
        if not isinstance(self.screenshot_dir, str):
            raise ValueError('screenshot_dir must be a string.')

    def identity(self):
        raw = json.dumps([self.service_url, self.host_url, self.loader_url, self.label])
        return hashlib.sha256(raw.encode()).hexdigest()


def result(ok, code, **fields):
    return {'ok': ok, 'code': code, **fields}


async def probe_health(base, endpoint, timeout):
    async def request():
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
            async with client.stream('GET', f'{base.rstrip("/")}/health/{endpoint}') as response:
                if response.status_code != 200:
                    return result(False, 'http_status', status=response.status_code)
                if response.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                    return result(False, 'content_type')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 16384:
                        return result(False, 'body_too_large')
                try:
                    data = json.loads(body)
                except (ValueError, UnicodeError):
                    return result(False, 'invalid_json')
                expected = 'ok' if endpoint == 'live' else 'ready'
                return result(isinstance(data, dict) and data.get('status') == expected,
                              'ok' if isinstance(data, dict) and data.get('status') == expected else 'health_contract')
    try:
        return await asyncio.wait_for(request(), timeout)
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return result(False, 'timeout')
    except httpx.HTTPError:
        return result(False, 'connection')


async def probe_widget(config):
    # Imported lazily: HTTP/state/delivery unit tests do not need a browser.
    from playwright.async_api import async_playwright, Error as BrowserError
    details = {'loader': False, 'iframe': False, 'ui_shell': False,
               'blocked_writes': 0, 'essential_failures': 0,
               'widget_js_errors': 0, 'host_js_errors': 0,
               'optional_failures': 0, 'session_verified': False}
    widget_origin = origin(config.loader_url)
    allowed = {origin(config.host_url), widget_origin}
    browser = None
    context = None
    page = None
    phase = 'browser_start'

    def essential(req):
        u = urlsplit(req.url)
        return (req.url == config.loader_url or
                (origin(req.url) == widget_origin and u.path.startswith('/widget/') and
                 req.resource_type in ('document', 'script', 'stylesheet')))

    async def guard(route):
        req = route.request
        if req.method not in ('GET', 'HEAD'):
            details['blocked_writes'] += 1
            await route.abort()
        elif origin(req.url) not in allowed or urlsplit(req.url).path.startswith('/api/'):
            await route.abort()
        else:
            await route.continue_()

    def failed(req):
        if req.method in ('GET', 'HEAD'):
            key = 'essential_failures' if essential(req) else 'optional_failures'
            details[key] += 1

    def response(res):
        if res.url == config.loader_url and res.status == 200:
            details['loader'] = True
        if res.status >= 300:
            key = 'essential_failures' if essential(res.request) else 'optional_failures'
            details[key] += 1

    def js_error(error):
        # Never retain exception text, URLs, page content or credentials.
        key = 'widget_js_errors' if widget_origin + '/widget/' in (error.stack or '') else 'host_js_errors'
        details[key] += 1

    try:
        async with async_playwright() as pw:
            try:
                channel = None if config.browser_channel == 'chromium' else config.browser_channel
                browser = await pw.chromium.launch(channel=channel, timeout=config.timeout * 1000)
                context = await browser.new_context(service_workers='block', accept_downloads=False)
                await context.route('**/*', guard)
                # Fail closed on versions lacking socket interception.
                await context.route_web_socket('**/*', lambda socket: socket.close())
                page = await context.new_page()
                page.on('requestfailed', failed)
                page.on('response', response)
                page.on('pageerror', js_error)

                async def inspect():
                    nonlocal phase
                    phase = 'host_navigation'
                    nav = await page.goto(config.host_url, wait_until='domcontentloaded', timeout=0)
                    if nav is None or nav.status != 200 or page.url != config.host_url:
                        return result(False, 'host_status_or_redirect', **details)
                    phase = 'loader'
                    await page.wait_for_function('typeof window.LaunchoWidget?.open === "function"', timeout=0)
                    scripts = page.locator('script[src]')
                    if not await scripts.evaluate_all('(els, url) => els.filter(e => e.src === url).length === 1', config.loader_url):
                        return result(False, 'loader_installation', **details)
                    await page.evaluate('window.LaunchoWidget.open()')
                    phase = 'iframe'
                    frame_node = page.locator('#launcho-widget iframe')
                    await frame_node.wait_for(state='attached', timeout=0)
                    if await frame_node.count() != 1:
                        return result(False, 'iframe_count', **details)
                    src = await frame_node.get_attribute('src')
                    if origin(src) != widget_origin or urlsplit(src).path not in ('/widget/widget.html', '/widget/widget-legacy.html'):
                        return result(False, 'iframe_target', **details)
                    details['iframe'] = True
                    phase = 'ui_shell'
                    await frame_node.wait_for(state='visible', timeout=0)
                    frame = await frame_node.element_handle()
                    frame = await frame.content_frame()
                    await frame.locator('#message').wait_for(state='visible', timeout=0)
                    if origin(frame.url) != widget_origin or urlsplit(frame.url).path not in ('/widget/widget.html', '/widget/widget-legacy.html'):
                        return result(False, 'iframe_navigation', **details)
                    await frame.locator('#close').wait_for(state='visible', timeout=0)
                    if not await frame.locator('#message').is_editable() or not await frame.locator('#close').is_enabled():
                        return result(False, 'ui_controls', **details)
                    # Exercise reversible close control, never a business action.
                    await frame.locator('#close').click(timeout=0)
                    await frame_node.wait_for(state='hidden', timeout=0)
                    details['ui_shell'] = True
                    ok = details['loader'] and not details['essential_failures'] and not details['widget_js_errors']
                    return result(bool(ok), 'ok' if ok else 'widget_resource_or_js', **details)

                try:
                    return await asyncio.wait_for(inspect(), config.timeout)
                except asyncio.TimeoutError:
                    return result(False, phase + '_timeout', **details)
                finally:
                    if not details['ui_shell'] and config.screenshot_dir and page:
                        # Mask the entire page: no host/customer text or frame pixels persist.
                        folder = Path(config.screenshot_dir)
                        folder.mkdir(parents=True, exist_ok=True)
                        try:
                            await page.screenshot(path=str(folder / 'widget-failure.png'),
                                                  mask=[page.locator('html')], timeout=2000)
                        except BrowserError:
                            pass
            finally:
                if context:
                    await context.close()
                if browser:
                    await browser.close()
    except (BrowserError, AttributeError):
        return result(False, 'browser_unavailable', **details)


class State:
    """Single-process monitor state. No application storage is touched."""
    def __init__(self, config):
        self.config = config
        self.path = Path(config.state_file)
        self.data = {'version': 1, 'identity': config.identity(), 'checks': {}}
        if self.path.exists():
            try:
                candidate = json.loads(self.path.read_text(encoding='utf-8'))
                if candidate.get('version') != 1 or candidate.get('identity') != config.identity():
                    raise ValueError
                checks = candidate['checks']
                if not isinstance(checks, dict) or set(checks) - {'live', 'ready', 'widget'}:
                    raise ValueError
                for item in checks.values():
                    if (set(item) != {'down', 'failures', 'successes'} or type(item['down']) is not bool or
                            any(type(item[k]) is not int or item[k] < 0 for k in ('failures', 'successes'))):
                        raise ValueError
                self.data = candidate
            except (ValueError, KeyError, TypeError, AttributeError):
                raise ValueError('State invalid or belongs to another target; inspect privately, then choose a new state file.') from None

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + '.tmp')
        temp.write_text(json.dumps(self.data), encoding='utf-8')
        os.replace(temp, self.path)

    def observe(self, name, outcome):
        s = self.data['checks'].setdefault(name, {'down': False, 'failures': 0, 'successes': 0})
        s['failures'] = 0 if outcome['ok'] else min(s['failures'] + 1, self.config.failure_threshold)
        s['successes'] = min(s['successes'] + 1, self.config.recovery_threshold) if outcome['ok'] else 0
        event = None
        if not s['down'] and s['failures'] >= self.config.failure_threshold:
            s['down'] = True
            event = 'outage'
        elif s['down'] and s['successes'] >= self.config.recovery_threshold:
            s['down'] = False
            event = 'recovery'
        return event


class Sender:
    def __init__(self, config, dry_run=True):
        self.config = config
        self.dry_run = dry_run
        self.url = os.environ.get('LAUNCHO_MONITOR_WEBHOOK', '')
        self.token = os.environ.get('LAUNCHO_MONITOR_WEBHOOK_TOKEN', '')
        if any(ord(c) < 32 or ord(c) > 126 for c in self.token):
            raise ValueError('Webhook token contains invalid header characters.')
        if not dry_run:
            valid_url(self.url, secret=True)
            u = urlsplit(self.url)
            if u.scheme != 'https' and u.hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('Webhook requires HTTPS except for loopback tests.')

    async def send(self, payload):
        if self.dry_run:
            emit('alert_dry_run', payload=payload)
            return True
        headers = {'Authorization': f'Bearer {self.token}'} if self.token else {}
        for attempt in range(self.config.delivery_attempts):
            try:
                async def post():
                    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
                        async with client.stream('POST', self.url, json=payload, headers=headers) as res:
                            return 200 <= res.status_code < 300
                if await asyncio.wait_for(post(), self.config.timeout):
                    emit('alert_delivered', event_id=payload['id'])
                    return True
            except (httpx.HTTPError, asyncio.TimeoutError):
                pass
            if attempt + 1 < self.config.delivery_attempts:
                await asyncio.sleep(0.2 * (attempt + 1))
        emit('alert_delivery_failed', event_id=payload['id'], attempts=self.config.delivery_attempts)
        return False


async def cycle(config, state, sender, widget_probe=probe_widget):
    outcomes = {}
    # Serial checks: no overlap or unbounded retries; each HTTP check has a total deadline.
    for name in ('live', 'ready'):
        outcomes[name] = await probe_health(config.service_url, name, config.timeout)
    outcomes['widget'] = await widget_probe(config)
    events = []
    for name, outcome in outcomes.items():
        transition = state.observe(name, outcome)
        emit('check', check=name, label=config.label, **outcome)
        if transition:
            stamp = utc()
            target = origin(config.host_url if name == 'widget' else config.service_url)
            ident = hashlib.sha256(f'{config.identity()}:{name}:{transition}:{stamp}'.encode()).hexdigest()[:24]
            events.append({'id': ident, 'time': stamp, 'type': transition,
                           'check': name, 'target': target, 'label': config.label,
                           'code': outcome['code'], 'test': False,
                           'summary': 'UI shell only; session not verified' if name == 'widget' else 'Health endpoint contract',
                           'checks': {k: {'ok': v['ok'], 'code': v['code']} for k, v in outcomes.items()}})
    # Persist BEFORE delivery: at-most-once bounded send sequence per transition.
    # Crash between persist/send may lose notification; no replay/reminder after restart.
    state.save()
    for payload in events:
        await sender.send(payload)
    return all(o['ok'] for o in outcomes.values())


async def run(args):
    config = Config(**json.loads(Path(args.config).read_text(encoding='utf-8')))
    sender = Sender(config, dry_run=not args.send)
    # Exclusive lock: stale lock after hard kill requires operator inspection.
    lock = Path(config.state_file + '.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        state = State(config)
        if args.test_alert:
            payload = {'id': hashlib.sha256(utc().encode()).hexdigest()[:24], 'time': utc(),
                       'type': 'test', 'check': 'channel', 'test': True,
                       'label': config.label, 'summary': 'آزمایشی — Launcho monitoring channel test'}
            return 0 if await sender.send(payload) else 1
        while True:
            healthy = await cycle(config, state, sender)
            if args.once:
                return 0 if healthy else 1
            # Interval is a delay after completion, not a fixed wall-clock cadence.
            await asyncio.sleep(config.interval)
    finally:
        os.close(fd)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Trusted local JSON config file')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--send', action='store_true', help='Enable bounded webhook delivery; default is dry-run')
    parser.add_argument('--test-alert', action='store_true', help='One labelled test message only')
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130
    except Exception:
        # Exception messages can contain URLs, secrets or filesystem/user data.
        emit('monitor_error', code='configuration_state_lock_or_runtime',
             hint='Check trusted config, browser installation, state permissions and stale lock; see runbook.')
        return 2


if __name__ == '__main__':
    sys.exit(main())
