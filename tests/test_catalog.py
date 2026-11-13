"""Catalog provenance, selection boundaries and compatibility; no external API."""
import copy
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

from app.mock_draft_store import MockDraftStore
from app.mock_launcho import create_mock_app, content, fixture
from app.services import launcho_api
from app.services.catalog import SignupCatalog, selectable_catalog
from app.services.draft_gateway import ExistingReadOnlyGateway, GatewayUnavailable, LaunchoReadOnlyGateway

CATALOG = json.loads((content / 'launcho-draft-test-catalog.json').read_text())['signupOptions']
BODY = {'kind': 'shop', 'businessName': 'Catalog test', 'category': 'test-category',
        'planMonths': 3, 'template': 'test-template', 'domain': {'label': 'example', 'tld': 'ir'}}
HEADERS = {'Authorization': 'Bearer local-simulation', 'Idempotency-Key': 'catalog_request_key_01'}


def approved_catalog():
    data = copy.deepcopy(CATALOG['shop'])
    data.update(approvalStatus='approved', availability='available')
    data['source'] = {'type': 'official_api', 'reference': 'https://example.invalid/test-contract'}
    for item in data['businessCategories'] + data['templates']:
        item.update(approvalStatus='approved', source={'type': 'official_api', 'reference': 'https://example.invalid/test-contract'},
                    approvalEvidence='Synthetic unit-test evidence only')
    return data


class CatalogTests(unittest.TestCase):
    def test_every_registry_has_valid_metadata_and_matches_published_schema(self):
        for kind in ('shop', 'website'):
            for raw in (fixture['signupOptions'][kind], CATALOG[kind]):
                model = SignupCatalog.model_validate(raw)
                self.assertEqual(model.kind, kind)
                for item in model.businessCategories + model.templates:
                    self.assertTrue(item.source.reference)
                    self.assertEqual(item.approvalStatus, 'test_only')
        schema = json.loads((content / 'launcho-catalog.schema.json').read_text())
        self.assertEqual(schema, SignupCatalog.model_json_schema())

    def test_legacy_path_has_no_selectable_samples_and_cannot_fabricate_draft(self):
        for kind in ('shop', 'website'):
            raw = launcho_api.get_signup_options(kind)
            self.assertEqual(raw, fixture['signupOptions'][kind])
            self.assertEqual(ExistingReadOnlyGateway().get_signup_options(kind), raw)
            self.assertEqual(raw['businessCategories'], [])
            self.assertEqual(raw['templates'], [])
        with self.assertRaises(ValueError):
            launcho_api.get_signup_options('other')
        with self.assertRaises(RuntimeError):
            launcho_api.create_signup_draft('test', 'fashion', 3, 'example-row')

    def test_pending_inactive_unavailable_and_test_options_are_not_live_choices(self):
        self.assertEqual(selectable_catalog(CATALOG['shop'], 'shop')['templates'], [])
        for status in ('pending', 'inactive'):
            data = approved_catalog()
            for item in data['businessCategories'] + data['templates']:
                item.update(approvalStatus=status, available=False)
            result = selectable_catalog(data, 'shop')
            self.assertEqual(result['businessCategories'], [])
            self.assertEqual(result['templates'], [])
            self.assertEqual(result['availability'], 'unavailable')
        data = approved_catalog()
        data['templates'][0]['available'] = False
        self.assertEqual(selectable_catalog(data, 'shop')['templates'], [])

    def test_invalid_metadata_ids_kinds_and_relations_fail_closed(self):
        for change in ('missing-source', 'bad-date', 'duplicate-id', 'wrong-kind', 'unknown-category',
                       'pending-available', 'empty-compatibility', 'unproven-approval'):
            raw = copy.deepcopy(CATALOG['shop'])
            item = raw['templates'][0]
            if change == 'missing-source': del item['source']
            elif change == 'bad-date': item['reviewedAt'] = 'not-a-date'
            elif change == 'duplicate-id': raw['templates'].append(copy.deepcopy(item))
            elif change == 'wrong-kind': item['kind'] = 'website'
            elif change == 'unknown-category': item['compatibleCategoryIds'] = ['missing']
            elif change == 'pending-available': item['approvalStatus'] = 'pending'
            elif change == 'empty-compatibility': item['compatibleCategoryIds'] = []
            elif change == 'unproven-approval': item['approvalStatus'] = 'approved'
            with self.subTest(change=change), self.assertRaises(ValueError):
                selectable_catalog(raw, 'shop', allow_test=True)
        with self.assertRaises(ValueError):
            selectable_catalog(CATALOG['shop'], 'website', allow_test=True)

    def test_live_adapter_rejects_simulation_unproven_and_test_catalogs(self):
        gateway = LaunchoReadOnlyGateway('https://example.invalid/api', 'token')
        for data, simulation in [(CATALOG['shop'], False), (approved_catalog(), True),
                                 ({'kind': 'shop', 'businessCategories': [], 'templates': []}, False)]:
            upstream = httpx.Response(200, json={'ok': True, 'data': data, 'simulation': simulation},
                                      request=httpx.Request('GET', 'https://example.invalid/api/signup-options'))
            with patch('app.services.draft_gateway.httpx.get', return_value=upstream):
                with self.assertRaises(GatewayUnavailable): gateway.get_signup_options('shop')

    def test_live_catalog_has_no_stale_fallback_on_outage_or_deletion(self):
        gateway = LaunchoReadOnlyGateway('https://example.invalid/api', 'token')
        def upstream(data):
            return httpx.Response(200, json={'ok': True, 'data': data},
                                  request=httpx.Request('GET', 'https://example.invalid/api/signup-options'))
        deleted = approved_catalog()
        deleted['templates'] = []
        with patch('app.services.draft_gateway.httpx.get', side_effect=[upstream(approved_catalog()),
                   httpx.ConnectError('network unavailable'), upstream(deleted)]) as get:
            self.assertEqual(len(gateway.get_signup_options('shop')['templates']), 1)
            with self.assertRaises(GatewayUnavailable): gateway.get_signup_options('shop')
            self.assertEqual(gateway.get_signup_options('shop')['templates'], [])
        self.assertEqual(get.call_count, 3)

    def test_mock_rejects_wrong_category_deleted_inactive_and_pending_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = copy.deepcopy(CATALOG)
            second = {**catalog['shop']['businessCategories'][0], 'id': 'second-category'}
            catalog['shop']['businessCategories'].append(second)
            store = MockDraftStore(Path(tmp) / 'mock.sqlite3', catalog, fixture['pricing'])
            with TestClient(create_mock_app(store=store)) as client:
                wrong = client.post('/signup-drafts', json={**BODY, 'category': 'second-category'}, headers=HEADERS)
                self.assertEqual(wrong.status_code, 422)
                self.assertEqual(wrong.json()['error']['code'], 'incompatible_template')
                self.assertEqual(client.post('/signup-drafts', json=BODY, headers=HEADERS).status_code, 200)
                original = copy.deepcopy(catalog['shop']['templates'][0])
                for status in ('inactive', 'pending', 'deleted'):
                    catalog['shop']['templates'] = ([] if status == 'deleted' else
                        [{**original, 'approvalStatus': status, 'available': False}])
                    options = client.get('/signup-options?kind=shop', headers=HEADERS).json()['data']
                    self.assertEqual(options['templates'], [])
                    rejected = client.post('/signup-drafts', json=BODY,
                                            headers={**HEADERS, 'Idempotency-Key': 'new_catalog_key_' + status})
                    self.assertEqual(rejected.status_code, 503)
                    # Existing operation remains replayable after a template is retired.
                    self.assertEqual(client.post('/signup-drafts', json=BODY, headers=HEADERS).status_code, 200)

    def test_missing_or_corrupt_catalog_is_distinct_from_invalid_selected_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = copy.deepcopy(CATALOG)
            store = MockDraftStore(Path(tmp) / 'mock.sqlite3', catalog, fixture['pricing'])
            with TestClient(create_mock_app(store=store)) as client:
                invalid = client.post('/signup-drafts', json={**BODY, 'template': 'missing'}, headers=HEADERS)
                self.assertEqual(invalid.status_code, 422)
                del catalog['shop']['templates'][0]['source']
                failed = client.get('/signup-options?kind=shop', headers=HEADERS)
                self.assertEqual(failed.status_code, 503)
                self.assertEqual(failed.json()['error']['code'], 'catalog_unavailable')
                failed = client.post('/signup-drafts', json=BODY, headers=HEADERS)
                self.assertEqual(failed.status_code, 503)

    def test_public_reference_names_are_not_registration_options(self):
        audit = json.loads((content / 'launcho-catalog-audit.json').read_text())
        for entry in audit['publicReferences']:
            self.assertIsNone(entry['registrationId'])
            self.assertFalse(entry['available'])
            self.assertEqual(entry['approvalStatus'], 'pending')


if __name__ == '__main__':
    unittest.main()
