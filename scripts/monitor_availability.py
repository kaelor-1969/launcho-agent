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


async def run(args):
    config = Config(**json.loads(Path(args.config).read_text(encoding='utf-8')))
    while True:
        outcomes = {}
        for name in ('live', 'ready'):
            outcomes[name] = await probe_health(config.service_url, name, config.timeout)
            emit('check', check=name, label=config.label, **outcomes[name])
        if args.once:
            return 0 if all(o['ok'] for o in outcomes.values()) else 1
        await asyncio.sleep(config.interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Trusted local JSON config file')
    parser.add_argument('--once', action='store_true')
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
