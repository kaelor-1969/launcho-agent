"""Persistent financial display, exact replay and lifecycle regression tests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest
from unittest.mock import Mock, patch

from test_conversation_core import FakeGateway, CHOICES
from test_offer_contract import OFFER
from app.models.schemas import ChatResponse, ConfirmRequest
from app.services.conversation_core import ConversationCore
from app.services.offer_contract import OfferState
from app.services.session_store import CoreError, SessionStore


class FinancialCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'sessions.sqlite3'
        self.gateway = FakeGateway()
        self.gateway.mode = 'local_mock'
        self.gateway.match_price_offers = Mock(return_value={'offers': [deepcopy(OFFER)]})
        self.core = ConversationCore(SessionStore(self.path), self.gateway, lambda *args: ('پاسخ', {}))
        self.session = self.core.create_session()
        self.sid = self.session['sessionId']
        self.token = self.session['sessionToken']
        self.core.edit(self.sid, self.token, 0, CHOICES)

    def chat(self, message='بودجه کمه، اقساط می‌خواهم', request_id=None):
        return self.core.chat(self.sid, self.token, message, request_id)

    def state(self):
        return OfferState.model_validate_json(self.core.store.get(self.sid, self.token)['offer_state'])

    def test_context_is_redacted_current_message_separate_and_metadata_survives(self):
        self.chat('سلام')
        result = self.chat('بودجه کمه، اقساط می‌خواهم. رمز عبور: SecretMarker')
        context = self.gateway.match_price_offers.call_args.kwargs
        self.assertNotIn('SecretMarker', context['message'])
        self.assertEqual(context['history'][0]['content'], 'سلام')
        self.assertEqual(len(context['history']), 2)
        self.assertEqual(context['step'], 'review_ready')
        self.assertEqual(context['offer_state'], OfferState().model_dump())
        self.assertEqual(result['financialOffer']['offerId'], OFFER['offerId'])
        self.assertIn(OFFER['displayText'], result['reply'])
        self.assertEqual(ChatResponse.model_validate(result).financialOffer.offerId, OFFER['offerId'])
        self.assertEqual(self.state().shownOfferIds, [OFFER['offerId']])

    def test_history_rolloff_restart_exact_retry_and_session_isolation(self):
        first = self.chat(request_id='first-request')
        for number in range(8):
            self.chat(f'سلام {number}')
        self.core = ConversationCore(SessionStore(self.path), self.gateway, lambda *args: ('پاسخ', {}))
        self.assertEqual(self.chat(request_id='first-request'), first)
        self.assertNotIn('financialOffer', self.chat())
        self.gateway.match_price_offers.assert_called_once()
        with self.assertRaises(CoreError) as conflict:
            self.chat('پیام متفاوت', request_id='first-request')
        self.assertEqual(conflict.exception.code, 'request_conflict')
        other = self.core.create_session()
        self.core.edit(other['sessionId'], other['sessionToken'], 0, CHOICES)
        result = self.core.chat(other['sessionId'], other['sessionToken'], 'بودجه کمه اقساط می‌خواهم')
        self.assertIn('financialOffer', result)

    def test_decline_persists_after_history_rolloff_and_restart(self):
        self.chat('پیشنهاد نمی‌خواهم')
        for number in range(8):
            self.chat(f'سلام {number}')
        self.core = ConversationCore(SessionStore(self.path), self.gateway, lambda *args: ('پاسخ', {}))
        self.chat()
        self.assertTrue(self.state().financialOffersDeclined)
        self.gateway.match_price_offers.assert_not_called()

    def test_decline_records_displayed_id(self):
        self.chat()
        self.chat('پیشنهاد نمی‌خواهم')
        self.assertEqual(self.state().rejectedOfferIds, [OFFER['offerId']])

    def test_bad_expired_wrong_kind_and_duplicate_offers_never_commit(self):
        cases = [
            {'offers': 'legacy string'},
            {'offers': [{'type': 'discount', 'displayText': 'ناقص'}]},
            {'offers': [{**OFFER, 'expiresAt': '2000-01-01T00:00:00Z'}]},
            {'offers': [{**OFFER, 'kind': 'website'}]},
            {'offers': [{**OFFER, 'eligibleStages': ['draft_created']}]},
            {'offers': [{**OFFER, 'planMonths': [12]}]},
            {'offers': [OFFER, OFFER]},
        ]
        for response in cases:
            with self.subTest(response=response):
                self.gateway.match_price_offers.return_value = response
                self.assertNotIn('financialOffer', self.chat())
                self.assertFalse(self.state().anyFinancialOfferShown)

    def test_expiry_rechecked_at_commit(self):
        original = self.core.financial_offer
        def expired_after_transport(*args):
            result = original(*args)
            result['expiresAt'] = '2000-01-01T00:00:00Z'
            return result
        with patch.object(self.core, 'financial_offer', side_effect=expired_after_transport):
            self.assertNotIn('financialOffer', self.chat())
        self.assertFalse(self.state().anyFinancialOfferShown)

    def test_model_failure_and_database_failure_do_not_mark_shown(self):
        self.core.model = Mock(side_effect=RuntimeError('model failure'))
        with self.assertRaises(RuntimeError):
            self.chat()
        self.gateway.match_price_offers.assert_not_called()
        self.core.model = lambda *args: ('پاسخ', {})
        with self.core.store.transaction() as db:
            db.execute("CREATE TRIGGER fail_reply BEFORE INSERT ON chat_responses "
                       "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.chat(request_id='rollback-request')
        self.assertFalse(self.state().anyFinancialOfferShown)
        self.assertEqual(json.loads(self.core.store.get(self.sid, self.token)['history']), [])
        with self.core.store.transaction() as db:
            db.execute('DROP TRIGGER fail_reply')
        self.assertIn('financialOffer', self.chat(request_id='rollback-request'))

    def test_concurrent_chat_can_commit_only_one_offer(self):
        entered, release = Event(), Event()
        def slow_model(*args):
            entered.set()
            self.assertTrue(release.wait(5))
            return 'پاسخ', {}
        self.core.model = slow_model
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.chat, request_id='same-request')
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaises(CoreError) as busy:
                    self.chat(request_id='same-request')
                self.assertEqual(busy.exception.code, 'conversation_busy')
            finally:
                release.set()
            result = first.result(5)
        self.assertEqual(self.chat(request_id='same-request'), result)
        self.gateway.match_price_offers.assert_called_once()

    def test_lifecycle_uses_review_revision_expiry_and_success(self):
        def stage():
            with self.core.store.transaction() as db:
                row = self.core.store.authenticate(db, self.sid, self.token)
                return self.core.financial_stage(db, row)
        self.assertEqual(stage(), 'review_ready')
        review = self.core.prepare_review(self.sid, self.token, 1)
        self.assertEqual(stage(), 'awaiting_confirmation')
        with self.core.store.transaction() as db:
            db.execute('UPDATE reviews SET expires=0 WHERE id=?', (review['reviewId'],))
        self.assertEqual(stage(), 'review_ready')
        with self.core.store.transaction() as db:
            db.execute("UPDATE reviews SET status='unknown' WHERE id=?", (review['reviewId'],))
        self.assertEqual(stage(), 'review_ready')
        self.gateway.mode = 'test_mock'
        request = ConfirmRequest(**{key: review[key] for key in ('revision', 'reviewId', 'confirmationToken')}, confirmed=True)
        self.core.confirm(self.sid, self.token, request)
        self.assertEqual(stage(), 'draft_created')
        with self.core.store.transaction() as db:
            db.execute('UPDATE sessions SET revision=revision+1 WHERE id=?', (self.sid,))
        self.assertEqual(stage(), 'review_ready')

    def test_guidance_and_collecting_preferences(self):
        new = self.core.create_session()
        with self.core.store.transaction() as db:
            row = self.core.store.authenticate(db, new['sessionId'], new['sessionToken'])
            self.assertEqual(self.core.financial_stage(db, row), 'guidance')
        self.core.edit(new['sessionId'], new['sessionToken'], 0, {'businessName': 'نمونه'})
        with self.core.store.transaction() as db:
            row = self.core.store.authenticate(db, new['sessionId'], new['sessionToken'])
            self.assertEqual(self.core.financial_stage(db, row), 'collecting_preferences')

    def test_live_display_requires_explicit_enable_and_rejects_simulation(self):
        self.gateway.mode = 'live'
        self.assertNotIn('financialOffer', self.chat())
        self.gateway.match_price_offers.assert_not_called()
        with patch.dict('os.environ', {'LAUNCHO_ENABLE_FINANCIAL_OFFERS': '1'}):
            self.assertNotIn('financialOffer', self.chat())
        self.assertFalse(self.state().anyFinancialOfferShown)

    def test_live_canonical_checkout_and_http_replay(self):
        from fastapi.testclient import TestClient
        from app.main import app
        self.gateway.mode = 'live'
        del self.gateway.match_price_offers
        official = {**OFFER, 'simulation': False, 'source': {
            'type': 'official_api', 'reference': 'https://launcho.ir/api/offers',
            'approvalEvidence': 'synthetic-transport-fixture'}}
        self.gateway.match_checkout_offers = Mock(return_value={'offers': [official]})
        body = {'sessionId': self.sid, 'requestId': 'b1823417-5dd5-44e4-ab48-ea9f6dd60cd8',
                'message': 'بودجه کمه اقساط می‌خواهم'}
        with patch.dict('os.environ', {'LAUNCHO_ENABLE_FINANCIAL_OFFERS': '1'}), \
                patch('app.api.routes.get_core', return_value=self.core), TestClient(app) as client:
            denied = client.post('/api/chat', json=body)
            self.assertEqual(denied.status_code, 404)
            self.gateway.match_checkout_offers.assert_not_called()
            first = client.post('/api/chat', json=body, headers={'X-Session-Token': self.token})
            second = client.post('/api/chat', json=body, headers={'X-Session-Token': self.token})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()['financialOffer']['source'], official['source'])
        self.assertEqual(first.headers['cache-control'], 'no-store')
        self.gateway.match_checkout_offers.assert_called_once()

    def test_expired_review_is_rechecked_after_offer_transport(self):
        review = self.core.prepare_review(self.sid, self.token, 1)
        offered = {**OFFER, 'eligibleStages': ['awaiting_confirmation']}
        def transport(*args, **kwargs):
            self.assertEqual(kwargs['step'], 'awaiting_confirmation')
            with self.core.store.transaction() as db:
                db.execute('UPDATE reviews SET expires=0 WHERE id=?', (review['reviewId'],))
            return {'offers': [offered]}
        self.gateway.match_price_offers.side_effect = transport
        self.assertNotIn('financialOffer', self.chat())
        self.assertFalse(self.state().anyFinancialOfferShown)

    def test_cleanup_cascades_durable_responses_and_state_survives_backup(self):
        first = self.chat(request_id='backup-request')
        backup = Path(self.temp.name) / 'backup.sqlite3'
        self.core.store.backup(backup)
        restored = ConversationCore(SessionStore(backup), self.gateway, lambda *args: ('unused', {}))
        self.assertEqual(restored.chat(self.sid, self.token, 'بودجه کمه، اقساط می‌خواهم', 'backup-request'), first)
        with self.core.store.transaction() as db:
            db.execute('UPDATE sessions SET expires=0 WHERE id=?', (self.sid,))
        self.core.store.cleanup()
        with self.core.store.transaction() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM chat_responses').fetchone()[0], 0)

    def test_legacy_schema_display_marker_is_migrated(self):
        with self.core.store.transaction() as db:
            db.execute('INSERT INTO shown_local_offers VALUES (?)', (self.sid,))
            db.execute('ALTER TABLE sessions DROP COLUMN offer_state')
        self.core.store = SessionStore(self.path)
        self.assertTrue(self.state().anyFinancialOfferShown)
        self.assertNotIn('financialOffer', self.chat())

    def test_legacy_decline_history_is_preserved(self):
        history = [{'role': 'user', 'content': 'پیشنهاد نمی‌خواهم'}, {'role': 'assistant', 'content': 'باشه'}]
        with self.core.store.transaction() as db:
            db.execute('UPDATE sessions SET history=? WHERE id=?', (json.dumps(history), self.sid))
        self.assertTrue(self.state().financialOffersDeclined)
