import os
os.environ['AI_API_KEY']='test-placeholder'
os.environ['AI_BASE_URL']='https://example.invalid/v1'
os.environ['AI_MODEL_NAME']='test-model'

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from threading import Event
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

try:
    import httpx
except ImportError:
    import httpx2 as httpx

from pydantic import ValidationError
from app.core.privacy import redact
from app.main import app
from app.models.schemas import ConfirmRequest, Preferences
from app.services.conversation_core import ConversationCore
from app.services.draft_gateway import ExistingReadOnlyGateway, GatewayRejected, LaunchoDraftGateway
from app.services.session_store import SessionStore, CoreError
from app.services import ai_service


class FakeGateway:
    mode='test_mock'
    can_create=True
    def __init__(self):
        self.calls=[]; self.results={}; self.fail_once=False; self.entered=None; self.release=None
    def get_pricing(self):
        return {'ok':True,'data':{'currency':'toman','setupFees':{'shop':15000000,'website':5000000},
            'plans':[{'months':3,'price':2400000},{'months':6,'price':4000000}],
            'domains':[{'tld':'ir','annualFee':0}]}}
    def get_signup_options(self,kind):
        return {'ok':True,'data':{'kind':kind,'businessCategories':[{'id':'fashion','label':'پوشاک'}],
            'templates':[{'id':'classic','available':True},{'id':'unfinished','available':False}]}}
    def create_signup_draft(self,payload,idempotency_key):
        self.calls.append((payload.copy(),idempotency_key))
        result=self.results.setdefault(idempotency_key,{'ref':'sd_mockreference',
            'confirmUrl':'https://launcho.ir/start?signup=sd_mockreference','status':'draft',
            'expiresAt':(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),
            'quote':{'total':17400000,'isFinal':False}})
        if self.entered:
            self.entered.set();self.release.wait(5)
        if self.fail_once:
            self.fail_once=False
            raise TimeoutError('Created upstream but response was lost')
        return {'ok':True,'data':result}


CHOICES={'businessName':'فروشگاه نمونه','category':'fashion','planMonths':3,
         'template':'classic','domain':{'ownDomain':'example.ir'}}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.gateway=FakeGateway()
        self.core=ConversationCore(SessionStore(Path(self.tmp.name)/'sessions.sqlite3'),self.gateway,
                                   model=lambda *args:('پاسخ تست',{}))
        session=self.core.create_session()
        self.sid,self.token=session['sessionId'],session['sessionToken']
    def tearDown(self):self.tmp.cleanup()
    def edited(self):return self.core.edit(self.sid,self.token,0,CHOICES)
    def review(self):
        revision=self.edited()['revision']
        return self.core.prepare_review(self.sid,self.token,revision)
    def request(self,review,**overrides):
        return ConfirmRequest.model_validate({k:review[k] for k in ['revision','reviewId','confirmationToken']}|{'confirmed':True}|overrides)
    def assert_core_error(self,code,function):
        with self.assertRaises(CoreError) as error:function()
        self.assertEqual(error.exception.code,code)

    def test_owner_token_and_storage_restart(self):
        self.edited()
        fresh=ConversationCore(SessionStore(self.core.store.path),self.gateway)
        self.assertEqual(fresh.get_session(self.sid,self.token)['preferences']['businessName'],CHOICES['businessName'])
        self.assert_core_error('session_not_found',lambda:fresh.get_session(self.sid,'wrong'))
        text=Path(self.core.store.path).read_bytes()
        self.assertNotIn(self.token.encode(),text)

    def test_live_draft_transport_preserves_key_and_status_is_session_owned(self):
        gateway = LaunchoDraftGateway('https://example.invalid/api/assistant/v1', 'test-token')
        self.core.gateway = gateway
        draft = self.gateway.create_signup_draft(CHOICES, 'fixture')
        endpoint = 'https://example.invalid/api/assistant/v1/signup-drafts'
        payload = httpx.Response(201, json=draft, request=httpx.Request('POST', endpoint))
        with patch.object(gateway, 'get_signup_options', self.gateway.get_signup_options), \
                patch.object(gateway, 'get_pricing', self.gateway.get_pricing), \
                patch('app.services.draft_gateway.httpx.post', return_value=payload) as send:
            revision = self.core.edit(self.sid, self.token, 0, CHOICES)['revision']
            review = self.core.prepare_review(self.sid, self.token, revision)
            request = ConfirmRequest(**{field:review[field] for field in ('revision','reviewId','confirmationToken')},
                                     confirmed=True)
            self.core.confirm(self.sid, self.token, request)
            self.core.confirm(self.sid, self.token, request)
        send.assert_called_once()
        self.assertEqual(send.call_args.args, (endpoint,))
        self.assertTrue(send.call_args.kwargs['headers']['Idempotency-Key'])
        with patch.object(gateway, 'get_draft_status', return_value={'ref':'sd_mockreference','status':'paid'}) as read:
            with self.assertRaises(CoreError):
                self.core.draft_status(self.sid, 'invalid-token')
            read.assert_not_called()
            self.assertEqual(self.core.draft_status(self.sid, self.token), {'status':'paid'})
        read.assert_called_once_with('sd_mockreference')
        with patch.object(gateway, 'match_checkout_offers', return_value={'offers':[
            {'type':'discount','line':'پیشنهاد منقضی','expiresAt':'2000-01-01T00:00:00Z'},
            {'type':'payment_option','line':'پرداخت قسطی در فرم'},
        ]}) as match:
            self.assertIsNone(self.core.checkout_offer('هزینه بالاست', [], {'kind':'shop'}))
            match.assert_not_called()
            self.assertEqual(self.core.checkout_offer('هزینه بالاست', [], {'kind':'shop', **CHOICES}),
                             'پرداخت قسطی در فرم')
        match.assert_called_once_with('shop', 3)

    def test_chat_retry_replays_saved_answer(self):
        calls = []
        def model(*args):
            calls.append(args)
            return 'پاسخ قبلی', {}
        self.core.model = model
        request_id = 'b1823417-5dd5-44e4-ab48-ea9f6dd60cd8'
        first = self.core.chat(self.sid, self.token, 'سؤال اول', request_id)
        replay = self.core.chat(self.sid, self.token, 'سؤال اول', request_id)
        self.assertEqual(first, replay)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.core.get_session(self.sid, self.token)['history']), 2)
        self.assert_core_error('request_conflict',
                               lambda: self.core.chat(self.sid, self.token, 'متن دیگر', request_id))

    def test_redaction_before_model_and_history(self):
        captured=[]
        def model(*args):captured.append(args);return 'one-time passcode: ۱۲۳۴۵۶',{}
        self.core.model=model
        self.core.chat(self.sid,self.token,'شماره من ۰۹۱۲۳۴۵۶۷۸۹ و گذرواژه: SampleSecret و one-time passcode: ۷۸۹۰۱۲')
        self.core.chat(self.sid,self.token,'ادامه')
        stored=self.core.get_session(self.sid,self.token)
        representation=json.dumps([captured,stored],ensure_ascii=False)
        for secret in ['۰۹۱۲۳۴۵۶۷۸۹','۱۲۳۴۵۶','09123456789','123456','SampleSecret','۷۸۹۰۱۲']:
            self.assertNotIn(secret,representation)
        self.assertTrue(captured[1][1])

    def test_existing_history_is_scrubbed_on_access(self):
        old = [{'role':'user','content':'گذرواژه: LegacySecret'},
               {'role':'assistant','content':'one-time passcode: 654321'}]
        with self.core.store.transaction() as db:
            db.execute('UPDATE sessions SET history=? WHERE id=?', (json.dumps(old), self.sid))
        history = self.core.get_session(self.sid,self.token)['history']
        self.assertEqual([turn['content'] for turn in history],
                         ['گذرواژه: [پوشانده شد]', 'one-time passcode: [پوشانده شد]'])
        with self.core.store.transaction() as db:
            row = db.execute('SELECT history FROM sessions WHERE id=?', (self.sid,)).fetchone()
        self.assertEqual(json.loads(row['history']), history)

    def test_safe_model_update_is_saved(self):
        self.core.model=lambda *args:('انتخاب دریافت شد',CHOICES)
        result=self.core.chat(self.sid,self.token,'نام کسب‌وکار را ثبت کن')
        self.assertEqual(result['preferences']['template'],'classic')
        self.assertEqual(result['revision'],1)
        self.assertEqual(self.gateway.calls,[])

    def test_invalid_model_update_preserves_state(self):
        self.core.model=lambda *args:('ok',{'businessName':'09123456789'})
        result=self.core.chat(self.sid,self.token,'ادامه')
        self.assertEqual(result['preferences'],{'kind':'shop'})

    def test_unavailable_option_and_stale_edit(self):
        for update in [{'category':'unknown'},{'template':'unfinished'},{'planMonths':12}]:
            with self.assertRaises(CoreError):self.core.edit(self.sid,self.token,0,update)
        self.edited()
        self.assert_core_error('stale_revision',lambda:self.core.edit(self.sid,self.token,0,{'planMonths':6}))

    def test_no_review_with_missing_fields(self):
        self.assert_core_error('incomplete_preferences',lambda:self.core.prepare_review(self.sid,self.token,0))

    def test_button_confirmation_and_duplicate_return_same_result(self):
        review=self.review()
        self.assertEqual(self.gateway.calls,[])
        request=self.request(review)
        first=self.core.confirm(self.sid,self.token,request)
        second=self.core.confirm(self.sid,self.token,request)
        self.assertEqual(first['ref'],second['ref'])
        self.assertTrue(second['replayed'])
        self.assertEqual(len(self.gateway.calls),1)
        payload=self.gateway.calls[0][0]
        self.assertEqual(payload['domain'],{'ownDomain':'example.ir'})
        self.assertNotIn('mobile',payload)

    def test_text_yes_never_creates_draft(self):
        self.review()
        self.core.chat(self.sid,self.token,'بله پیش‌نویس را بساز')
        self.assertEqual(self.gateway.calls,[])

    def test_false_confirmation(self):
        review=self.review()
        self.assert_core_error('confirmation_required',lambda:self.core.confirm(self.sid,self.token,self.request(review,confirmed=False)))
        self.assertEqual(self.gateway.calls,[])

    def test_tampered_and_cross_session_confirmation(self):
        review=self.review()
        self.assert_core_error('stale_confirmation',lambda:self.core.confirm(self.sid,self.token,self.request(review,confirmationToken='x'*40)))
        other=self.core.create_session()
        self.assert_core_error('stale_confirmation',lambda:self.core.confirm(other['sessionId'],other['sessionToken'],self.request(review)))
        self.assertEqual(self.gateway.calls,[])

    def test_edit_invalidates_confirmation(self):
        review=self.review()
        self.core.edit(self.sid,self.token,review['revision'],{'planMonths':6})
        self.assert_core_error('stale_confirmation',lambda:self.core.confirm(self.sid,self.token,self.request(review)))
        self.assertEqual(self.gateway.calls,[])

    def test_review_refresh_invalidates_old_token(self):
        old=self.review()
        new=self.core.prepare_review(self.sid,self.token,old['revision'])
        self.assertNotEqual(old['reviewId'],new['reviewId'])
        self.assert_core_error('stale_confirmation',lambda:self.core.confirm(self.sid,self.token,self.request(old)))

    def test_timeout_reuses_same_upstream_key_and_payload(self):
        review=self.review();request=self.request(review)
        self.gateway.fail_once=True
        self.assert_core_error('draft_outcome_unknown',lambda:self.core.confirm(self.sid,self.token,request))
        self.assert_core_error('draft_unresolved',lambda:self.core.edit(self.sid,self.token,review['revision'],{'planMonths':6}))
        self.assert_core_error('draft_unresolved',lambda:self.core.prepare_review(self.sid,self.token,review['revision']))
        result=self.core.confirm(self.sid,self.token,request)
        self.assertEqual(result['ref'],'sd_mockreference')
        self.assertEqual(self.gateway.calls[0],self.gateway.calls[1])
        self.assertEqual(len(self.gateway.results),1)

    def test_definitive_rejection_does_not_retry(self):
        review=self.review();request=self.request(review)
        def reject(*args):raise GatewayRejected(401,'unauthorized')
        self.gateway.create_signup_draft=reject
        self.assert_core_error('draft_rejected',lambda:self.core.confirm(self.sid,self.token,request))
        self.assert_core_error('review_rejected',lambda:self.core.confirm(self.sid,self.token,request))
        self.core.edit(self.sid,self.token,1,{'planMonths':6})

    def test_live_estimate_uses_api_data_only(self):
        self.gateway.mode='live'
        self.core.edit(self.sid,self.token,0,CHOICES|{'domain':{'label':'sample','tld':'ir'}})
        review=self.core.prepare_review(self.sid,self.token,1)
        self.assertEqual(review['estimate'],{'currency':'toman','total':17400000,'isFinal':False})

    def test_model_failure_releases_chat_lock(self):
        def failing(*args):raise RuntimeError('private')
        self.core.model=failing
        with self.assertRaises(RuntimeError):self.core.chat(self.sid,self.token,'سلام')
        self.core.edit(self.sid,self.token,0,{'businessName':'نمونه'})

    def test_busy_chat_blocks_confirmation_and_edits(self):
        review=self.review()
        with self.core.store.transaction() as db:
            db.execute('UPDATE sessions SET chat_until=?',(time.time()+100,))
        self.assert_core_error('conversation_busy',lambda:self.core.confirm(self.sid,self.token,self.request(review)))
        self.assert_core_error('conversation_busy',lambda:self.core.edit(self.sid,self.token,1,{'planMonths':6}))

    def test_concurrent_click_calls_gateway_once(self):
        request=self.request(self.review())
        self.gateway.entered,self.gateway.release=Event(),Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.core.confirm,self.sid,self.token,request)
            self.assertTrue(self.gateway.entered.wait(3))
            self.assert_core_error('draft_in_progress',lambda:self.core.confirm(self.sid,self.token,request))
            self.gateway.release.set();first.result(timeout=5)
        self.assertEqual(len(self.gateway.calls),1)

    def test_review_and_session_expiry(self):
        review=self.review()
        with self.core.store.transaction() as db:
            db.execute('UPDATE reviews SET expires=?',(time.time()-1,))
        self.assert_core_error('review_expired',lambda:self.core.confirm(self.sid,self.token,self.request(review)))
        with self.core.store.transaction() as db:
            db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
        self.assert_core_error('session_expired',lambda:self.core.get_session(self.sid,self.token))

    def test_untrusted_upstream_url_never_shows_success(self):
        review=self.review()
        original=self.gateway.create_signup_draft
        def bad(payload,key):
            result=original(payload,key)
            result['data']['confirmUrl']='https://evil.example/start?signup=sd_mockreference'
            return result
        self.gateway.create_signup_draft=bad
        self.assert_core_error('draft_outcome_unknown',lambda:self.core.confirm(self.sid,self.token,self.request(review)))

    def test_resume_requires_owner_capability(self):
        result=self.core.confirm(self.sid,self.token,self.request(self.review()))
        self.assertEqual(self.core.store.resume(result['ref'],self.token)['id'],self.sid)
        self.assert_core_error('session_not_found',lambda:self.core.store.resume(result['ref'],'wrong'))

    def test_fallback_is_encoded_and_never_includes_domain(self):
        self.edited()
        result=self.core.fallback(self.sid,self.token,'/')
        self.assertIn('name=',result['url'])
        self.assertNotIn('example.ir',result['url'])
        self.assertNotIn('label=',result['url'])
        self.assertFalse(result['isDraft'])
        self.assert_core_error('already_on_form',lambda:self.core.fallback(self.sid,self.token,'/start'))

    def test_existing_mock_cannot_claim_real_draft(self):
        self.edited()
        self.core.gateway=ExistingReadOnlyGateway()
        # Existing fixtures have a different template, so switch only the capability here.
        self.core.gateway=self.gateway;self.gateway.can_create=False
        review=self.core.prepare_review(self.sid,self.token,1)
        self.assertFalse(review['canConfirm'])
        self.assert_core_error('draft_adapter_unavailable',lambda:self.core.confirm(self.sid,self.token,self.request(review)))


class PrivacyAndModelTests(unittest.TestCase):
    def test_text_only_widget_redirects_attachment_requests(self):
        for answer in ('یک عکس از محصولت بفرست.', 'لطفاً ارسال کنید\nتصویر محصول را.'):
            response = NS(choices=[NS(message=NS(content=answer, tool_calls=[]))])
            with self.subTest(answer=answer), patch.object(
                ai_service.client.chat.completions, 'create', return_value=response
            ):
                reply, _ = ai_service.generate_turn('برای معرفی محصول چه کار کنم؟')
                self.assertIn('با متن', reply)
                self.assertNotIn(answer, reply)

    def test_store_conversation_continues_when_model_reply_is_empty(self):
        first, _ = ai_service.generate_turn('برای ساخت فروشگاه با لانچو از کجا شروع کنم؟')
        history = [{'role': 'assistant', 'content': first}]
        response = NS(choices=[NS(message=NS(content='', tool_calls=[]))])
        with patch.object(ai_service.client.chat.completions, 'create', return_value=response):
            reply, _ = ai_service.generate_turn('لباس زنانه می‌فروشم.', history)
        self.assertIn('اسم برندتان', reply)
        self.assertNotIn('https://', reply)

    def test_widget_starters_work_without_model(self):
        import re

        html = (Path(__file__).resolve().parents[1] / 'frontend' / 'widget.html').read_text(encoding='utf-8')
        starters = re.findall(r'data-question="([^"]+)"', html)
        self.assertEqual(len(starters), 3)
        with patch.object(ai_service.client.chat.completions, 'create') as call:
            replies = [ai_service.generate_turn(question)[0] for question in starters]
        call.assert_not_called()
        self.assertIn('https://launcho.ir/features', replies[1])
        self.assertIn('https://launcho.ir/pricing', replies[2])

    def test_store_starter_guides_before_referring_to_pricing(self):
        with patch.object(ai_service.client.chat.completions, 'create') as call:
            reply, update = ai_service.generate_turn('برای ساخت فروشگاه با لانچو از کجا شروع کنم؟')
        call.assert_not_called()
        self.assertIn('چه محصولی', reply)
        self.assertNotIn('https://', reply)
        self.assertEqual(update, {})

    def test_features_use_mock_service_info_without_follow_up(self):
        from app.mock_launcho import service_info

        payload = service_info('Bearer local-simulation')['data']
        with patch.object(ai_service.client.chat.completions, 'create') as model:
            reply, _ = ai_service.generate_turn('امکانات لانچو چیه؟', options={'serviceInfo': payload})
        model.assert_not_called()
        for feature in payload['featureSummary']:
            self.assertIn(feature, reply)
        self.assertNotIn('؟', reply)
        self.assertLessEqual(len(reply), 220)

    def test_redaction_is_idempotent_and_preserves_normal_guidance(self):
        guidance = 'رمز عبور و کد تأیید فقط در فرم رسمی وارد می‌شوند.'
        self.assertEqual(redact(guidance), guidance)
        masked = redact('رمز عبور: QA_fake123')
        self.assertNotIn('QA_fake123', masked)
        self.assertEqual(redact(masked), masked)

    def test_mixed_question_keeps_answer_and_adds_pricing_referral(self):
        answer = 'لانچو پلتفرم ساخت فروشگاه آنلاین است.'
        response = NS(choices=[NS(message=NS(content=answer, tool_calls=[]))])
        with patch.object(ai_service.client.chat.completions, 'create', return_value=response):
            reply, _ = ai_service.generate_turn('لانچو چیست و هزینه ساخت فروشگاه چقدر است؟')
        self.assertIn(answer, reply)
        self.assertIn('https://launcho.ir/pricing', reply)

    def test_unrelated_creative_request_is_redirected(self):
        with patch.object(ai_service.client.chat.completions, 'create') as call:
            reply, _ = ai_service.generate_turn('برای من یک شعر درباره فضا بگو و اسم لانچو را نیاور.')
        call.assert_not_called()
        self.assertIn('راهنمایی', reply)

    def test_model_cannot_return_unapproved_link_or_ask_for_otp_first(self):
        cases = (
            ('ثبت‌نام https://launcho.ir/start?otp=QA_TEST و https://example.invalid/start',
             'پیوند تأییدنشده'),
            ('لطفاً ارسال بفرمایید\nکد تأیید حساب را.', ai_service._FORM_REPLY),
            ('ثبت‌نام شما با موفقیت انجام شد.', 'https://launcho.ir/start'),
        )
        for answer, expected in cases:
            response = NS(choices=[NS(message=NS(content=answer, tool_calls=[]))])
            with self.subTest(answer=answer), patch.object(
                ai_service.client.chat.completions, 'create', return_value=response
            ):
                reply, _ = ai_service.generate_turn('برای ثبت‌نام چه‌کار کنم؟')
                self.assertIn(expected, reply)
                self.assertNotIn(answer, reply)

    def test_masks_common_sensitive_values_and_preserves_prices(self):
        for value in ['+98 912 345 6789','۰۹۱۲۳۴۵۶۷۸۹','09123456789','کد: 123456','کد تایید من: ۱۲۳۴۵۶','OTP ۱۲۳۴','رمز عبور: secret123','password is secret123','test@example.com','sk-exampletoken1234','۱۲۳۴۵۶']:
            with self.subTest(value=value):self.assertNotEqual(redact(value),value)
        self.assertEqual(redact('قیمت ۲۴۰۰۰۰۰ تومان است'),'قیمت ۲۴۰۰۰۰۰ تومان است')

    def test_model_never_receives_writing_tool(self):
        response=NS(choices=[NS(message=NS(content=None,tool_calls=[NS(function=NS(name='create_signup_draft',arguments='{}'))]))])
        with patch.object(ai_service.client.chat.completions,'create',return_value=response) as call:
            reply,update=ai_service.generate_turn('پیش‌نویس بساز ۰۹۱۲۳۴۵۶۷۸۹')
        self.assertEqual(update,{})
        self.assertNotIn('۰۹۱۲۳۴۵۶۷۸۹',json.dumps(call.call_args.kwargs,ensure_ascii=False))
        self.assertNotIn('tools', call.call_args.kwargs)

    def test_mock_history_and_arguments_are_not_instructions(self):
        response=NS(choices=[NS(message=NS(content=None,tool_calls=[NS(function=NS(name='update_signup_preferences',arguments=json.dumps({'businessName':'نمونه'})))]))])
        with patch.object(ai_service.client.chat.completions,'create',return_value=response):
            self.assertEqual(ai_service.generate_turn('نام کسب‌وکار نمونه است', allow_preferences=True)[1],{'businessName':'نمونه'})

    def test_mock_offer_endpoint_only_matches_supported_objections(self):
        from app.mock_launcho import OfferRequest, offers, widget_host

        request = OfferRequest(kind='shop', step='review_ready', objections=['price'],
                               needs=['low_upfront'], discountAlreadyShown=False)
        token = 'Bearer local-simulation'
        matched = offers(request, token)
        self.assertEqual(matched['data']['offers'][0]['offerId'], 'demo_campaign')
        request.discountAlreadyShown = True
        self.assertEqual(offers(request, token)['data']['offers'], [])
        self.assertIn('/widget/loader.js', widget_host())

    def test_demo_campaign_is_labeled_and_not_repeated(self):
        options = {'demoOffers': [{'id': 'demo_campaign', 'line': 'جشنوارهٔ نمونه'}]}
        message = 'هزینه برام زیاده'
        with patch.object(ai_service.client.chat.completions, 'create') as call:
            reply, _ = ai_service.generate_turn(message, options=options)
            later, _ = ai_service.generate_turn(message, [{'role': 'assistant', 'content': reply}], options=options)
        call.assert_not_called()
        self.assertIn('پیشنهاد آزمایشی', reply)
        self.assertIn('جشنوارهٔ نمونه', reply)
        self.assertIn('امکانات ضروری', reply)
        self.assertNotIn('جشنواره', later)

    def test_store_campaign_question_uses_product_knowledge(self):
        response = NS(choices=[NS(message=NS(content='در پنل فروشنده می‌توانید حراج زمان‌دار بسازید.', tool_calls=[]))])
        with patch.object(ai_service.client.chat.completions, 'create', return_value=response) as call:
            reply, _ = ai_service.generate_turn('برای مشتریان فروشگاه در پنل جشنواره دارم؟')
        self.assertIn('حراج زمان‌دار', reply)
        self.assertNotIn('launcho.ir/pricing', reply)
        self.assertIn('مدیریت کیف پول', call.call_args.kwargs['messages'][0]['content'])

    def test_long_model_reply_is_shortened_at_sentence_boundary(self):
        sentence = 'برای شروع، فهرست محصولات اصلی را آماده کنید.'
        response = NS(choices=[NS(message=NS(content=(sentence + ' ') * 40, tool_calls=[]))])
        with patch.object(ai_service.client.chat.completions, 'create', return_value=response):
            reply, _ = ai_service.generate_turn('چطور محصولاتم را آماده کنم؟')
        self.assertLessEqual(len(reply), 280)
        self.assertTrue(reply.endswith(sentence))

    def test_price_question_uses_official_referral_without_calling_model(self):
        with patch.object(ai_service.client.chat.completions, 'create') as call:
            reply, update = ai_service.generate_turn('هزینه ساخت فروشگاه چقدره؟')
        call.assert_not_called()
        self.assertIn('https://launcho.ir/pricing', reply)
        self.assertEqual(update, {})

    def test_model_rate_limit_answers_explicit_inventory_question(self):
        from openai import RateLimitError

        upstream = httpx.Response(429, request=httpx.Request('POST', 'https://example.invalid/v1/chat'))
        failure = RateLimitError('gateway throttled', response=upstream, body=None)
        with patch.object(ai_service.client.chat.completions, 'create', side_effect=failure):
            reply, update = ai_service.generate_turn('موجودی هر رنگ و سایز را چطور ثبت کنم؟')
            self.assertEqual(reply, 'در پنل موجودی می‌توانید موجودی هر رنگ و سایز را جدا ثبت کنید.')
            self.assertEqual(update, {})
            with self.assertRaises(RateLimitError):
                ai_service.generate_turn('آیا امکان مهاجرت اطلاعات از سرویس فعلی را دارم؟')

    def test_bold_official_url_survives_and_impostor_is_removed(self):
        text = '**https://launcho.ir/start** و **https://launcho.ir.evil.example/start**'
        response = NS(choices=[NS(message=NS(content=text, tool_calls=[]))])
        with patch.object(ai_service.client.chat.completions, 'create', return_value=response):
            reply, _ = ai_service.generate_turn('آدرس صفحه شروع ثبت‌نام کجاست؟')
        self.assertIn('**https://launcho.ir/start**', reply)
        self.assertNotIn('evil.example', reply)

    def test_business_types_get_one_direct_next_step(self):
        with patch.object(ai_service.client.chat.completions, 'create') as model:
            for business in ('کیف‌فروشی', 'تعمیر موبایل', 'آموزش زبان', 'ابزار صنعتی', 'قهوه تخصصی'):
                with self.subTest(business=business):
                    history = [{'role': 'assistant', 'content': ai_service._STORE_START_REPLY}]
                    reply, _ = ai_service.generate_turn(business, history)
                    self.assertEqual(reply, ai_service._STORE_DOMAIN_QUESTION)
        model.assert_not_called()

    def test_chat_guides_signup_and_hands_off_after_user_is_ready(self):
        history = []
        with patch.object(ai_service.client.chat.completions, 'create') as model:
            for message, expected in (
                ('من از لانچو خوشم اومده مراحل ثبت نام رو برام انجام بده', 'چه محصولی'),
                ('کیف‌فروشی', 'اسم برندتان'),
                ('تو برام انجام بده', 'پیشنهاد دامنه را من آماده می‌کنم'),
                ('هزینه چقدر است؟', 'https://launcho.ir/pricing'),
                ('Kif Sara', 'kifsara.ir'),
                ('بله', 'https://launcho.ir/#templates'),
                ('آماده‌ام', 'https://launcho.ir/start'),
            ):
                reply, update = ai_service.generate_turn(message, history)
                self.assertIn(expected, reply)
                self.assertEqual(update, {})
                if message != 'آماده‌ام':
                    self.assertNotIn('https://launcho.ir/start', reply)
                history.extend([{'role':'user','content':message}, {'role':'assistant','content':reply}])
        model.assert_not_called()

    def test_guidance_replaces_unsupported_price_and_sensitive_request(self):
        for text, link in (
            ('اشتراک ۲۴۰٬۰۰۰ تومان است.', 'https://launcho.ir/pricing'),
            ('کد تأیید خود را همین‌جا بفرستید.', ai_service._FORM_REPLY),
        ):
            with self.subTest(text=text):
                response = NS(choices=[NS(message=NS(content=text, tool_calls=[]))])
                with patch.object(ai_service.client.chat.completions, 'create', return_value=response):
                    reply, update = ai_service.generate_turn('چطور شروع کنم؟')
                self.assertIn(link, reply)
                self.assertNotIn(text, reply)
                self.assertEqual(update, {})


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_chat_reports_model_rate_limit(self):
        from openai import RateLimitError

        session = self.core.create_session()
        upstream = httpx.Response(429, request=httpx.Request('POST', 'https://example.invalid/v1/chat'))
        failure = RateLimitError('private gateway details', response=upstream, body=None)
        with patch.object(self.core, 'model', side_effect=failure):
            response = await self.client.post(
                '/api/chat', json={'message':'سلام','sessionId':session['sessionId']},
                headers={'X-Session-Token':session['sessionToken']},
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['detail']['code'], 'model_rate_limited')
        self.assertNotIn('private gateway details', response.text)

    async def test_invisible_chat_is_rejected_and_persian_joiner_survives(self):
        with patch('app.api.routes.get_ai_response', return_value='پاسخ') as model:
            blank = await self.client.post('/api/chat', json={'message':'\u200b\u200c\u202e\ufe0f'})
            self.assertEqual(blank.status_code, 422)
            model.assert_not_called()
            valid = await self.client.post('/api/chat', json={'message':'می‌روم'})
            self.assertEqual(valid.status_code, 200)
            model.assert_called_once_with('می‌روم')

    async def test_invalid_chat_body_does_not_echo_rejected_input(self):
        marker = 'QA_FAKE_REJECTED_INPUT'
        response = await self.client.post('/api/chat', json={'message': {'otp': marker}})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(marker, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.gateway=FakeGateway()
        self.core=ConversationCore(SessionStore(Path(self.tmp.name)/'db.sqlite3'),self.gateway,
                                   lambda *args:('پاسخ تست',{}))
        self.patch=patch('app.api.routes.get_core',return_value=self.core);self.patch.start()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test')
    async def asyncTearDown(self):
        await self.client.aclose();self.patch.stop();self.tmp.cleanup()
    async def test_complete_endpoint_flow(self):
        created=await self.client.post('/api/sessions')
        self.assertEqual(created.status_code,201)
        session=created.json();sid=session['sessionId'];headers={'X-Session-Token':session['sessionToken']}
        self.assertEqual((await self.client.get('/api/sessions/'+sid)).status_code,404)
        edited=await self.client.patch('/api/sessions/'+sid+'/preferences',headers=headers,json={'revision':0,'preferences':CHOICES})
        self.assertEqual(edited.status_code,200)
        review=await self.client.post('/api/sessions/'+sid+'/review',headers=headers,json={'revision':1})
        data=review.json()
        payload={k:data[k] for k in ['revision','reviewId','confirmationToken']}|{'confirmed':True}
        confirmed=await self.client.post('/api/sessions/'+sid+'/confirm',headers=headers,json=payload)
        self.assertEqual(confirmed.status_code,200)
        self.assertEqual(confirmed.json()['ref'],'sd_mockreference')
        resumed=await self.client.post('/api/sessions/resume',headers=headers,json={'signupRef':'sd_mockreference'})
        self.assertEqual(resumed.json()['sessionId'],sid)
        self.assertEqual(confirmed.headers['cache-control'],'no-store')

    async def test_legacy_chat_preserved(self):
        with patch('app.api.routes.get_ai_response',return_value='پاسخ'):
            result=await self.client.post('/api/chat',json={'message':'سلام'})
        self.assertEqual(result.json(),{'reply':'پاسخ'})

    async def test_sensitive_or_extra_structured_fields_rejected(self):
        session=self.core.create_session();sid=session['sessionId'];headers={'X-Session-Token':session['sessionToken']}
        for fields in [{'mobile':'09123456789'},{'businessName':'09123456789'},{'password':'secret'}]:
            result=await self.client.patch('/api/sessions/'+sid+'/preferences',headers=headers,json={'revision':0,'preferences':fields})
            self.assertEqual(result.status_code,422)
        for message in ['', ' ', 'a'*5001]:
            self.assertEqual((await self.client.post('/api/chat',json={'message':message})).status_code,422)

if __name__=='__main__':unittest.main()
