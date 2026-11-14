"""Internal named-stage offer contract; persistent state is supplied by the core owner."""
import os
os.environ.setdefault('AI_API_KEY', 'test-placeholder')
os.environ.setdefault('AI_BASE_URL', 'https://example.invalid/v1')
os.environ.setdefault('AI_MODEL_NAME', 'test-model')
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.mock_launcho import app, OfferRequest
from app.services.draft_gateway import LocalMockGateway, LaunchoDraftGateway, GatewayUnavailable
from app.services.offer_contract import FinancialOffer, OfferState, OFFER_STAGES, validated_offers

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
OFFER = dict(offerId='demo_campaign', type='discount', kind='shop',
             displayText='این پیشنهاد آزمایشی است و برای خرید اعتبار ندارد.',
             expiresAt='2099-01-01T00:00:00Z', simulation=True,
             source={'type': 'internal_fixture', 'reference': 'content/launcho-mock.json'},
             eligibleStages=['review_ready'], planMonths=[3, 6, 12])


class OfferContractTests(unittest.TestCase):
    def filter(self, offers, **kwargs):
        return validated_offers({'offers': offers}, kind='shop', stage='review_ready',
                                allow_simulation=True, now=NOW, **kwargs)['offers']

    def test_named_stages_and_rejected_numeric_stage_over_http(self):
        body = dict(kind='shop', step='review_ready', objections=['price'],
                    needs=['low_upfront'], discountAlreadyShown=False)
        with TestClient(app) as client:
            for stage in OFFER_STAGES:
                reply = client.post('/offers/match', json={**body, 'step': stage},
                                    headers={'Authorization': 'Bearer local-simulation'})
                self.assertEqual(reply.status_code, 200)
                self.assertEqual(bool(reply.json()['data']['offers']), stage == 'review_ready')
            for stage in [4, True, '4', 'invented']:
                self.assertEqual(client.post('/offers/match', json={**body, 'step': stage},
                    headers={'Authorization': 'Bearer local-simulation'}).status_code, 422)

    def test_mock_result_is_structured_and_local_only(self):
        self.assertEqual(self.filter([OFFER])[0]['offerId'], 'demo_campaign')
        self.assertEqual(validated_offers({'offers': [OFFER]}, kind='shop', stage='review_ready',
                                         now=NOW)['offers'], [])

    def test_expiry_exact_boundary_kind_stage_and_period(self):
        for change in [{'expiresAt': NOW.isoformat()}, {'kind': 'website'},
                       {'eligibleStages': ['draft_created']}, {'planMonths': [12]}]:
            with self.subTest(change=change):
                self.assertEqual(self.filter([{**OFFER, **change}], plan_months=3), [])

    def test_malformed_provenance_text_ids_and_time_fail(self):
        for change in [{'offerId': ''}, {'expiresAt': '2099-01-01'}, {'expiresAt': 9999999999},
                       {'source': {'type': 'official_api', 'reference': 'https://launcho.ir/offers'}},
                       {'displayText': '[پرداخت](https://evil.example)'},
                       {'displayText': 'کد تایید: 123456'}, {'type': 'unknown'},
                       {'eligibleStages': ['review_ready', 'review_ready']}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.filter([{**OFFER, **change}])
        with self.assertRaises(ValueError):
            self.filter([OFFER, OFFER])
        with self.assertRaises(ValueError):
            validated_offers({'offers': 'invalid'}, kind='shop', stage='review_ready')

    def test_official_source_requires_evidence_and_exact_host(self):
        # All official-looking values here are synthetic transport fixtures, not product approval.
        offer = {**OFFER, 'simulation': False, 'source': {'type': 'official_api',
                 'reference': 'https://launcho.ir/api/offers', 'approvalEvidence': 'synthetic-test-only'}}
        self.assertFalse(FinancialOffer.model_validate(offer).simulation)
        for reference in ['https://launcho.ir.evil.example/api', 'http://launcho.ir/api',
                          'https://user@launcho.ir/api', 'https://launcho.ir/api?token=secret']:
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                FinancialOffer.model_validate({**offer, 'source': {**offer['source'], 'reference': reference}})
        with self.assertRaises(ValueError):
            FinancialOffer.model_validate({**offer, 'source': {**offer['source'], 'approvalEvidence': None}})

    def test_persistent_state_suppresses_even_without_history(self):
        for state in [{'anyFinancialOfferShown': True}, {'shownOfferIds': ['different_offer']},
                      {'financialOffersDeclined': True}, {'rejectedOfferIds': ['demo_campaign']}]:
            with self.subTest(state=state):
                # Serialization simulates the boundary, not SQLite/restart owned by the core.
                state = json.loads(json.dumps(state))
                self.assertEqual(self.filter([OFFER], state=state), [])
        self.assertEqual(len(self.filter([OFFER], state={})), 1)
        self.assertEqual(len(self.filter([OFFER], state={'rejectedOfferIds': ['different_offer']})), 1)

    def test_adapter_needs_explicit_state_and_does_not_forward_message(self):
        gateway = LocalMockGateway('http://127.0.0.1:8001')
        with patch.object(gateway, 'read', return_value={'offers': [OFFER]}) as read:
            kwargs = dict(message='قسطی می خوام؛ شماره تست 09123456789', step='review_ready')
            self.assertEqual(gateway.match_price_offers('shop', **kwargs), {'offers': []})
            read.assert_not_called()
            result = gateway.match_price_offers('shop', offer_state={}, **kwargs)
            self.assertEqual(result['offers'][0]['offerId'], 'demo_campaign')
            self.assertNotIn('09123456789', json.dumps(read.call_args.kwargs))
            self.assertEqual(read.call_args.kwargs['payload']['step'], 'review_ready')
            self.assertNotIn('message', read.call_args.kwargs['payload'])

    def test_live_adapter_rejects_simulation_and_malformed_data(self):
        gateway = LaunchoDraftGateway('https://launcho.ir', 'synthetic-token')
        with patch.object(gateway, 'read', return_value={'offers': [OFFER]}):
            self.assertEqual(gateway.match_checkout_offers('shop', 3, message='قسطی می خوام',
                             step='review_ready', offer_state={}), {'offers': []})
        with patch.object(gateway, 'read', return_value={'offers': [{'line': 'بدون مدرک'}]}):
            with self.assertRaises(GatewayUnavailable):
                gateway.match_checkout_offers('shop', 3, message='قسطی می خوام',
                                             step='review_ready', offer_state={})
        with self.assertRaises(GatewayUnavailable):
            gateway.match_checkout_offers('shop', 3, message='قسطی می خوام',
                                         step='review_ready', offer_state={'anyFinancialOfferShown': 'false'})

    def test_published_schemas_match_runtime_models(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / 'docs/examples'
        for name, model in [('launcho-offer-request-v1', OfferRequest),
                            ('launcho-offer-v1', FinancialOffer), ('launcho-offer-state-v1', OfferState)]:
            self.assertEqual(json.loads((root / (name + '.schema.json')).read_text()), model.model_json_schema())

    def test_legacy_positional_plan_and_numeric_stage_do_not_crash(self):
        gateway = LocalMockGateway('http://127.0.0.1:8001')
        with patch.object(gateway, 'read') as read:
            self.assertEqual(gateway.match_price_offers('shop', 3, step=4), {'offers': []})
            read.assert_not_called()
