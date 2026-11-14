"""Executable examples and the real routes/core/HTTP-adapter boundary; no external calls."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('AI_API_KEY', 'test-placeholder')
os.environ.setdefault('AI_BASE_URL', 'https://example.invalid/v1')
os.environ.setdefault('AI_MODEL_NAME', 'test-model')

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.mock_launcho import create_mock_app, fixture
from app.services.conversation_core import ConversationCore
from app.services.draft_gateway import LaunchoDraftGateway, GatewayRejected
from app.services.launcho_contract import DraftRequest, normalize_draft
from app.services.session_store import SessionStore

ROOT = Path(__file__).resolve().parents[1]
CHOICES = {'kind': 'shop', 'businessName': 'test shop', 'category': 'test-category',
           'planMonths': 3, 'template': 'test-template',
           'domain': {'label': 'example', 'tld': 'ir'}}


def assert_subset(test, expected, actual):
    if isinstance(expected, dict):
        test.assertIsInstance(actual, dict)
        for key, value in expected.items():
            test.assertIn(key, actual)
            assert_subset(test, value, actual[key])
    elif isinstance(expected, list):
        test.assertIsInstance(actual, list)
        test.assertEqual(len(expected), len(actual))
        for left, right in zip(expected, actual):
            assert_subset(test, left, right)
    else:
        test.assertEqual(expected, actual)


class ContractExamples(unittest.TestCase):
    def test_documented_requests_match_http(self):
        examples = json.loads((ROOT / 'docs/examples/launcho-mock-v3.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temp, TestClient(create_mock_app(
                db_path=Path(temp) / 'mock.sqlite3', catalog_profile='unavailable')) as client:
            for case in examples['cases']:
                with self.subTest(case=case['name']):
                    request = case['request']
                    kwargs = {'headers': request['headers']}
                    if 'json' in request:
                        kwargs['json'] = request['json']
                    response = client.request(request['method'], request['path'], **kwargs)
                    self.assertEqual(response.status_code, case['response']['status'])
                    if case.get('comparison') == 'subset':
                        assert_subset(self, case['response']['json'], response.json())
                    else:
                        self.assertEqual(response.json(), case['response']['json'])

    def test_schema_is_published_from_the_adapter_model(self):
        schema = json.loads((ROOT / 'docs/examples/launcho-draft-request.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(schema, DraftRequest.model_json_schema())

    def test_proposed_draft_example_matches_main_core_and_fixture_total(self):
        target = json.loads((ROOT / 'docs/examples/launcho-draft-target-v1.json').read_text(encoding='utf-8'))
        case = target['cases'][0]
        payload = normalize_draft(case['request']['json'])
        result = case['response']['json']
        total = fixture['pricing']['setupFees'][payload['kind']]
        total += next(p['price'] for p in fixture['pricing']['plans'] if p['months'] == payload['planMonths'])
        total += next(d['annualFee'] for d in fixture['pricing']['domains'] if d['tld'] == payload['domain']['tld'])
        self.assertEqual(result['data']['quote']['total'], total)
        clock = datetime.fromisoformat(target['referenceClock'].replace('Z', '+00:00')).timestamp()
        with patch('app.services.conversation_core.time.time', return_value=clock):
            self.assertEqual(ConversationCore.validate_result(result)['ref'], result['data']['ref'])

    def test_normalization_is_stable_and_rejects_ambiguous_payloads(self):
        value = {**CHOICES, 'businessName': '  test shop  ',
                 'domain': {**CHOICES['domain'], 'ownDomain': None}}
        self.assertEqual(normalize_draft(value), CHOICES)
        self.assertEqual(normalize_draft(normalize_draft(value)), CHOICES)
        self.assertEqual(normalize_draft({k: v for k, v in CHOICES.items() if k != 'kind'}), CHOICES)
        for change in ({'domain': None}, {'planMonths': 3.0}, {'planMonths': True},
                       {'planMonths': '3'}, {'mobile': 'test'}, {'template': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_draft({**CHOICES, **change})

    def test_invalid_payload_and_key_never_reach_transport(self):
        gateway = LaunchoDraftGateway('https://example.invalid/api', 'test-token')
        with patch('app.services.draft_gateway.httpx.post') as send:
            for payload, key in [({**CHOICES, 'domain': None}, 'a' * 32),
                                 (CHOICES, 'short'), (CHOICES, 'x' * 16 + '\n')]:
                with self.assertRaises(GatewayRejected):
                    gateway.create_signup_draft(payload, key)
            send.assert_not_called()


class CoreAdapterContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.gateway = LaunchoDraftGateway('https://example.invalid/assistant/v1', 'test-token')
        self.core = ConversationCore(SessionStore(Path(self.tmp.name) / 'sessions.sqlite3'), self.gateway)
        self.calls = []
        self.result = {'ref': 'sd_contract_test', 'status': 'draft',
                       'confirmUrl': 'https://launcho.ir/start?signup=sd_contract_test',
                       'expiresAt': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
                       'quote': {'total': 17400000, 'isFinal': False}}
        self.fail_once = False
        self.error_status = None
        self.created = False
        self.bad_result = None
        for target, value in [('app.api.routes.get_core', self.core)]:
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target, action in [('app.services.draft_gateway.httpx.get', self.get_upstream),
                               ('app.services.draft_gateway.httpx.post', self.post_upstream)]:
            patcher = patch(target, side_effect=action)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        session = self.client.post('/api/sessions').json()
        self.base = '/api/sessions/' + session['sessionId']
        self.headers = {'X-Session-Token': session['sessionToken']}

    def response(self, method, url, data, status=200):
        return httpx.Response(status, json=data, request=httpx.Request(method, url))

    def get_upstream(self, url, **kwargs):
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-token')
        if url.endswith('/pricing'):
            data = fixture['pricing']
        elif url.endswith('/signup-options'):
            # Synthetic approved upstream response for transport tests only; no real catalog approval.
            data = json.loads((ROOT / 'content/launcho-draft-test-catalog.json').read_text(encoding='utf-8'))['signupOptions']['shop']
            data.update(approvalStatus='approved', availability='available')
            data['source'] = {'type': 'official_api', 'reference': 'https://example.invalid/test-catalog'}
            for entry in data['businessCategories'] + data['templates']:
                entry.update(approvalStatus='approved',
                             source={'type': 'official_api', 'reference': 'https://example.invalid/test-catalog'},
                             approvalEvidence='Synthetic approval in an isolated transport test; not real data')
        elif url.endswith('/signup-drafts/sd_contract_test'):
            data = {'ref': 'sd_contract_test', 'status': 'draft'}
        else:
            self.fail('Unexpected upstream read: ' + url)
        return self.response('GET', url, {'ok': True, 'data': data})

    def post_upstream(self, url, **kwargs):
        self.assertEqual(url, self.gateway.base_url + '/signup-drafts')
        self.calls.append(copy.deepcopy(kwargs))
        if self.error_status:
            return self.response('POST', url, {'ok': False, 'error': {'code': 'upstream_error'}}, self.error_status)
        self.created = True
        if self.fail_once:
            self.fail_once = False
            raise httpx.ReadTimeout('response lost after creation')
        return self.response('POST', url, {'ok': True, 'data': self.bad_result or self.result})

    def review(self, choices=None):
        edited = self.client.patch(self.base + '/preferences', headers=self.headers,
                                   json={'revision': 0, 'preferences': choices or CHOICES})
        self.assertEqual(edited.status_code, 200, edited.text)
        review = self.client.post(self.base + '/review', headers=self.headers,
                                  json={'revision': edited.json()['revision']})
        self.assertEqual(review.status_code, 200, review.text)
        value = review.json()
        return {**{k: value[k] for k in ('revision', 'reviewId', 'confirmationToken')}, 'confirmed': True}

    def test_main_http_flow_and_replay_preserve_core_payload_and_key(self):
        body = self.review()
        first = self.client.post(self.base + '/confirm', headers=self.headers, json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['confirmUrl'], self.result['confirmUrl'])
        replay = self.client.post(self.base + '/confirm', headers=self.headers, json=body)
        self.assertTrue(replay.json()['replayed'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]['json'], CHOICES)
        key = self.calls[0]['headers']['Idempotency-Key']
        self.assertRegex(key, r'^[A-Za-z0-9_-]{16,128}$')
        status = self.client.get(self.base + '/draft-status', headers=self.headers)
        self.assertEqual(status.json(), {'status': 'draft'})
        self.assertEqual(self.client.get(self.base + '/draft-status').status_code, 404)

    def test_timeout_retries_same_key_and_payload_through_main_http(self):
        body = self.review()
        self.fail_once = True
        failed = self.client.post(self.base + '/confirm', headers=self.headers, json=body)
        self.assertTrue(self.created)
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.json()['detail']['code'], 'draft_outcome_unknown')
        retried = self.client.post(self.base + '/confirm', headers=self.headers, json=body)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(self.calls[0]['json'], self.calls[1]['json'])
        self.assertEqual(self.calls[0]['headers'], self.calls[1]['headers'])

    def test_missing_domain_is_rejected_by_the_existing_core_before_transport(self):
        choices = {k: v for k, v in CHOICES.items() if k != 'domain'}
        edited = self.client.patch(self.base + '/preferences', headers=self.headers,
                                   json={'revision': 0, 'preferences': choices})
        review = self.client.post(self.base + '/review', headers=self.headers,
                                  json={'revision': edited.json()['revision']})
        self.assertEqual(review.status_code, 422)
        self.assertEqual(review.json()['detail']['code'], 'incomplete_preferences')
        self.assertEqual(self.calls, [])

    def test_conflict_stays_unknown_and_does_not_mint_a_new_operation(self):
        body = self.review()
        self.error_status = 409
        failed = self.client.post(self.base + '/confirm', headers=self.headers, json=body)
        self.assertEqual(failed.json()['detail']['code'], 'draft_outcome_unknown')
        # A conflict can mean an earlier operation exists: never classify it as safe to recreate.
        second = self.client.post(self.base + '/confirm', headers=self.headers, json=body)
        self.assertEqual(second.status_code, 503)
        self.assertEqual(self.calls[0]['headers'], self.calls[1]['headers'])

    def test_local_url_never_passes_the_existing_core(self):
        body = self.review()
        self.bad_result = {**self.result, 'confirmUrl': 'http://127.0.0.1:8001/draft-preview'}
        failed = self.client.post(self.base + '/confirm', headers=self.headers, json=body)
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.json()['detail']['code'], 'draft_outcome_unknown')
        self.assertNotIn('confirmUrl', failed.json())


if __name__ == '__main__':
    unittest.main()
