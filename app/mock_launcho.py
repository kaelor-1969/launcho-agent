"""Local-only Launcho contract simulation and a separate widget host."""
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

from app.mock_draft_store import MockDraftError, MockDraftStore
from app.services.launcho_contract import DraftRequest
from app.services.catalog import selectable_catalog
from app.services.offer_contract import OfferStage, FinancialOffer

content = Path(__file__).resolve().parents[1] / 'content'
fixture = json.loads((content / 'launcho-mock.json').read_text(encoding='utf-8'))
public = json.loads((content / 'launcho-public.json').read_text(encoding='utf-8'))
ServiceKind = Literal['shop', 'website']


class OfferRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: ServiceKind
    # Optional in the demo; it validates a supported period, not campaign eligibility.
    planMonths: Literal[3, 6, 12] | None = None
    step: OfferStage
    objections: list[Literal['price', 'trust', 'complexity', 'time', 'template', 'domain', 'other']]
    needs: list[Literal['low_upfront', 'fast_launch', 'own_domain', 'support', 'other']]
    discountAlreadyShown: bool


def response(data, authorization):
    if authorization != 'Bearer local-simulation':
        raise HTTPException(status_code=401)
    return {'ok': True, 'data': data, 'simulation': True, 'notice': fixture['simulationNotice']}


def pricing(authorization: str = Header(default=''), kind: ServiceKind | None = None):
    data = fixture['pricing']
    if kind is not None:
        data = {key: value for key, value in data.items() if key != 'serviceDetails'}
        data = {**data, 'kind': kind, **fixture['pricing']['serviceDetails'][kind]}
    return response(data, authorization)


def signup_options(kind: ServiceKind, authorization: str = Header(default='')):
    return response(selectable_catalog(fixture['signupOptions'][kind], kind), authorization)


def service_info(authorization: str = Header(default='')):
    return response({
        **fixture['serviceInfo'],
        'overview': public['overview'],
        'featureSummary': public['featureSummary'],
    }, authorization)


def offers(request: OfferRequest, authorization: str = Header(default='')):
    eligible = (request.kind == 'shop' and request.step == 'review_ready' and 'price' in request.objections
                and 'low_upfront' in request.needs and not request.discountAlreadyShown)
    offers = []
    if eligible:
        for item in fixture['offers']:
            offer = FinancialOffer(offerId=item['id'], type=item['type'], kind='shop',
                displayText=item['line'], expiresAt='2099-01-01T00:00:00Z',
                source={'type': 'internal_fixture', 'reference': 'content/launcho-mock.json'},
                simulation=True, eligibleStages=['review_ready'], planMonths=[3, 6, 12])
            offers.append(offer.model_dump(mode='json'))
    return response({'offers': offers}, authorization)


def widget_host():
    origin = urlsplit(os.getenv('LAUNCHO_WIDGET_ORIGIN', 'http://127.0.0.1:8000'))
    if (origin.scheme != 'http' or origin.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or origin.username or origin.password or origin.path or origin.query or origin.fragment):
        raise HTTPException(500, detail='Invalid local widget origin')
    loader = f'http://{origin.hostname if origin.hostname != "::1" else "[::1]"}:{origin.port or 80}/widget/loader.js'
    return """<!doctype html>
<html lang="fa" dir="rtl">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>میزبان آزمایشی لانچو</title>
<style>
body { font-family: system-ui, sans-serif; margin: 0; color: #17264b; background: #f4f6fb }
header { padding: 24px max(24px, 8vw); background: white; font-weight: 750 }
main { max-width: 720px; margin: 12vh auto; padding: 24px; line-height: 1.9 }
p { max-width: 56ch }
</style>
<header>لانچو · محیط آزمایشی</header>
<main>
<h1>راه‌اندازی سایت و فروشگاه آنلاین</h1>
<p>دستیار را از پایین صفحه باز کنید. برای شروع بپرسید «برای فروش کیف و کفش از کجا شروع کنم؟» و بعد «هزینه برام زیاده، چه گزینه‌ای دارم؟».</p>
<p>این صفحه برای تست نصب ویجت است. تعرفه و جشنوارهٔ آزمایشی برای خرید معتبر نیستند.</p>
</main>
<script defer src="__WIDGET_LOADER__" data-theme="light"></script>
</html>""".replace("__WIDGET_LOADER__", loader)


def create_mock_app(*, store=None, db_path=None, catalog_profile=None, ttl=None,
                    retention=None, preview_origin=None):
    """Each test uses its own store/path; normal imports perform no database writes."""
    application = FastAPI(title='Launcho local simulation')
    profile = catalog_profile or os.getenv('LAUNCHO_MOCK_DRAFT_CATALOG', 'unavailable')
    if profile not in {'unavailable', 'test', 'widget'}:
        raise ValueError('LAUNCHO_MOCK_DRAFT_CATALOG must be unavailable, test, or widget.')
    catalog = fixture['signupOptions']
    if profile == 'test':
        catalog = json.loads((content / 'launcho-draft-test-catalog.json').read_text(encoding='utf-8'))['signupOptions']
    if profile == 'widget':
        catalog = json.loads((content / 'launcho-widget-catalog.json').read_text(encoding='utf-8'))['signupOptions']
    if store is not None:
        catalog = store.catalog
    draft_ttl = int(os.getenv('LAUNCHO_MOCK_DRAFT_TTL_SECONDS', '86400')) if ttl is None else ttl
    key_retention = int(os.getenv('LAUNCHO_MOCK_KEY_RETENTION_SECONDS', '604800')) if retention is None else retention
    if type(draft_ttl) is not int or type(key_retention) is not int or draft_ttl <= 0 or key_retention < draft_ttl:
        raise ValueError('Mock retention must be >= positive draft TTL.')
    path = db_path or os.getenv('LAUNCHO_MOCK_DB') or os.getenv('LAUNCHO_MOCK_DRAFT_DB') or content.parent / 'data' / 'mock-drafts.sqlite3'
    origin = preview_origin or os.getenv('LAUNCHO_MOCK_PREVIEW_ORIGIN', 'http://127.0.0.1:8001')
    MockDraftStore.validate_origin(origin)
    application.state.draft_store = store
    initialization = Lock()

    def get_store():
        with initialization:
            if application.state.draft_store is None:
                application.state.draft_store = MockDraftStore(
                    path, catalog, fixture['pricing'], ttl=draft_ttl, retention=key_retention,
                    preview_origin=origin)
            return application.state.draft_store

    def draft_error(status, code, message):
        return JSONResponse(status_code=status, content={
            'ok': False, 'error': {'code': code, 'message': message},
            'simulation': True, 'notice': fixture['simulationNotice']},
            headers={'Cache-Control': 'no-store'})

    @application.exception_handler(MockDraftError)
    async def handle_draft_error(request, error):
        return draft_error(error.status, error.code, error.message)

    @application.exception_handler(sqlite3.Error)
    @application.exception_handler(OSError)
    async def handle_storage_error(request, error):
        # A commit failure can have an uncertain outcome: retry the same key, never claim rejection.
        return draft_error(503, 'draft_outcome_unknown', 'ذخیره یا نتیجهٔ پیش‌نویس نامطمئن است؛ همان درخواست را با همان کلید تکرار کنید.')

    @application.exception_handler(RequestValidationError)
    async def handle_validation(request, error):
        if request.url.path == '/signup-drafts' or request.url.path.startswith('/signup-drafts/'):
            return draft_error(422, 'invalid_request', 'اطلاعات پیش‌نویس معتبر نیست.')
        from fastapi.exception_handlers import request_validation_exception_handler
        return await request_validation_exception_handler(request, error)

    def authenticated(authorization):
        if authorization != 'Bearer local-simulation':
            raise MockDraftError(401, 'unauthorized', 'دسترسی به mock مجاز نیست.')

    # Inline $defs so the standalone JSON Schema also resolves inside OpenAPI.
    schema = DraftRequest.model_json_schema()
    definitions = schema.pop('$defs', {})

    def inline_schema(value):
        if isinstance(value, list):
            return [inline_schema(item) for item in value]
        if isinstance(value, dict):
            if '$ref' in value and value['$ref'].startswith('#/$defs/'):
                target = definitions[value['$ref'].split('/')[-1]]
                return inline_schema({**target, **{k: v for k, v in value.items() if k != '$ref'}})
            return {key: inline_schema(item) for key, item in value.items()}
        return value

    @application.post('/signup-drafts', openapi_extra={'requestBody': {
        'required': True, 'content': {'application/json': {'schema': inline_schema(schema)}}}})
    async def create_draft(request: Request, authorization: str = Header(default=''),
                           idempotency_key: str = Header(default='')):
        authenticated(authorization)
        MockDraftStore.validate_key(idempotency_key)
        try:
            payload = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise MockDraftError(422, 'invalid_request', 'بدنهٔ JSON معتبر نیست.') from None
        if not isinstance(payload, dict):
            raise MockDraftError(422, 'invalid_request', 'بدنه باید یک شیء JSON باشد.')
        # Keep SQLite waits off the event loop, including concurrent requests.
        from starlette.concurrency import run_in_threadpool
        data = await run_in_threadpool(lambda: get_store().create(payload, idempotency_key))
        return JSONResponse(response(data, authorization), headers={'Cache-Control': 'no-store'})

    @application.get('/signup-drafts/{ref}')
    def read_draft(ref: str, authorization: str = Header(default='')):
        authenticated(authorization)
        return JSONResponse(response(get_store().get(ref), authorization), headers={'Cache-Control': 'no-store'})

    @application.get('/signup-drafts/{ref}/preview', response_class=HTMLResponse)
    @application.get('/mock-drafts/{ref}', response_class=HTMLResponse)
    def preview_draft(ref: str):
        # Public mock-only capability link. Never render the stored payload or business name.
        data = get_store().get(ref)
        expired = data['status'] == 'expired'
        status = 'این پیش‌نویس آزمایشی منقضی شده است.' if expired else 'پیش‌نویس فقط در mock ذخیره شده است.'
        html = ('<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>پیش‌نویس آزمایشی لانچو</title><main>'
                '<h1>پیش‌نویس آزمایشی — برای خرید معتبر نیست</h1><p>' + status + '</p>'
                '<p>هیچ پرداخت، ثبت‌نام واقعی، ساخت فروشگاه یا انتشاری انجام نشده است.</p></main></html>')
        return HTMLResponse(html, status_code=410 if expired else 200, headers={
            'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"})

    @application.get('/signup-options')
    def options(kind: ServiceKind, authorization: str = Header(default='')):
        authenticated(authorization)
        try:
            data = selectable_catalog(catalog[kind], kind, allow_test=profile in {'test', 'widget'} or store is not None)
        except (ValueError, KeyError, TypeError):
            raise MockDraftError(503, 'catalog_unavailable', 'کاتالوگ معتبر فعلاً در دسترس نیست.') from None
        return response(data, authorization)

    application.get('/pricing')(pricing)
    application.get('/service-info')(service_info)
    application.post('/offers/match')(offers)
    application.get('/', response_class=HTMLResponse)(widget_host)
    return application


app = create_mock_app(catalog_profile=os.getenv('LAUNCHO_MOCK_DRAFT_CATALOG', 'widget'))
