from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from app.services.ai_service import get_ai_response

router = APIRouter()

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)

    @field_validator("message", mode="before")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("Message must not be blank.")
        return value

@router.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, str]:
    return {"reply": get_ai_response(payload.message)}
