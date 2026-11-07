from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import mimetypes
from app.api.routes import router

app = FastAPI(title="Launcho Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
# Windows MIME registries do not consistently recognize WOFF2.
mimetypes.add_type("font/woff2", ".woff2")
app.mount("/widget", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend"), name="widget")

@app.get("/")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
