"""Persistent mock API: actual SQLite transactions and HTTP, isolated from normal data."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.mock_draft_store import MockDraftStore
from app.mock_launcho import create_mock_app, content, fixture

CATALOG = json.loads((content / 'launcho-draft-test-catalog.json').read_text())['signupOptions']
PAYLOAD = {'kind': 'shop', 'businessName': 'Mock business', 'category': 'test-category',
           'planMonths': 3, 'template': 'test-template', 'domain': {'label': 'example', 'tld': 'ir'}}
HEADERS = {'Authorization': 'Bearer local-simulation', 'Idempotency-Key': 'mock_test_request_0001'}


class MockDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'mock.sqlite3'
        self.now = 1800000000.0
        self.catalog = copy.deepcopy(CATALOG)
        self.store = self.make_store()
        self.client = TestClient(create_mock_app(store=self.store), raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def make_store(self, **kwargs):
        return MockDraftStore(self.path, self.catalog, fixture['pricing'],
                              ttl=10, retention=30, clock=lambda: self.now, **kwargs)

    def create(self, body=None, headers=None):
        return self.client.post('/signup-drafts', json=PAYLOAD if body is None else body,
                                headers=HEADERS if headers is None else headers)

    def count(self):
        with sqlite3.connect(self.path) as db:
            return db.execute('SELECT COUNT(*) FROM mock_drafts').fetchone()[0]

    def test_create_read_quote_and_controlled_preview(self):
        result = self.create()
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()['data']
        self.assertTrue(result.json()['simulation'])
        self.assertIn('آزمایشی', result.json()['notice'])
        self.assertRegex(data['ref'], r'^sd_mock_[A-Za-z0-9_-]+$')
        self.assertEqual(data['status'], 'draft')
        self.assertLess(data['createdAt'], data['expiresAt'])
        self.assertLess(data['expiresAt'], data['retainUntil'])
        self.assertEqual(data['quote'], {'currency': 'toman', 'total': 17400000, 'isFinal': False})
        self.assertEqual(data['confirmUrl'], 'http://127.0.0.1:8001/mock-drafts/' + data['ref'])
        read = self.client.get('/signup-drafts/' + data['ref'], headers=HEADERS)
        self.assertEqual(read.json()['data'], data)
        preview = self.client.get('/mock-drafts/' + data['ref'])
        self.assertEqual(preview.status_code, 200)
        self.assertIn('هیچ پرداخت', preview.text)
        self.assertNotIn(PAYLOAD['businessName'], preview.text)
        self.assertIn("default-src 'none'", preview.headers['content-security-policy'])
        self.assertEqual(preview.headers['cache-control'], 'no-store')

    def test_published_draft_examples_match_the_api(self):
        examples = json.loads((content.parent / 'docs/examples/launcho-mock-drafts-v2.json').read_text())
        with patch('app.mock_draft_store.secrets.token_urlsafe', return_value='example01'):
            for case in examples['cases']:
                with self.subTest(case=case['name']):
                    self.now = examples['clock'] + case['offsetSeconds']
                    request = case['request']
                    kwargs = {'headers': request['headers']}
                    if 'json' in request:
                        kwargs['json'] = request['json']
                    result = self.client.request(request['method'], request['path'], **kwargs)
                    self.assertEqual(result.status_code, case['response']['status'])
                    self.assertEqual(result.json(), case['response']['json'])

    def test_replay_canonicalization_and_frozen_expiry(self):
        first = self.create().json()
        self.now += 2
        body = {k: PAYLOAD[k] for k in reversed(list(PAYLOAD)) if k != 'kind'}
        body['businessName'] = '  Mock business  '
        body['domain'] = {'ownDomain': None, 'tld': 'ir', 'label': 'example'}
        repeat = self.create(body)
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json(), first)
        self.assertEqual(self.count(), 1)
        # Replay must still work if a template is retired after the original write.
        self.catalog['shop']['templates'].clear()
        self.assertEqual(self.create().json(), first)

    def test_conflict_cannot_modify_existing_record(self):
        first = self.create().json()['data']
        conflict = self.create({**PAYLOAD, 'businessName': 'Different business'})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['error']['code'], 'idempotency_conflict')
        self.assertEqual(self.create().json()['data'], first)
        self.assertEqual(self.count(), 1)

    def test_concurrent_requests_from_independent_app_instances_create_once(self):
        def submit(index):
            with TestClient(create_mock_app(db_path=self.path, catalog_profile='test')) as client:
                return client.post('/signup-drafts', json=PAYLOAD, headers=HEADERS)
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(submit, range(12)))
        self.assertEqual({reply.status_code for reply in replies}, {200})
        self.assertEqual(len({reply.json()['data']['ref'] for reply in replies}), 1)
        self.assertEqual(self.count(), 1)

    def test_concurrent_different_payloads_have_one_winner(self):
        def submit(index):
            body = {**PAYLOAD, 'businessName': 'Business ' + str(index)}
            with TestClient(create_mock_app(db_path=self.path, catalog_profile='test')) as client:
                return client.post('/signup-drafts', json=body, headers=HEADERS).status_code
        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(submit, range(6)))
        self.assertEqual(statuses.count(200), 1)
        self.assertEqual(statuses.count(409), 5)
        self.assertEqual(self.count(), 1)

    def test_lost_http_response_after_commit_replays_saved_result(self):
        saved = []
        def lose_response(data, authorization):
            saved.append(data)
            raise RuntimeError('connection lost after commit')
        with patch('app.mock_launcho.response', side_effect=lose_response):
            lost = self.create()
        self.assertEqual(lost.status_code, 500)
        self.assertEqual(self.count(), 1)
        retry = self.create()
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()['data'], saved[0])
        self.assertEqual(self.count(), 1)

    def test_write_failure_rolls_back_and_never_returns_success(self):
        original = self.store.transaction
        @contextmanager
        def fail_before_commit():
            with original() as db:
                yield db
                raise sqlite3.OperationalError('test storage failure')
        with patch.object(self.store, 'transaction', fail_before_commit):
            failed = self.create()
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.json()['error']['code'], 'draft_outcome_unknown')
        self.assertNotIn('test storage failure', failed.text)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.create().status_code, 200)
        self.assertEqual(self.count(), 1)

    def test_restart_preserves_key_payload_result_and_deadlines(self):
        first = self.create().json()['data']
        self.now += 3
        rebuilt = MockDraftStore(self.path, self.catalog, fixture['pricing'], ttl=100, retention=200,
                                  clock=lambda: self.now)
        with TestClient(create_mock_app(store=rebuilt)) as client:
            reply = client.post('/signup-drafts', json=PAYLOAD, headers=HEADERS)
            self.assertEqual(reply.json()['data'], first)
            read = client.get('/signup-drafts/' + first['ref'], headers=HEADERS)
            self.assertEqual(read.json()['data'], first)
        self.assertEqual(self.count(), 1)

    def test_separate_process_can_replay_after_restart(self):
        # A fresh interpreter has no in-memory idempotency cache.
        first = self.create().json()['data']
        script = '''import json,sys
from fastapi.testclient import TestClient
from app.mock_draft_store import MockDraftStore
from app.mock_launcho import create_mock_app,content,fixture
catalog=json.loads((content/'launcho-draft-test-catalog.json').read_text())['signupOptions']
store=MockDraftStore(sys.argv[1],catalog,fixture['pricing'],clock=lambda:1800000001)
with TestClient(create_mock_app(store=store)) as client:
    r=client.post('/signup-drafts',json=json.loads(sys.argv[2]),headers=json.loads(sys.argv[3]))
    print(json.dumps({'status':r.status_code,'body':r.json()}))
'''
        run = subprocess.run([sys.executable, '-c', script, str(self.path), json.dumps(PAYLOAD), json.dumps(HEADERS)],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['status'], 200)
        self.assertEqual(result['body']['data'], first)

    def test_expiry_boundary_replay_conflict_and_status(self):
        first = self.create().json()['data']
        self.now += 9.999
        self.assertEqual(self.create().status_code, 200)
        self.now = 1800000010.0
        expired = self.create()
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(expired.json()['error']['code'], 'draft_expired')
        self.assertEqual(self.count(), 1)
        read = self.client.get('/signup-drafts/' + first['ref'], headers=HEADERS)
        self.assertEqual(read.json()['data']['status'], 'expired')
        self.assertEqual(self.client.get('/mock-drafts/' + first['ref']).status_code, 410)
        changed = self.create({**PAYLOAD, 'businessName': 'Different business'})
        self.assertEqual(changed.status_code, 409)
        fresh = self.create(headers={**HEADERS, 'Idempotency-Key': 'new_mock_request_0002'})
        self.assertEqual(fresh.status_code, 200)
        self.assertNotEqual(fresh.json()['data']['ref'], first['ref'])

    def test_retention_boundary_cleanup_and_key_reuse(self):
        first = self.create().json()['data']
        self.now += 30
        missing = self.client.get('/signup-drafts/' + first['ref'], headers=HEADERS)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(self.count(), 0)
        new = self.create().json()['data']
        self.assertNotEqual(new['ref'], first['ref'])
        self.now += 30
        self.assertEqual(self.store.cleanup(), 1)
        self.assertEqual(self.store.cleanup(), 0)

    def test_auth_input_and_unknown_ids_have_explicit_errors(self):
        for headers in ({}, {'Authorization': 'Bearer wrong', 'Idempotency-Key': HEADERS['Idempotency-Key']}):
            result = self.create(headers=headers)
            self.assertEqual(result.status_code, 401)
        bad_payloads = [[], None, {**PAYLOAD, 'mobile': 'not allowed'},
                        {**PAYLOAD, 'domain': None}, {**PAYLOAD, 'planMonths': '3'},
                        {**PAYLOAD, 'planMonths': True}, {**PAYLOAD, 'planMonths': 3.0},
                        {**PAYLOAD, 'kind': 'other'}, {**PAYLOAD, 'template': 'missing'},
                        {**PAYLOAD, 'domain': {'label': 'example', 'tld': 'invalid'}}]
        for body in bad_payloads:
            with self.subTest(body=body):
                result = self.client.post('/signup-drafts', json=body, headers=HEADERS)
                self.assertEqual(result.status_code, 422, result.text)
                self.assertFalse(result.json()['ok'])
        malformed = self.client.post('/signup-drafts', content='{', headers=HEADERS)
        self.assertEqual(malformed.status_code, 422)
        missing_key = self.create(headers={'Authorization': HEADERS['Authorization']})
        self.assertEqual(missing_key.json()['error']['code'], 'invalid_idempotency_key')
        self.assertEqual(self.client.get('/signup-drafts/sd_missing', headers=HEADERS).status_code, 404)
        self.assertEqual(self.client.get('/signup-drafts/invalid', headers=HEADERS).status_code, 422)
        self.assertEqual(self.client.get('/signup-drafts/sd_missing').status_code, 401)
        self.assertEqual(self.count(), 0)

    def test_website_and_unknown_existing_domain_cost(self):
        website = {**PAYLOAD, 'kind': 'website', 'category': 'test-website-category',
                   'template': 'test-website-template'}
        result = self.create(website)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['data']['quote']['total'], 7400000)
        own = self.create({**PAYLOAD, 'domain': {'ownDomain': 'example.ir'}},
                          headers={**HEADERS, 'Idempotency-Key': 'existing_domain_test_01'})
        self.assertEqual(own.status_code, 200)
        self.assertIsNone(own.json()['data']['quote'])

    def test_default_catalog_stays_unavailable_and_test_db_is_isolated(self):
        other_path = Path(self.tmp.name) / 'separate' / 'ordinary.sqlite3'
        with TestClient(create_mock_app(db_path=other_path, catalog_profile='unavailable')) as normal:
            options = normal.get('/signup-options?kind=shop', headers=HEADERS).json()['data']
            self.assertEqual(options['availability'], 'unavailable')
            result = normal.post('/signup-drafts', json=PAYLOAD, headers=HEADERS)
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json()['error']['code'], 'catalog_unavailable')
        self.assertEqual(self.count(), 0)
        with self.client as client:
            options = client.get('/signup-options?kind=shop', headers=HEADERS).json()['data']
            self.assertEqual(options['availability'], 'test_only')

    def test_bad_lifetimes_and_uncontrolled_preview_origins_are_rejected(self):
        for ttl, retention in [(0, 30), (-1, 30), (20, 10), (True, 30)]:
            with self.assertRaises(ValueError):
                MockDraftStore(self.path, self.catalog, fixture['pricing'], ttl=ttl, retention=retention)
        for origin in ['https://launcho.ir', 'http://evil.example', 'http://127.0.0.1/path',
                       'http://user@127.0.0.1', 'http://127.0.0.1?x=1']:
            with self.assertRaises(ValueError):
                self.make_store(preview_origin=origin)
        result = self.client.post('/signup-drafts', json=PAYLOAD, headers={**HEADERS, 'Host': 'evil.example'})
        self.assertTrue(result.json()['data']['confirmUrl'].startswith('http://127.0.0.1:8001/'))

    def test_unusable_database_directory_has_safe_retryable_error(self):
        blocked = Path(self.tmp.name) / 'not-a-directory'
        blocked.write_text('file instead of directory')
        with TestClient(create_mock_app(db_path=blocked / 'draft.sqlite3', catalog_profile='test'),
                        raise_server_exceptions=False) as client:
            result = client.post('/signup-drafts', json=PAYLOAD, headers=HEADERS)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()['error']['code'], 'draft_outcome_unknown')
        self.assertNotIn(str(blocked), result.text)
        self.assertNotIn('confirmUrl', result.text)
        self.assertEqual(result.headers['cache-control'], 'no-store')

    def test_invalid_preview_configuration_fails_before_database_access(self):
        path = Path(self.tmp.name) / 'unused' / 'draft.sqlite3'
        for origin in ('http://external.example', 'http://127.0.0.1:0', 'http://127.0.0.1:bad'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                create_mock_app(db_path=path, preview_origin=origin)
        self.assertFalse(path.parent.exists())

    def test_openapi_exposes_resolvable_draft_body_schema(self):
        application = create_mock_app(store=self.store)
        schema = application.openapi()['paths']['/signup-drafts']['post']['requestBody']
        self.assertTrue(schema['required'])
        body = schema['content']['application/json']['schema']
        self.assertIn('domain', body['required'])
        self.assertIn('businessName', body['required'])
        self.assertEqual(body['properties']['planMonths']['enum'], [3, 6, 12])
        self.assertFalse(body['additionalProperties'])
        self.assertIn('ownDomain', body['properties']['domain']['properties'])
        self.assertNotIn('"$ref"', json.dumps(body))


if __name__ == '__main__':
    unittest.main()
