import logging
import re
from fastapi.responses import HTMLResponse
from app.services.draft_gateway import GatewayUnavailable
from fastapi import APIRouter, Header, HTTPException, Response
from openai import APIError, RateLimitError
from pydantic import ValidationError

from app.core.privacy import redact
from app.models.schemas import (ChatRequest, ChatResponse, EditRequest, ReviewRequest,
                                ConfirmRequest, ResumeRequest)
from app.services.ai_service import get_ai_response
from app.services.conversation_core import get_core
from app.services.session_store import CoreError

logger = logging.getLogger(__name__)
router = APIRouter()


def run(action):
    try:
        return action()
    except CoreError as exc:
        raise HTTPException(exc.status,detail={'code':exc.code,'message':exc.message},headers={'Cache-Control':'no-store'}) from None
    except ValidationError:
        raise HTTPException(422,detail={'code':'invalid_preferences','message':'اطلاعات انتخابی معتبر نیست.'},headers={'Cache-Control':'no-store'}) from None
    except RateLimitError:
        logger.warning('chat_gateway_failure type=RateLimitError')
        raise HTTPException(429, detail={'code':'model_rate_limited','message':'سرویس پاسخ‌گویی به محدودیت مصرف رسیده است.'},
                            headers={'Cache-Control':'no-store'}) from None
    except APIError as exc:
        logger.warning('chat_gateway_failure type=%s',type(exc).__name__)
        raise HTTPException(503,detail={'code':'model_unavailable','message':'سرویس گفتگو در دسترس نیست.'},headers={'Cache-Control':'no-store'}) from None
    except Exception as exc:
        logger.error('core_failure type=%s',type(exc).__name__)
        raise HTTPException(500,detail={'code':'internal_error','message':'خطایی در پردازش درخواست رخ داد.'},headers={'Cache-Control':'no-store'}) from None


def no_store(response):
    response.headers['Cache-Control']='no-store'


@router.post('/api/chat',response_model=ChatResponse,response_model_exclude_none=True)
def chat(request: ChatRequest, response: Response, x_session_token: str | None = Header(default=None)):
    no_store(response)
    if request.sessionId:
        return run(lambda:get_core().chat(request.sessionId,x_session_token,request.message,request.requestId))
    # Legacy widget remains compatible, but has no memory or draft-writing ability.
    return run(lambda:ChatResponse(reply=redact(get_ai_response(redact(request.message)))))


@router.get('/api/local-signup-options')
def local_signup_options(response: Response, kind: str = 'shop'):
    no_store(response)
    core = get_core()
    if core.gateway.mode != 'local_mock':
        raise HTTPException(404)
    if kind not in {'shop', 'website'}:
        raise HTTPException(422)
    options, pricing = run(lambda: core.data(kind))
    return {**options, 'periods': [item['months'] for item in pricing['plans']],
            'suffixes': [item['tld'] for item in pricing['domains']]}


@router.get('/api/local-drafts/{ref}/preview')
def local_draft_preview(ref: str):
    core = get_core()
    if core.gateway.mode != 'local_mock' or not re.fullmatch(r'sd_[A-Za-z0-9_-]{4,128}', ref):
        raise HTTPException(404)
    try:
        status = core.gateway.get_draft_status(ref)
    except GatewayUnavailable:
        raise HTTPException(404, detail='پیش‌نویس محلی در دسترس نیست.') from None
    if status.get('ref') != ref or status.get('status') not in {'draft', 'expired'}:
        raise HTTPException(404)
    if status['status'] == 'expired':
        raise HTTPException(410, detail='پیش‌نویس آزمایشی منقضی شده است.')
    return HTMLResponse(
        '<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">'
        '<title>پیش‌نویس آزمایشی</title><h1>پیش‌نویس آزمایشی آماده است</h1>'
        '<p>حساب، فروشگاه و پرداختی ایجاد نشده است.</p></html>',
        headers={'Cache-Control': 'no-store'},
    )


@router.post('/api/sessions',status_code=201)
def create_session(response: Response):
    no_store(response)
    result = run(lambda:get_core().create_session())
    logger.info('launcho_event=session_started')
    return result


@router.get('/api/sessions/{session_id}')
def get_session(session_id: str, response: Response, x_session_token: str | None = Header(default=None)):
    no_store(response)
    return run(lambda:get_core().get_session(session_id,x_session_token))


@router.patch('/api/sessions/{session_id}/preferences')
def edit_preferences(session_id: str, request: EditRequest, response: Response,
                     x_session_token: str | None = Header(default=None)):
    no_store(response)
    return run(lambda:get_core().edit(session_id,x_session_token,request.revision,
                                     request.preferences.model_dump(exclude_unset=True,mode='json')))


@router.post('/api/sessions/{session_id}/review')
def review(session_id: str, request: ReviewRequest, response: Response,
           x_session_token: str | None = Header(default=None)):
    no_store(response)
    return run(lambda:get_core().prepare_review(session_id,x_session_token,request.revision))


@router.post('/api/sessions/{session_id}/confirm')
def confirm(session_id: str, request: ConfirmRequest, response: Response,
            x_session_token: str | None = Header(default=None)):
    no_store(response)
    result = run(lambda:get_core().confirm(session_id,x_session_token,request))
    if not result['replayed']:
        logger.info('launcho_event=draft_created')
    return result


@router.get('/api/sessions/{session_id}/draft-status')
def draft_status(session_id: str, response: Response, x_session_token: str | None = Header(default=None)):
    no_store(response)
    result = run(lambda:get_core().draft_status(session_id, x_session_token))
    logger.info('launcho_event=draft_status_checked status=%s', result['status'])
    return result


@router.post('/api/sessions/resume')
def resume(request: ResumeRequest, response: Response, x_session_token: str | None = Header(default=None)):
    no_store(response)
    def action():
        core=get_core()
        return core.view(core.store.resume(request.signupRef,x_session_token))
    return run(action)


@router.get('/api/sessions/{session_id}/fallback-link')
def fallback_link(session_id: str, response: Response, path: str='/',
                  x_session_token: str | None = Header(default=None)):
    no_store(response)
    return run(lambda:get_core().fallback(session_id,x_session_token,path))
