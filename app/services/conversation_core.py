"""Persistent sessions and button-driven draft orchestration, independent of LLM tools."""
from datetime import datetime, timezone
from functools import lru_cache
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from pydantic import ValidationError

from app.core.config import PROJECT_ROOT
from app.core.privacy import has_visible_text, redact
from app.models.schemas import Preferences, PreferenceUpdate
from app.services.ai_service import generate_turn
from app.services.draft_gateway import build_gateway, unwrap, GatewayRejected, GatewayUnavailable
from app.services.financial_context import financial_context
from app.services.offer_contract import OfferState, validated_offers
from app.services.session_store import CoreError, SessionStore, digest


def stamp(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def parse_expiry(value):
    try:
        result = datetime.fromisoformat(value.replace('Z','+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result.timestamp()
    except (AttributeError, TypeError, ValueError):
        raise ValueError('Invalid expiry') from None


class ConversationCore:
    def __init__(self, store, gateway, model=generate_turn):
        self.store, self.gateway, self.model = store, gateway, model

    def view(self, row):
        result = {'sessionId':row['id'], 'revision':row['revision'],
                'expiresAt':stamp(row['expires']), 'preferences':json.loads(row['prefs']),
                'history':json.loads(row['history']), 'adapterMode':self.gateway.mode,
                'canCreateDraft':self.gateway.can_create}
        if row['review_id']:
            with self.store.transaction() as db:
                review=db.execute('SELECT status,result FROM reviews WHERE id=?',(row['review_id'],)).fetchone()
            if review:
                result['draftState']=review['status']
                if review['status']=='completed':
                    result['draft']=json.loads(review['result'])
        return result

    def create_session(self):
        sid, token = self.store.create()
        return {**self.view(self.store.get(sid,token)), 'sessionToken':token}

    def get_session(self, sid, token):
        return self.view(self.store.get(sid,token))

    def data(self, kind):
        try:
            options = unwrap(self.gateway.get_signup_options(kind))
            pricing = unwrap(self.gateway.get_pricing())
            for source, key, field, expected in (
                (options, 'businessCategories', 'id', str), (options, 'templates', 'id', str),
                (pricing, 'plans', 'months', int), (pricing, 'domains', 'tld', str),
            ):
                items = source.get(key, [] if key == 'domains' else None)
                if not isinstance(items, list) or any(
                    not isinstance(item, dict) or type(item.get(field)) is not expected for item in items
                ):
                    raise GatewayUnavailable('Invalid options or pricing response.')
            return options, pricing
        except Exception:
            raise CoreError(503,'options_unavailable','گزینه‌های معتبر در دسترس نیستند؛ از فرم رسمی استفاده کنید.') from None

    def validate_preferences(self, prefs):
        prefs = Preferences.model_validate(prefs).model_dump(exclude_none=True, mode='json')
        options, pricing = self.data(prefs['kind'])
        if 'category' in prefs and prefs['category'] not in {x['id'] for x in options['businessCategories']}:
            raise CoreError(422,'invalid_category','دسته‌بندی را از گزینه‌های فعلی انتخاب کنید.')
        if 'template' in prefs and prefs['template'] not in {x['id'] for x in options['templates'] if x.get('available')}:
            raise CoreError(422,'invalid_template','قالب آماده و معتبر انتخاب کنید.')
        if 'planMonths' in prefs and prefs['planMonths'] not in {x['months'] for x in pricing['plans']}:
            raise CoreError(422,'invalid_plan','دوره اشتراک معتبر انتخاب کنید.')
        if 'domain' in prefs and 'tld' in prefs['domain']:
            tlds = {x['tld'] for x in pricing.get('domains',[])}
            if prefs['domain']['tld'] not in tlds:
                raise CoreError(422,'invalid_domain','پسوند دامنه در گزینه‌های فعلی موجود نیست.')
        return prefs

    def ensure_editable(self, db, row):
        if row['chat_until'] > time.time():
            raise CoreError(409,'conversation_busy','پاسخ گفتگو در حال آماده‌شدن است.')
        if row['review_id']:
            review = db.execute('SELECT * FROM reviews WHERE id=?',(row['review_id'],)).fetchone()
            if review and review['status'] in {'creating','unknown'}:
                raise CoreError(409,'draft_unresolved','ابتدا نتیجه همان درخواست پیش‌نویس را بررسی کنید.')

    def edit(self, sid, token, revision, update):
        row = self.store.get(sid,token)
        if row['revision'] != revision:
            raise CoreError(409,'stale_revision','خلاصه تغییر کرده؛ وضعیت جدید را دریافت کنید.')
        old = json.loads(row['prefs'])
        merged = self.merge(old,update)
        prefs = self.validate_preferences(merged)
        with self.store.transaction() as db:
            current = self.store.authenticate(db,sid,token)
            self.ensure_editable(db,current)
            if current['revision'] != revision:
                raise CoreError(409,'stale_revision','خلاصه تغییر کرده است.')
            if prefs != old:
                db.execute('UPDATE sessions SET prefs=?,revision=revision+1,review_id=NULL WHERE id=?',
                           (json.dumps(prefs,ensure_ascii=False),sid))
        return self.get_session(sid,token)

    @staticmethod
    def merge(old, update):
        update = PreferenceUpdate.model_validate(update).model_dump(exclude_unset=True,mode='json')
        merged = dict(old)
        if update.get('kind') and update['kind'] != old.get('kind'):
            merged.pop('category',None)
            merged.pop('template',None)
        for key,value in update.items():
            if value is None:
                if key != 'kind':
                    merged.pop(key,None)
            else:
                merged[key] = value
        return merged

    def chat(self, sid, token, message, request_id=None):
        if not has_visible_text(message):
            raise CoreError(422, 'invalid_request', 'پیام خالی است.')
        safe = redact(message)
        with self.store.transaction() as db:
            row = self.store.authenticate(db,sid,token)
            history = json.loads(row['history'])
            if request_id:
                saved = db.execute('SELECT message_hash,response FROM chat_responses '
                                   'WHERE session_id=? AND request_id=?', (sid, request_id)).fetchone()
                if saved:
                    if saved['message_hash'] != digest(safe):
                        raise CoreError(409, 'request_conflict', 'شناسهٔ پیام قبلاً استفاده شده است.')
                    return json.loads(saved['response'])
                for previous, answer in zip(history[::2], history[1::2]):
                    if previous.get('requestId') == request_id:
                        if previous['content'] != safe:
                            raise CoreError(409, 'request_conflict', 'شناسهٔ پیام قبلاً استفاده شده است.')
                        prefs = json.loads(row['prefs'])
                        return self.chat_result(sid, row['revision'], prefs, answer['content'])
            self.ensure_editable(db,row)
            state = OfferState.model_validate_json(row['offer_state'])
            if financial_context(safe, history)['rejected']:
                state.financialOffersDeclined = True
                state.rejectedOfferIds = list(dict.fromkeys(state.rejectedOfferIds + state.shownOfferIds))
            stage = self.financial_stage(db, row)
            lease = time.time()+150
            db.execute('UPDATE sessions SET chat_until=? WHERE id=?',(lease,sid))
        try:
            prefs = json.loads(row['prefs'])
            options, pricing = {}, {}
            if self.gateway.mode in {'live', 'local_mock'}:
                try:
                    options, pricing = self.data(prefs['kind'])
                    if self.gateway.mode == 'local_mock':
                        pricing = {}
                        options = {key: options[key] for key in ('businessCategories', 'templates')}
                except CoreError:
                    pass
            service_info = getattr(self.gateway, 'get_service_info', None)
            if service_info is not None:
                try:
                    options = {**options, 'serviceInfo': service_info()}
                except GatewayUnavailable:
                    pass
            if self.model is generate_turn:
                reply, update = self.model(safe, history, prefs, options, pricing,
                                           allow_preferences=self.gateway.can_create and bool(options and pricing))
            else:
                reply, update = self.model(safe, history, prefs, options, pricing)
            reply = redact(reply)
            if update:
                try:
                    prefs = self.validate_preferences(self.merge(prefs,update))
                except (ValidationError, CoreError):
                    prefs = json.loads(row['prefs'])
                    reply = 'انتخاب‌ها معتبر نبودند. لطفاً از گزینه‌های مجاز استفاده کنید؛ اطلاعات قبلی حفظ شد.'
            changed = prefs != json.loads(row['prefs'])
            if changed:
                stage = self.preference_stage(prefs)
            offer = self.financial_offer(safe, history, prefs, stage, state)
            if safe != message:
                reply = 'بخش حساس پیام پیش از پردازش و ذخیره پوشانده شد. اطلاعات ورود را فقط در فرم رسمی وارد کنید.\n' + reply
            user_turn = {'role':'user','content':safe}
            if request_id:
                user_turn['requestId'] = request_id
            with self.store.transaction() as db:
                current = self.store.authenticate(db,sid,token)
                if current['revision'] != row['revision'] or current['chat_until'] != lease:
                    raise CoreError(409,'stale_revision','اطلاعات تغییر کرده؛ دوباره وضعیت را دریافت کنید.')
                final_stage = stage if changed else self.financial_stage(db, current)
                if offer:
                    # Recheck expiry and eligibility after network/model latency, at commit time.
                    offers = validated_offers({'offers': [offer]}, kind=prefs['kind'],
                                              stage=final_stage, plan_months=prefs.get('planMonths'),
                                              allow_simulation=self.gateway.mode == 'local_mock',
                                              state=state.model_dump())['offers']
                    offer = offers[0] if offers else None
                if offer:
                    reply += '\n' + offer['displayText']
                    state.shownOfferIds.append(offer['offerId'])
                    state.anyFinancialOfferShown = True
                history = (history + [user_turn, {'role': 'assistant', 'content': reply}])[-12:]
                result = self.chat_result(sid, current['revision'] + int(changed), prefs, reply)
                if offer:
                    result['financialOffer'] = offer
                db.execute('UPDATE sessions SET prefs=?,history=?,revision=revision+?,review_id=?, '
                           'offer_state=?,chat_until=0 WHERE id=?',
                           (json.dumps(prefs,ensure_ascii=False),json.dumps(history,ensure_ascii=False),int(changed),
                            None if changed else current['review_id'],state.model_dump_json(),sid))
                if request_id:
                    db.execute('INSERT INTO chat_responses VALUES (?,?,?,?)',
                               (sid, request_id, digest(safe), json.dumps(result, ensure_ascii=False)))
            return result
        finally:
            with self.store.transaction() as db:
                db.execute('UPDATE sessions SET chat_until=0 WHERE id=? AND chat_until=?',(sid,lease))

    def chat_result(self, sid, revision, prefs, reply):
        return {'reply':reply,'sessionId':sid,'revision':revision,'preferences':prefs,
                'nextAction':'review' if self.gateway.can_create and self.complete(prefs) else 'collect_preferences'}

    def financial_stage(self, db, row):
        prefs = json.loads(row['prefs'])
        if row['review_id']:
            review = db.execute('SELECT * FROM reviews WHERE id=? AND session_id=?',
                                (row['review_id'], row['id'])).fetchone()
            if review and review['revision'] == row['revision']:
                if review['status'] == 'completed':
                    try:
                        result = json.loads(review['result'])
                        if (result.get('status') == 'draft' and result.get('ref', '').startswith('sd_')
                                and parse_expiry(result['expiresAt']) > time.time()):
                            return 'draft_created'
                    except (ValueError, TypeError, KeyError):
                        pass
                if review['status'] == 'awaiting' and review['expires'] > time.time():
                    return 'awaiting_confirmation'
        return self.preference_stage(prefs)

    def preference_stage(self, prefs):
        if self.complete(prefs):
            return 'review_ready'
        return 'collecting_preferences' if any(key != 'kind' for key in prefs) else 'guidance'

    def financial_offer(self, message, history, prefs, stage, state):
        if (state.anyFinancialOfferShown or state.shownOfferIds or state.financialOffersDeclined
                or not financial_context(message, history)['objections']):
            return None
        if self.gateway.mode == 'live' and os.getenv('LAUNCHO_ENABLE_FINANCIAL_OFFERS') != '1':
            return None
        # Canonical offers stay out of model context. The core owns their display and state.
        for name in ('match_price_offers', 'match_checkout_offers'):
            match = getattr(self.gateway, name, None)
            if match is None:
                continue
            try:
                raw = unwrap(match(prefs['kind'], prefs.get('planMonths'), message=message,
                                   history=history, step=stage, offer_state=state.model_dump()))
                offers = validated_offers(raw, kind=prefs['kind'], stage=stage,
                                          plan_months=prefs.get('planMonths'),
                                          allow_simulation=self.gateway.mode == 'local_mock',
                                          state=state.model_dump())['offers']
            except (GatewayUnavailable, ValueError, TypeError):
                continue
            if offers:
                return offers[0]
        return None

    @staticmethod
    def complete(prefs):
        return all(prefs.get(key) for key in ('businessName','category','planMonths','template','domain'))

    def prepare_review(self, sid, token, revision):
        row = self.store.get(sid,token)
        if row['revision'] != revision:
            raise CoreError(409,'stale_revision','اطلاعات تغییر کرده؛ خلاصه تازه لازم است.')
        prefs = self.validate_preferences(json.loads(row['prefs']))
        if not self.complete(prefs):
            raise CoreError(422,'incomplete_preferences','نام کسب‌وکار، دسته، دوره، قالب و دامنه را کامل کنید.')
        rid, confirmation = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            row = self.store.authenticate(db,sid,token)
            self.ensure_editable(db,row)
            if row['revision'] != revision:
                raise CoreError(409,'stale_revision','اطلاعات تغییر کرده است.')
            if row['review_id']:
                previous = db.execute('SELECT * FROM reviews WHERE id=?',(row['review_id'],)).fetchone()
                if previous and previous['status']=='completed':
                    result = json.loads(previous['result'])
                    if parse_expiry(result['expiresAt']) > time.time():
                        return {'sessionId':sid,'revision':revision,'canConfirm':False,'draft':result}
            db.execute('INSERT INTO reviews(id,session_id,revision,token_hash,expires,payload,idem,status) VALUES(?,?,?,?,?,?,?,?)',
                       (rid,sid,revision,digest(confirmation),time.time()+900,json.dumps(prefs,ensure_ascii=False),
                        secrets.token_urlsafe(32),'awaiting'))
            db.execute('UPDATE sessions SET review_id=? WHERE id=?',(rid,sid))
        return {'sessionId':sid,'revision':revision,'reviewId':rid,'confirmationToken':confirmation,
                'expiresAt':stamp(time.time()+900),'summary':prefs,'canConfirm':self.gateway.can_create,
                'adapterMode':self.gateway.mode,
                'estimate':self.estimate(prefs),
                'notice':'این تأیید فقط پیش‌نویس می‌سازد؛ حساب، فاکتور یا پرداخت ایجاد نمی‌کند.'}

    def estimate(self, prefs):
        # Never turn local fixtures into user-facing live prices.
        if self.gateway.mode!='live' or not self.gateway.can_create:
            return None
        try:
            _,pricing=self.data(prefs['kind'])
            setup=pricing['setupFees'][prefs['kind']]
            plan=next(x['price'] for x in pricing['plans'] if x['months']==prefs['planMonths'])
            domain=prefs['domain']
            if domain.get('ownDomain'):
                return None  # Existing-domain charges are not specified by the fixture contract.
            fee=next(x['annualFee'] for x in pricing['domains'] if x['tld']==domain['tld'])
            if pricing.get('currency')!='toman' or any(type(x) is not int or x<0 for x in (setup,plan,fee)):
                return None
            return {'currency':'toman','total':setup+plan+fee,'isFinal':False}
        except (CoreError,KeyError,StopIteration,TypeError):
            return None

    @staticmethod
    def validate_result(raw, local=False):
        data = unwrap(raw)
        ref, url = data.get('ref',''), data.get('confirmUrl','')
        import re
        if not re.fullmatch(r'sd_[A-Za-z0-9_-]{4,128}',ref):
            raise ValueError('Invalid reference')
        if local:
            if (url != f'/signup-drafts/{ref}/preview' or data.get('status') != 'draft'
                    or parse_expiry(data.get('expiresAt')) <= time.time()):
                raise ValueError('Invalid local draft')
            return {'ref': ref, 'confirmUrl': f'/api/local-drafts/{ref}/preview',
                    'expiresAt': data['expiresAt'], 'status': 'draft'}
        parsed = urlsplit(url)
        if (parsed.scheme!='https' or parsed.netloc!='launcho.ir' or parsed.path!='/start'
            or parsed.fragment or parse_qsl(parsed.query)!=[('signup',ref)]):
            raise ValueError('Invalid confirmation URL')
        if data.get('status')!='draft' or parse_expiry(data.get('expiresAt'))<=time.time():
            raise ValueError('Invalid draft state')
        quote = data.get('quote')
        if not isinstance(quote,dict) or quote.get('isFinal') is not False or type(quote.get('total')) is not int or quote['total']<0:
            raise ValueError('Invalid quote')
        # Store only the contract fields needed for the caller, not arbitrary upstream data.
        return {'ref':ref,'confirmUrl':url,'expiresAt':data['expiresAt'],'status':'draft',
                'quote':{'total':quote['total'],'isFinal':False}}

    def confirm(self, sid, token, request):
        if request.confirmed is not True:
            raise CoreError(422,'confirmation_required','دکمه تأیید خلاصه باید انتخاب شود.')
        with self.store.transaction() as db:
            row = self.store.authenticate(db,sid,token)
            if row['chat_until']>time.time():
                raise CoreError(409,'conversation_busy','پاسخ گفتگو در حال آماده‌شدن است.')
            review = db.execute('SELECT * FROM reviews WHERE id=? AND session_id=?',
                                (request.reviewId,sid)).fetchone()
            if (not review or row['review_id']!=request.reviewId or row['revision']!=request.revision
                or review['revision']!=request.revision
                or not hmac.compare_digest(review['token_hash'],digest(request.confirmationToken))):
                raise CoreError(409,'stale_confirmation','تأیید معتبر نیست؛ خلاصه تازه دریافت کنید.')
            if review['status']=='completed':
                result = json.loads(review['result'])
                if parse_expiry(result['expiresAt'])<=time.time():
                    raise CoreError(410,'draft_expired','پیش‌نویس منقضی شده؛ خلاصه و تأیید تازه لازم است.')
                return {**result,'adapterMode':self.gateway.mode,'replayed':True}
            if review['status']=='rejected':
                raise CoreError(409,'review_rejected','درخواست قبلی رد شده؛ اطلاعات را بررسی و خلاصه تازه دریافت کنید.')
            if review['status']=='awaiting' and review['expires']<=time.time():
                raise CoreError(410,'review_expired','خلاصه منقضی شده؛ آن را دوباره مرور کنید.')
            if review['status']=='creating' and review['started']>time.time()-180:
                raise CoreError(409,'draft_in_progress','همان درخواست در حال پردازش است؛ دوباره ارسال نکنید.')
            if not self.gateway.can_create:
                raise CoreError(503,'draft_adapter_unavailable','اتصال قراردادی پیش‌نویس آماده نیست؛ از فرم رسمی استفاده کنید.')
            db.execute("UPDATE reviews SET status='creating',started=? WHERE id=?",(time.time(),review['id']))
            payload, idem = json.loads(review['payload']), review['idem']
        try:
            # No automatic retry. A manual retry uses this exact key and stored payload.
            result = self.validate_result(self.gateway.create_signup_draft(payload,idem),
                                          local=self.gateway.mode == 'local_mock')
        except GatewayRejected as error:
            with self.store.transaction() as db:
                db.execute("UPDATE reviews SET status='rejected' WHERE id=?",(review['id'],))
            status=error.status if error.status in {400,401,403,404,409,410,422,429} else 503
            messages={401:'اتصال لانچو مجاز نیست؛ مسئول اتصال باید بررسی کند.',
                      429:'محدودیت درخواست لانچو؛ بعداً خلاصه تازه دریافت کنید.',
                      410:'پیش‌نویس منقضی است؛ مرور و تأیید تازه لازم است.'}
            raise CoreError(status,'draft_rejected',messages.get(status,'درخواست توسط لانچو رد شد؛ اطلاعات را بررسی کنید.')) from None
        except Exception:
            with self.store.transaction() as db:
                db.execute("UPDATE reviews SET status='unknown' WHERE id=? AND status='creating'",(review['id'],))
            raise CoreError(503,'draft_outcome_unknown','نتیجه پیش‌نویس نامعلوم است؛ فقط همان تأیید را برای بازیابی نتیجه تکرار کنید.') from None
        with self.store.transaction() as db:
            db.execute("UPDATE reviews SET status='completed',result=? WHERE id=?",
                       (json.dumps(result,ensure_ascii=False),review['id']))
        return {**result,'adapterMode':self.gateway.mode,'replayed':False}

    def fallback(self, sid, token, path):
        row = self.store.get(sid,token)
        if urlsplit(path).path.rstrip('/') == '/start':
            raise CoreError(409,'already_on_form','روی فرم فقط راهنمایی انجام می‌شود؛ لینک پیش‌پرشده داده نمی‌شود.')
        prefs = self.validate_preferences(json.loads(row['prefs']))
        query = {}
        if prefs['kind']=='website': query['kind']='website'
        for source,target in [('businessName','name'),('category','cat'),('planMonths','plan'),('template','template')]:
            if source in {'category', 'template'} and self.gateway.mode == 'local_mock':
                continue
            if source in prefs: query[target]=prefs[source]
        return {'url':'https://launcho.ir/start'+('?' + urlencode(query) if query else ''),
                'isDraft':False,'notice':'این لینک عمومی است؛ پیش‌نویسی در لانچو ساخته نشده است.'}

    def draft_status(self, sid, token):
        session = self.get_session(sid, token)
        draft = session.get('draft')
        if not draft:
            raise CoreError(404, 'draft_not_found', 'پیش‌نویسی برای این گفتگو پیدا نشد.')
        reader = getattr(self.gateway, 'get_draft_status', None)
        if reader is None:
            raise CoreError(503, 'draft_status_unavailable', 'پیگیری وضعیت فعلاً در دسترس نیست.')
        try:
            result = unwrap(reader(draft['ref']))
            status = result.get('status')
            if result.get('ref') != draft['ref'] or status not in (
                'draft', 'opened', 'mobile_verified', 'invoiced', 'paid', 'active', 'expired'
            ):
                raise GatewayUnavailable('Invalid draft status.')
        except GatewayUnavailable:
            raise CoreError(503, 'draft_status_unavailable', 'پیگیری وضعیت فعلاً در دسترس نیست.') from None
        return {'status':status}


@lru_cache(maxsize=1)
def get_core():
    gateway = build_gateway()
    filename = 'local-sessions.sqlite3' if gateway.mode == 'local_mock' else 'sessions.sqlite3'
    path = os.getenv('LAUNCHO_SESSION_DB', str(PROJECT_ROOT / 'data' / filename))
    ttl = int(os.getenv('LAUNCHO_SESSION_TTL_SECONDS','86400'))
    if not 60<=ttl<=86400:
        raise RuntimeError('LAUNCHO_SESSION_TTL_SECONDS must be between 60 and 86400.')
    return ConversationCore(SessionStore(path,ttl),gateway)
