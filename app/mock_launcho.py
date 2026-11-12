"""Local-only Launcho contract simulation and a separate widget host."""
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Path as PathParam
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas import DomainChoice, Preferences

content = Path(__file__).resolve().parents[1] / 'content'
fixture = json.loads((content / 'launcho-mock.json').read_text(encoding='utf-8'))
public = json.loads((content / 'launcho-public.json').read_text(encoding='utf-8'))
app = FastAPI(title='Launcho local simulation')
ServiceKind = Literal['shop', 'website']
DraftRef = Annotated[str, PathParam(pattern=r'^sd_[A-Za-z0-9_-]{4,128}$')]
DRAFT_TTL = timedelta(minutes=30)
DRAFT_DB = Path(os.getenv('LAUNCHO_MOCK_DRAFT_DB', str(content.parent / 'data' / 'mock-drafts.sqlite3')))

@contextmanager
def draft_db():
    DRAFT_DB.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DRAFT_DB, timeout=10)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS drafts (
            request_key TEXT PRIMARY KEY, fingerprint BLOB NOT NULL,
            ref TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL
        )''')
        db.execute('BEGIN IMMEDIATE')
        yield db


def draft_data(ref, expires_at):
    return {'ref': ref, 'status': 'expired' if datetime.now(timezone.utc) >= expires_at else 'draft',
            'expiresAt': expires_at.isoformat(), 'confirmUrl': f'/signup-drafts/{ref}/preview'}


class DraftRequest(Preferences):
    kind: ServiceKind
    businessName: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=100)
    planMonths: int = Field(strict=True, ge=1, le=120)
    template: str = Field(min_length=1, max_length=100)
    domain: DomainChoice


class OfferRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: ServiceKind
    # Optional in the demo; it validates a supported period, not campaign eligibility.
    planMonths: Literal[3, 6, 12] | None = None
    step: int = Field(ge=0, le=4)
    objections: list[Literal['price', 'trust', 'complexity', 'time', 'template', 'domain', 'other']]
    needs: list[Literal['low_upfront', 'fast_launch', 'own_domain', 'support', 'other']]
    discountAlreadyShown: bool


def require_local_token(authorization):
    if authorization != 'Bearer local-simulation':
        raise HTTPException(status_code=401)


def response(data, authorization):
    require_local_token(authorization)
    return {'ok': True, 'data': data, 'simulation': True, 'notice': fixture['simulationNotice']}


@app.get('/pricing')
def pricing(authorization: str = Header(default=''), kind: ServiceKind | None = None):
    data = fixture['pricing']
    if kind is not None:
        data = {key: value for key, value in data.items() if key != 'serviceDetails'}
        data = {**data, 'kind': kind, **fixture['pricing']['serviceDetails'][kind]}
    return response(data, authorization)


@app.get('/signup-options')
def signup_options(kind: ServiceKind, authorization: str = Header(default='')):
    return response(fixture['signupOptions'][kind], authorization)


@app.get('/service-info')
def service_info(authorization: str = Header(default='')):
    return response({
        **fixture['serviceInfo'],
        'overview': public['overview'],
        'featureSummary': public['featureSummary'],
    }, authorization)


@app.post('/offers/match')
def offers(request: OfferRequest, authorization: str = Header(default='')):
    eligible = (request.kind == 'shop' and 'price' in request.objections
                and 'low_upfront' in request.needs and not request.discountAlreadyShown)
    return response({'offers': fixture['offers'] if eligible else []}, authorization)


@app.post('/signup-drafts', status_code=201)
def create_signup_draft(
    request: DraftRequest,
    idempotency_key: Annotated[str, Header(pattern=r'^[A-Za-z0-9_-]{1,128}$')],
    authorization: str = Header(default=''),
):
    require_local_token(authorization)
    fingerprint = sha256(request.model_dump_json().encode('utf-8')).digest()
    with draft_db() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        db.execute('DELETE FROM drafts WHERE expires_at < ?', (cutoff.isoformat(),))
        previous = db.execute('SELECT fingerprint, ref, expires_at FROM drafts WHERE request_key = ?',
                              (idempotency_key,)).fetchone()
        if previous is not None:
            previous_fingerprint, ref, expires_at = previous
            if previous_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail={'code': 'idempotency_conflict'})
            draft = draft_data(ref, datetime.fromisoformat(expires_at))
            if draft['status'] == 'expired':
                raise HTTPException(status_code=410, detail={'code': 'draft_expired'})
            return response(draft, authorization)

        options = fixture['signupOptions'][request.kind]
        catalog = options['templates']
        templates = {item['id'] for item in catalog if item.get('available')}
        if request.category not in {item['id'] for item in options['businessCategories']}:
            raise HTTPException(status_code=422, detail={'code': 'invalid_category'})
        if request.template not in templates:
            raise HTTPException(status_code=422, detail={'code': 'invalid_template'})
        if request.planMonths not in {item['months'] for item in fixture['pricing']['plans']}:
            raise HTTPException(status_code=422, detail={'code': 'invalid_plan'})
        if request.domain.tld and request.domain.tld not in {item['tld'] for item in fixture['pricing']['domains']}:
            raise HTTPException(status_code=422, detail={'code': 'invalid_domain'})

        ref = 'sd_' + token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + DRAFT_TTL
        db.execute('INSERT INTO drafts VALUES (?, ?, ?, ?)',
                   (idempotency_key, fingerprint, ref, expires_at.isoformat()))
    return response(draft_data(ref, expires_at), authorization)


def find_draft(ref):
    with draft_db() as db:
        record = db.execute('SELECT expires_at FROM drafts WHERE ref = ?', (ref,)).fetchone()
    if record is None:
        raise HTTPException(status_code=404, detail={'code': 'draft_not_found'})
    return draft_data(ref, datetime.fromisoformat(record[0]))


@app.get('/signup-drafts/{ref}')
def signup_draft_status(ref: DraftRef, authorization: str = Header(default='')):
    require_local_token(authorization)
    return response(find_draft(ref), authorization)


@app.get('/signup-drafts/{ref}/preview', response_class=HTMLResponse)
def signup_draft_preview(ref: DraftRef):
    expired = find_draft(ref)['status'] == 'expired'
    title = 'پیش‌نویس آزمایشی منقضی شده' if expired else 'پیش‌نویس آزمایشی آماده است'
    return HTMLResponse(
        f'<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">'
        f'<title>{title}</title><h1>{title}</h1>'
        '<p>این صفحه برای توسعهٔ محلی است. حساب، فروشگاه یا پرداختی ایجاد نشده است.</p></html>',
        status_code=410 if expired else 200,
        headers={'Cache-Control': 'no-store'},
    )


@app.get('/', response_class=HTMLResponse)
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
<script defer src="__LOCAL_WIDGET_LOADER__" data-theme="light"></script>
</html>""".replace('__LOCAL_WIDGET_LOADER__', loader)
