from pathlib import Path
import mimetypes

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

# مسیر پوشهٔ استاتیک همیشه نسبت به ریشهٔ پروژه محاسبه می‌شود.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Launcho Agent API")

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
