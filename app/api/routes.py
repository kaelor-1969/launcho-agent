from fastapi import APIRouter, HTTPException

from app.models.schemas import ChatRequest, ChatResponse
from app.services.ai_service import get_ai_response

router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    # اجرای سرویس همگام در مسیر همگام فست‌API
    try:
        return ChatResponse(reply=get_ai_response(request.message))
    except Exception:
        # جزئیات داخلی خطا به کاربر نمایش داده نمی‌شود.
        raise HTTPException(
            status_code=500,
            detail="متأسفانه در حال حاضر مشکلی پیش آمده است.",
        ) from None
