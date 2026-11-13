"""Exercise the real mock routes and chat boundary without network or AI calls."""
import os
os.environ.setdefault('AI_API_KEY', 'test-placeholder')
os.environ.setdefault('AI_BASE_URL', 'https://example.invalid/v1')
os.environ.setdefault('AI_MODEL_NAME', 'test-model')

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.mock_launcho import app as mock_app, fixture
from app.services import ai_service
from app.services.conversation_core import ConversationCore
from app.services.draft_gateway import LocalMockGateway
from app.services.session_store import SessionStore


class MockDemoTests(unittest.TestCase):
    def setUp(self):
        self.mock = TestClient(mock_app)
        self.client = TestClient(app)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.mock.close)
        self.addCleanup(self.client.close)
        self.gateway = LocalMockGateway('http://127.0.0.1:8001')
        self.core = ConversationCore(SessionStore(Path(self.tmp.name) / 'session.sqlite3'), self.gateway)

    def assert_no_sample_amounts(self, value):
        text = json.dumps(value, ensure_ascii=False)
        for amount in (15000000, 5000000, 2400000, 4000000, 4800000, 8000000,
                       9600000, 50000, 1200000, 4200000, 3750000, 1250000):
            for digits in (str(amount), f'{amount:,}'):
                self.assertNotIn(digits, text)
                self.assertNotIn(digits.translate(str.maketrans('0123456789,', '۰۱۲۳۴۵۶۷۸۹٬')), text)

    def test_mock_contract_is_explicitly_simulated_and_authenticated(self):
        endpoints = [('/pricing', None), ('/service-info', None),
                     ('/signup-options?kind=shop', None),
                     ('/offers/match', dict(kind='shop', step='review_ready', objections=['price'],
                                           needs=['low_upfront'], discountAlreadyShown=False))]
        for path, body in endpoints:
            with self.subTest(path=path):
                method = 'POST' if body else 'GET'
                kwargs = {'json': body} if body else {}
                self.assertEqual(self.mock.request(method, path, **kwargs).status_code, 401)
                response = self.mock.request(method, path, headers={'Authorization': 'Bearer local-simulation'}, **kwargs)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()['simulation'])
                self.assertIn('آزمایشی', response.json()['notice'])
        pricing = self.mock.get('/pricing', headers={'Authorization': 'Bearer local-simulation'}).json()
        self.assertEqual(pricing['data'], fixture['pricing'])  # Contract practice still works.
        offer = fixture['offers'][0]
        self.assertIn('آزمایشی', offer['title'])
        self.assertIn('برای خرید اعتبار ندارد', offer['line'])
        self.assertNotIn('مرحلهٔ پرداخت', offer['line'])

    def test_pricing_separates_website_and_shop_without_changing_shared_data(self):
        headers = {'Authorization': 'Bearer local-simulation'}
        responses = {}
        for kind, expected_part in [('shop', 3750000), ('website', 1250000)]:
            with self.subTest(kind=kind):
                result = self.mock.get('/pricing', params={'kind': kind}, headers=headers)
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.json()['simulation'])
                data = result.json()['data']
                responses[kind] = data
                self.assertEqual(data['kind'], kind)
                self.assertEqual(data['installment']['monthlyPart'], expected_part)
                self.assertEqual(data['installment']['scope'], 'setup_only')
                self.assertIn('اشتراک و هزینهٔ دامنه', data['installment']['line'])
                self.assertNotIn('متن آماده لانچو', data['installment']['line'])
                self.assertNotIn('serviceDetails', data)
                self.assertEqual(next(d['annualFee'] for d in data['domains'] if d['tld'] == 'com'), 4200000)
        self.assertEqual(responses['website']['plans'], responses['shop']['plans'])
        self.assertIn('بدون کاتالوگ، سبد خرید و درگاه', responses['website']['planIncludes'][0])
        self.assertNotIn('اینماد', ' '.join(responses['website']['setupIncludes']))
        self.assertIn('اینماد', ' '.join(responses['shop']['setupIncludes']))
        # Scoped requests must not mutate the shared fixture or erase the other service.
        unscoped = self.mock.get('/pricing', headers=headers).json()['data']
        self.assertEqual(unscoped, fixture['pricing'])
        self.assertEqual(set(unscoped['serviceDetails']), {'shop', 'website'})
        self.assertNotIn('installment', unscoped)
        self.assertFalse(unscoped['giftUsage']['rollover'])
        self.assertEqual(self.mock.get('/pricing?kind=other', headers=headers).status_code, 422)
        self.assertEqual(self.mock.get('/pricing?kind=website').status_code, 401)

    def test_demo_signup_options_do_not_claim_real_catalog_availability(self):
        for kind in ['shop', 'website']:
            with self.subTest(kind=kind):
                result = self.mock.get('/signup-options', params={'kind': kind},
                                       headers={'Authorization': 'Bearer local-simulation'})
                self.assertEqual(result.status_code, 200)
                data = result.json()['data']
                self.assertEqual(data['availability'], 'unavailable')
                self.assertIn('سایت واقعی نیست', data['notice'])
                self.assertEqual(data['templates'], [])
                self.assertEqual(data['businessCategories'], [])

    def test_offer_period_only_accepts_supported_plans(self):
        body = dict(kind='shop', step='review_ready', objections=['price'],
                    needs=['low_upfront'], discountAlreadyShown=False)
        headers = {'Authorization': 'Bearer local-simulation'}
        for period in [None, 3, 6, 12]:
            with self.subTest(period=period):
                result = self.mock.post('/offers/match', json={**body, 'planMonths': period}, headers=headers)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()['data']['offers'][0]['offerId'], 'demo_campaign')
        for period in [0, 1, 5, 120, 121]:
            with self.subTest(period=period):
                result = self.mock.post('/offers/match', json={**body, 'planMonths': period}, headers=headers)
                self.assertEqual(result.status_code, 422)

    def test_session_chat_uses_actual_mock_without_exposing_prices(self):
        def read(url, **kwargs):
            kwargs.pop('timeout', None)
            kwargs.pop('follow_redirects', None)
            return self.mock.get(url.replace(self.gateway.base_url, ''), **kwargs)

        def post(url, **kwargs):
            kwargs.pop('timeout', None)
            kwargs.pop('follow_redirects', None)
            return self.mock.post(url.replace(self.gateway.base_url, ''), **kwargs)

        with patch('app.api.routes.get_core', return_value=self.core), \
             patch('app.services.draft_gateway.httpx.get', side_effect=read), \
             patch('app.services.draft_gateway.httpx.post', side_effect=post), \
             patch.object(ai_service.client.chat.completions, 'create') as model:
            session = self.client.post('/api/sessions').json()
            headers = {'X-Session-Token': session['sessionToken']}
            body = {'sessionId': session['sessionId'], 'message': 'هزینه برام زیاده'}
            first = self.client.post('/api/chat', headers=headers, json=body)
            self.assertEqual(first.status_code, 200)
            self.assertNotIn('پیشنهاد آزمایشی', first.json()['reply'])
            self.assertIn('https://launcho.ir/pricing', first.json()['reply'])
            second = self.client.post('/api/chat', headers=headers, json=body)
            self.assertEqual(second.status_code, 200)
            self.assertNotIn('پیشنهاد آزمایشی', second.json()['reply'])
            saved = self.client.get('/api/sessions/' + session['sessionId'], headers=headers)
            self.assertEqual(saved.status_code, 200)
            self.assert_no_sample_amounts([first.json(), second.json(), saved.json()])
            self.assertIsNone(self.core.estimate({'kind': 'shop'}))
            model.assert_not_called()

            model.return_value = NS(choices=[NS(message=NS(content='برای فروش پوشاک، رنگ و سایز را آماده کنید.', tool_calls=[]))])
            mixed = self.client.post('/api/chat', headers=headers, json={
                **body, 'message': 'برای فروش پوشاک چه امکاناتی دارید و هزینه چقدر است؟'})
            self.assertEqual(mixed.status_code, 200)
            self.assertIn('رنگ و سایز', mixed.json()['reply'])
            self.assertIn('https://launcho.ir/pricing', mixed.json()['reply'])
            self.assert_no_sample_amounts(model.call_args.kwargs)
            self.assert_no_sample_amounts(mixed.json())

    def test_legacy_stateless_chat_has_no_sample_prices_or_demo_offer(self):
        with patch.object(ai_service.client.chat.completions, 'create') as model:
            result = self.client.post('/api/chat', json={'message': 'قیمت و جشنواره دارید؟'})
        self.assertEqual(result.status_code, 200)
        self.assertIn('https://launcho.ir/pricing', result.json()['reply'])
        self.assertNotIn('پیشنهاد آزمایشی', result.json()['reply'])
        self.assert_no_sample_amounts(result.json())
        model.assert_not_called()

    def test_offer_text_cannot_bypass_sample_price_guard(self):
        for line in ['اشتراک ۲۴۰۰۰۰۰ تومان', 'قسط 3750000 تومان', 'دامنه رایگان']:
            with self.subTest(line=line):
                reply = ai_service.price_guidance('هزینه چقدر است؟',
                    {'demoOffers': [{'id': 'demo_campaign', 'line': line}]}, [])
                self.assertNotIn(line, reply)
                self.assertNotIn('پیشنهاد آزمایشی', reply)

    def test_subscription_discount_is_distinct_from_campaign_or_coupon(self):
        with patch.object(ai_service.client.chat.completions, 'create') as model:
            result = self.client.post('/api/chat', json={'message': 'اشتراک سالانه تخفیف دارد؟'})
        self.assertEqual(result.status_code, 200)
        reply = result.json()['reply']
        self.assertIn('دوره‌های بلندتر اشتراک در تعرفهٔ رسمی تخفیف دارند', reply)
        self.assertIn('جشنواره یا کد تخفیف فعالی برای تأیید در دسترسم نیست', reply)
        self.assert_no_sample_amounts(reply)
        model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
