"""Local-only Launcho contract simulation and a separate widget host."""
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

content = Path(__file__).resolve().parents[1] / 'content'
fixture = json.loads((content / 'launcho-mock.json').read_text(encoding='utf-8'))
public = json.loads((content / 'launcho-public.json').read_text(encoding='utf-8'))
app = FastAPI(title='Launcho local simulation')
ServiceKind = Literal['shop', 'website']


class OfferRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: ServiceKind
    planMonths: int | None = Field(default=None, ge=1, le=120)
    step: int = Field(ge=0, le=4)
    objections: list[Literal['price', 'trust', 'complexity', 'time', 'template', 'domain', 'other']]
    needs: list[Literal['low_upfront', 'fast_launch', 'own_domain', 'support', 'other']]
    discountAlreadyShown: bool


def response(data, authorization):
    if authorization != 'Bearer local-simulation':
        raise HTTPException(status_code=401)
    return {'ok': True, 'data': data}


@app.get('/pricing')
def pricing(authorization: str = Header(default='')):
    return response(fixture['pricing'], authorization)


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
    eligible = (request.kind == 'shop' and request.step == 4 and 'price' in request.objections
                and 'low_upfront' in request.needs and not request.discountAlreadyShown)
    return response({'offers': fixture['offers'] if eligible else []}, authorization)


@app.get('/', response_class=HTMLResponse)
def widget_host():
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
<script defer src="http://127.0.0.1:8000/widget/loader.js" data-theme="light"></script>
</html>"""
