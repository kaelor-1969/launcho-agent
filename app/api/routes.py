import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.services.ai_service import get_ai_response

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    """پیام ورودی کاربر."""

    message: str = Field(min_length=1, max_length=5000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("لطفاً متن پیام را وارد کنید.")
        return value


class ChatResponse(BaseModel):
    """پاسخ دستیار."""

    reply: str


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        return ChatResponse(reply=get_ai_response(request.message))
    except Exception:
        # جزئیات خطا به کاربر نمایش داده نمی‌شود.
        logger.exception("خطا هنگام پردازش پیام کاربر")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="متأسفانه در پردازش پیام مشکلی پیش آمد. لطفاً دوباره تلاش کنید.",
        ) from None
