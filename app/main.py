from pathlib import Path
import mimetypes
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.runtime import RuntimePolicy
from app.services.conversation_core import get_core

policy = RuntimePolicy()

# مسیر پوشهٔ استاتیک همیشه نسبت به ریشهٔ پروژه محاسبه می‌شود.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(_app):
    core = get_core()
    await asyncio.to_thread(core.store.cleanup)
    async def cleanup_loop():
        while True:
            await asyncio.sleep(300)
            try:
                await asyncio.to_thread(core.store.cleanup)
            except Exception:
                import logging
                logging.getLogger(__name__).error('session_cleanup_failed')
    worker = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


app = FastAPI(title="Launcho Agent API", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, _exc: RequestValidationError):
    # Pydantic error details can contain the rejected input, including credentials.
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "invalid_request", "message": "اطلاعات درخواست معتبر نیست."}},
        headers={"Cache-Control": "no-store"},
    )

# اجازهٔ دسترسی فرانت‌اند از همهٔ دامنه‌ها
app.add_middleware(
    CORSMiddleware,
    allow_origins=policy.origins or ([] if policy.production else ["*"]),
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-Token"],
    allow_credentials=False,
)


@app.middleware('http')
async def admission_and_headers(request: Request, call_next):
    response = None
    if request.url.path.startswith('/api/'):
        if not policy.admit(request.client.host if request.client else 'unknown'):
            response = JSONResponse(status_code=429, content={'detail': {'code': 'request_rate_limited'}},
                                    headers={'Retry-After': '60'})
        else:
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > policy.max_body:
                    response = JSONResponse(status_code=413, content={'detail': {'code': 'request_too_large'}})
                    break
                chunks.append(chunk)
            if response is None:
                request._body = b''.join(chunks)
    if response is None:
        response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self' " + ' '.join(policy.parents or ([] if policy.production else ['http://127.0.0.1:8001', 'http://localhost:8001']))
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/health/live')
def liveness():
    return {'status': 'ok'}


@app.get('/health/ready')
def readiness():
    try:
        core = get_core()
        with core.store.transaction() as db:
            db.execute('SELECT 1 FROM sessions LIMIT 1').fetchone()
        core.data('shop')
        return {'status': 'ready', 'adapterMode': core.gateway.mode}
    except Exception:
        return JSONResponse(status_code=503, content={'status': 'not_ready'})

@app.get('/static/widget.html', include_in_schema=False)
def legacy_widget():
    return RedirectResponse(url='/widget/widget.html', status_code=307)


@app.get('/static/loader.js', include_in_schema=False)
def legacy_loader():
    return RedirectResponse(url='/widget/loader.js', status_code=307)


# انتشار فایل‌هایی مانند ویجت و لودر
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/webp", ".webp")
app.mount("/widget", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend"), name="widget")


@app.get("/")
def health_check() -> dict[str, str]:
    # پاسخ ساده برای بررسی سلامت سرویس
    return {"status": "ok", "message": "Launcho Agent is running"}
