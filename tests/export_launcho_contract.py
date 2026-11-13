"""Explicitly refresh HTTP examples/schema: python tests/export_launcho_contract.py.

Run from the repository root; no model, external HTTP, credentials or application DB needed.
"""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.mock_launcho import create_mock_app, content, fixture
from app.mock_draft_store import MockDraftStore
from app.services.launcho_contract import DraftRequest
from app.services.catalog import SignupCatalog


def main():
    path = ROOT / 'docs/examples/launcho-mock-v2.json'
    examples = json.loads((ROOT / 'docs/examples/launcho-mock-v1.json').read_text())
    cases = examples['cases'][:10]
    for case in cases:
        if case['name'] == 'draft-not-implemented':
            case['name'] = 'draft-missing-key'
    body = dict(kind='shop', planMonths=3, step=4, objections=['price'],
                needs=['low_upfront'], discountAlreadyShown=False)
    headers = {'Authorization': 'Bearer local-simulation'}
    invalid = [
        ('pricing-invalid-kind', 'GET', '/pricing?kind=other', None),
        ('options-missing-kind', 'GET', '/signup-options', None),
        ('options-invalid-kind', 'GET', '/signup-options?kind=other', None),
        ('offer-invalid-period', 'POST', '/offers/match', {**body, 'planMonths': 5}),
        ('offer-extra-field', 'POST', '/offers/match', {**body, 'unexpected': True}),
        ('offer-missing-field', 'POST', '/offers/match', {k: v for k, v in body.items() if k != 'needs'}),
        ('offer-invalid-need', 'POST', '/offers/match', {**body, 'needs': ['invented']}),
        ('pricing-wrong-method', 'POST', '/pricing', {}),
        ('status-not-found', 'GET', '/signup-drafts/sd_contract_test', None),
    ]
    for name, method, route, payload in invalid:
        req = {'method': method, 'path': route, 'headers': headers}
        if payload is not None:
            req['json'] = payload
        cases.append({'name': name, 'request': req})
    with tempfile.TemporaryDirectory() as temp, TestClient(create_mock_app(
            db_path=Path(temp) / 'mock.sqlite3', catalog_profile='unavailable')) as client:
        for case in cases:
            req = case['request']
            kwargs = {'headers': req['headers']}
            if 'json' in req:
                kwargs['json'] = req['json']
            response = client.request(req['method'], req['path'], **kwargs)
            value = response.json()
            if response.status_code == 422 and isinstance(value.get('detail'), list):
                value = {'detail': [{'type': err['type'], 'loc': err['loc']} for err in value['detail']]}
                case['comparison'] = 'subset'
            case['response'] = {'status': response.status_code, 'json': value}
    examples.update(contractVersion='local-mock-v2.0.0',
                    generatedFrom='FastAPI TestClient against app.mock_launcho; no external requests',
                    cases=cases)
    path.write_text(json.dumps(examples, ensure_ascii=False, indent=2) + '\n')
    schema = DraftRequest.model_json_schema()
    (path.parent / 'launcho-draft-request.schema.json').write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + '\n')
    export_drafts(path.parent)
    (ROOT / 'content/launcho-catalog.schema.json').write_text(
        json.dumps(SignupCatalog.model_json_schema(), ensure_ascii=False, indent=2) + '\n')
    print(f'Exported {len(cases)} HTTP examples, persistent-draft scenarios and the adapter request schema.')


def export_drafts(directory):
    now = [1800000000.0]
    payload = {'kind': 'shop', 'businessName': 'Mock business', 'category': 'test-category',
               'planMonths': 3, 'template': 'test-template', 'domain': {'label': 'example', 'tld': 'ir'}}
    headers = {'Authorization': 'Bearer local-simulation', 'Idempotency-Key': 'mock_example_request_01'}
    ref = 'sd_mock_example01'
    scenarios = [
        ('create', 0, 'POST', '/signup-drafts', payload),
        ('replay', 1, 'POST', '/signup-drafts', payload),
        ('conflict', 2, 'POST', '/signup-drafts', {**payload, 'businessName': 'Another business'}),
        ('status-draft', 3, 'GET', '/signup-drafts/' + ref, None),
        ('replay-expired', 10, 'POST', '/signup-drafts', payload),
        ('status-expired', 10, 'GET', '/signup-drafts/' + ref, None),
        ('status-purged', 30, 'GET', '/signup-drafts/' + ref, None),
        ('invalid-reference', 30, 'GET', '/signup-drafts/invalid', None),
    ]
    catalog = json.loads((content / 'launcho-draft-test-catalog.json').read_text())['signupOptions']
    result = []
    with tempfile.TemporaryDirectory() as temp:
        store = MockDraftStore(Path(temp) / 'mock.sqlite3', catalog, fixture['pricing'],
                               ttl=10, retention=30, clock=lambda: now[0])
        with TestClient(create_mock_app(store=store)) as client, \
                patch('app.mock_draft_store.secrets.token_urlsafe', return_value='example01'):
            for name, offset, method, route, body in scenarios:
                now[0] = 1800000000.0 + offset
                kwargs = {'headers': headers}
                if body is not None:
                    kwargs['json'] = body
                response = client.request(method, route, **kwargs)
                result.append({'name': name, 'offsetSeconds': offset,
                               'request': {'method': method, 'path': route, **kwargs},
                               'response': {'status': response.status_code, 'json': response.json()}})
    (directory / 'launcho-mock-drafts-v2.json').write_text(json.dumps({
        'contractVersion': 'local-mock-v2.0.0', 'generatedFrom': 'TestClient with isolated SQLite and a fixed clock',
        'clock': 1800000000.0, 'ttlSeconds': 10, 'retentionSeconds': 30, 'cases': result},
        ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
