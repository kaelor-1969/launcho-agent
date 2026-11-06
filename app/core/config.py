import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)

class Settings:
    def __init__(self) -> None:
        self.AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
        self.AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip()
        self.AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "").strip()
        self.LAUNCHO_API_URL = os.getenv("LAUNCHO_API_URL", "").strip()
        self.LAUNCHO_API_KEY = os.getenv("LAUNCHO_API_KEY", "").strip()
        for name in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL_NAME"):
            if not getattr(self, name):
                raise RuntimeError(f"{name} is missing. Set it in the project-root .env file.")

settings = Settings()
