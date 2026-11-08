"""Boundary owned jointly with the API teammate. No legacy write calls."""
from typing import Protocol
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


def build_gateway() -> DraftGateway:
    # Replace this factory with the teammate's contract-compliant adapter.
    # It must preserve Idempotency-Key through timeouts and return real API data.
    return ExistingReadOnlyGateway()


def unwrap(value: dict) -> dict:
    if not isinstance(value, dict):
        raise GatewayUnavailable('Invalid gateway response.')
    if 'ok' in value:
        if value.get('ok') is not True or not isinstance(value.get('data'), dict):
            raise GatewayUnavailable('Gateway unavailable or rejected request.')
        return value['data']
    return value
