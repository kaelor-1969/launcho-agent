import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings:
    def __init__(self) -> None:
        # کلید هر درگاه باید با آدرس همان درگاه استفاده شود.
        self.AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
        self.AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.vitaico.ir/v1").strip().rstrip("/")
        self.AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "").strip()
        self.AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
        self.AI_MAX_OUTPUT_TOKENS = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "160"))
        temperature = os.getenv("AI_TEMPERATURE", "").strip()
        # مقدار خالی یعنی پارامتر ارسال نشود؛ همهٔ مدل‌ها آن را نمی‌پذیرند.
        self.AI_TEMPERATURE = float(temperature) if temperature else None
        self.LAUNCHO_MOCK_URL = os.getenv("LAUNCHO_MOCK_URL", "").strip()
        self.LAUNCHO_API_URL = os.getenv("LAUNCHO_API_URL", "").strip()
        self.LAUNCHO_API_KEY = os.getenv("LAUNCHO_API_KEY", "").strip()
        self.LAUNCHO_ENABLE_DRAFTS = os.getenv("LAUNCHO_ENABLE_DRAFTS", "").strip() == "1"
        for name in ("AI_API_KEY", "AI_MODEL_NAME"):
            if not self.LAUNCHO_MOCK_URL and not getattr(self, name):
                raise RuntimeError(f"{name} is missing. Configure the project-root .env.")
        url = urlsplit(self.AI_BASE_URL)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise RuntimeError("AI_BASE_URL must be an HTTPS URL without credentials.")
        if not 0 < self.AI_TIMEOUT_SECONDS <= 120:
            raise RuntimeError("AI_TIMEOUT_SECONDS must be between 0 and 120.")
        if not 128 <= self.AI_MAX_OUTPUT_TOKENS <= 2048:
            raise RuntimeError("AI_MAX_OUTPUT_TOKENS must be between 128 and 2048.")
        if self.AI_TEMPERATURE is not None and not 0 <= self.AI_TEMPERATURE <= 2:
            raise RuntimeError("AI_TEMPERATURE must be between 0 and 2, or empty.")


settings = Settings()
