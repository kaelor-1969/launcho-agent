from pathlib import Path
import mimetypes

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

# مسیر پوشهٔ استاتیک همیشه نسبت به ریشهٔ پروژه محاسبه می‌شود.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Launcho Agent API")


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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# انتشار فایل‌هایی مانند ویجت و لودر
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)
mimetypes.add_type("font/woff2", ".woff2")
app.mount("/widget", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend"), name="widget")


@app.get("/")
def health_check() -> dict[str, str]:
    # پاسخ ساده برای بررسی سلامت سرویس
    return {"status": "ok", "message": "Launcho Agent is running"}
