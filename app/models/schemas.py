from pydantic import BaseModel


class ChatRequest(BaseModel):
    # ساختار پیام دریافتی از کاربر
    message: str


class ChatResponse(BaseModel):
    # ساختار پاسخ دستیار
    reply: str
