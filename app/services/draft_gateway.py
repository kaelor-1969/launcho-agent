"""Boundary owned jointly with the API teammate. No legacy write calls."""
from threading import Lock
from time import monotonic
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.services import launcho_api


class GatewayUnavailable(Exception):
    pass


class GatewayRejected(GatewayUnavailable):
    """Definitive rejection only: adapter knows the operation was not accepted."""
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


class DraftGateway(Protocol):
    mode: str
    can_create: bool

    def get_pricing(self) -> dict: ...
    def get_signup_options(self, kind: str) -> dict: ...
    def create_signup_draft(self, payload: dict, idempotency_key: str) -> dict: ...


class ExistingReadOnlyGateway:
    """Existing local fixtures are usable for previews, never for real success."""
    mode = 'legacy_mock'
    can_create = False

    def get_pricing(self):
        return launcho_api.get_pricing()

    def get_signup_options(self, kind):
        return launcho_api.get_signup_options(kind)

    def create_signup_draft(self, payload, idempotency_key):
        raise GatewayUnavailable('Contract-compliant draft adapter not installed.')


class LaunchoReadOnlyGateway:
    mode = 'live'
    can_create = False

    def __init__(self, base_url: str, token: str, *, local_mock=False):
        url = urlsplit(base_url)
        allowed_scheme = url.scheme == 'https'
        if local_mock:
            allowed_scheme = url.scheme == 'http' and url.hostname in {'127.0.0.1', '::1'}
        if (not allowed_scheme or not url.hostname or url.username or url.password
                or url.query or url.fragment or not token):
            raise GatewayUnavailable('Invalid Launcho API configuration.')
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.cache = {}
        self.lock = Lock()

    def read(self, endpoint: str, ttl: int, params: dict | None = None, *, payload=None) -> dict:
        key = (endpoint, tuple((params or {}).items()))
        with self.lock:
            entry = self.cache.get(key)
            if entry and monotonic() < entry[0]:
                return entry[1]
            try:
                request_options = dict(headers={'Authorization': f'Bearer {self.token}'},
                                       timeout=5, follow_redirects=False)
                if payload is None:
                    response = httpx.get(self.base_url + endpoint, params=params, **request_options)
                else:
                    response = httpx.post(self.base_url + endpoint, json=payload, **request_options)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                raise GatewayUnavailable('Launcho read request failed.') from None
            if not isinstance(payload, dict) or payload.get('ok') is not True:
                raise GatewayUnavailable('Invalid Launcho response envelope.')
            data = unwrap(payload)
            if ttl:
                self.cache[key] = (monotonic() + ttl, data)
            return data

    def get_pricing(self):
        return self.read('/pricing', 600)

    def get_signup_options(self, kind):
        if kind not in {'shop', 'website'}:
            raise GatewayUnavailable('Invalid Launcho service kind.')
        return self.read('/signup-options', 600, {'kind': kind})

    def get_service_info(self):
        return self.read('/service-info', 60)

    def create_signup_draft(self, payload, idempotency_key):
        raise GatewayUnavailable('Live draft creation is disabled.')


class LocalMockGateway(LaunchoReadOnlyGateway):
    mode = 'local_mock'

    def __init__(self, base_url):
        super().__init__(base_url, 'local-simulation', local_mock=True)

    def match_price_offers(self, kind):
        return self.read('/offers/match', 0, payload={
            'kind': kind, 'step': 4, 'objections': ['price'],
            'needs': ['low_upfront'], 'discountAlreadyShown': False,
        })


def build_gateway() -> DraftGateway:
    if settings.LAUNCHO_MOCK_URL:
        if settings.LAUNCHO_API_URL or settings.LAUNCHO_API_KEY:
            raise GatewayUnavailable('Configure either the local mock or the live Launcho API.')
        return LocalMockGateway(settings.LAUNCHO_MOCK_URL)
    if settings.LAUNCHO_API_URL or settings.LAUNCHO_API_KEY:
        return LaunchoReadOnlyGateway(settings.LAUNCHO_API_URL, settings.LAUNCHO_API_KEY)
    return ExistingReadOnlyGateway()


def unwrap(value: dict) -> dict:
    if not isinstance(value, dict):
        raise GatewayUnavailable('Invalid gateway response.')
    if 'ok' in value:
        if value.get('ok') is not True or not isinstance(value.get('data'), dict):
            raise GatewayUnavailable('Gateway unavailable or rejected request.')
        return value['data']
    return value
