import os
os.environ.setdefault('AI_API_KEY', 'test-placeholder')
os.environ.setdefault('AI_BASE_URL', 'https://example.invalid/v1')
os.environ.setdefault('AI_MODEL_NAME', 'test-model')
import unittest
from unittest.mock import patch
import httpx
from app.services.financial_context import financial_context
from app.services import ai_service
from app.services.draft_gateway import LocalMockGateway, LaunchoDraftGateway, GatewayUnavailable


class FinancialTests(unittest.TestCase):
    def test_question_is_not_objection_or_low_upfront(self):
        for message in ['قیمت چنده؟', 'تخفیف دارید؟', 'گران نیست', 'بودجه دارم']:
            self.assertEqual(financial_context(message)['objections'], [])
        self.assertEqual(financial_context('هزینه خیلی بالاست')['needs'], [])

    def test_budget_objection_without_model(self):
        with patch.object(ai_service.client.chat.completions, 'create') as model:
            for message in ['بودجه ندارم', 'پول ندارم', 'گرونه']:
                reply, _ = ai_service.generate_turn(message)
                self.assertIn('https://launcho.ir/pricing', reply)
        model.assert_not_called()

    def test_explicit_installment_and_service_kind_payload(self):
        gateway = LocalMockGateway('http://127.0.0.1:8001')
        with patch.object(gateway, 'read', return_value={'offers': []}) as read:
            gateway.match_price_offers('website', message='قسطی می خوام', step='collecting_preferences', offer_state={})
        self.assertEqual(read.call_args.kwargs['payload'], {
            'kind': 'website', 'step': 'collecting_preferences', 'objections': ['price'],
            'needs': ['low_upfront'], 'discountAlreadyShown': False})

    def test_contextless_core_calls_never_invent_eligibility(self):
        for gateway, call in [(LocalMockGateway('http://127.0.0.1:8001'), 'match_price_offers'),
                              (LaunchoDraftGateway('https://example.invalid', 'test'), 'match_checkout_offers')]:
            with patch.object(gateway, 'read') as read:
                args = ('shop', 3) if call == 'match_checkout_offers' else ('shop',)
                self.assertEqual(getattr(gateway, call)(*args), {'offers': []})
            read.assert_not_called()

    def test_shown_rejected_and_changed_mind(self):
        gateway = LocalMockGateway('http://127.0.0.1:8001')
        history = [{'role': 'user', 'content': 'پیشنهاد نمی خوام'}]
        with patch.object(gateway, 'read', return_value={'offers': []}) as read:
            gateway.match_price_offers('shop', message='قسطی می خوام', history=history, step='review_ready', offer_state={})
            read.assert_not_called()
            gateway.match_price_offers('shop', message='دوباره اقساط را بررسی کن', history=history, step='review_ready', offer_state={})
            read.assert_called_once()
        history = [{'role': 'assistant', 'content': 'پیشنهاد لانچو — قبلی'}]
        with patch.object(gateway, 'read') as read:
            gateway.match_price_offers('shop', message='قسطی می خوام', history=history, step='review_ready', offer_state={})
            read.assert_not_called()

    def test_installment_guidance_no_unverified_offer(self):
        reply = ai_service.price_guidance('قسطی می خوام', {'checkoutOffer': 'تخفیف قطعی ۵۰ درصد'}, [])
        self.assertIn('https://launcho.ir/installments', reply)
        self.assertNotIn('۵۰', reply)
        self.assertNotIn('پیشنهاد لانچو', reply)

    def test_outage_does_not_become_empty_success(self):
        gateway = LocalMockGateway('http://127.0.0.1:8001')
        with patch('app.services.draft_gateway.httpx.post', side_effect=httpx.ConnectError('offline')):
            with self.assertRaises(GatewayUnavailable):
                gateway.match_price_offers('shop', message='قسطی می خوام', step='review_ready', offer_state={})
        reply = ai_service.price_guidance('قسطی می خوام', {}, [])
        self.assertIn('https://launcho.ir/installments', reply)
