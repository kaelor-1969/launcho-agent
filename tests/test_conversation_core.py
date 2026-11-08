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
from app.services.draft_gateway import ExistingReadOnlyGateway, GatewayRejected
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

    def test_redaction_before_model_and_history(self):
        captured=[]
        def model(*args):captured.append(args);return 'کد تأیید: ۱۲۳۴۵۶',{}
        self.core.model=model
        self.core.chat(self.sid,self.token,'شماره من ۰۹۱۲۳۴۵۶۷۸۹ و کد تأیید: ۱۲۳۴۵۶')
        self.core.chat(self.sid,self.token,'ادامه')
        stored=self.core.get_session(self.sid,self.token)
        representation=json.dumps([captured,stored],ensure_ascii=False)
        for secret in ['۰۹۱۲۳۴۵۶۷۸۹','۱۲۳۴۵۶','09123456789','123456']:
            self.assertNotIn(secret,representation)
        self.assertTrue(captured[1][1])

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
        self.assertEqual([x['function']['name'] for x in call.call_args.kwargs['tools']],['update_signup_preferences'])

    def test_mock_history_and_arguments_are_not_instructions(self):
        response=NS(choices=[NS(message=NS(content=None,tool_calls=[NS(function=NS(name='update_signup_preferences',arguments=json.dumps({'businessName':'نمونه'})))]))])
        with patch.object(ai_service.client.chat.completions,'create',return_value=response):
            self.assertEqual(ai_service.generate_turn('نام کسب‌وکار نمونه است')[1],{'businessName':'نمونه'})


class EndpointTests(unittest.IsolatedAsyncioTestCase):
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
