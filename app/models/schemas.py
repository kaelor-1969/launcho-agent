from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    # ساختار پیام دریافتی از کاربر
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


class ChatResponse(BaseModel):
    # ساختار پاسخ دستیار
    reply: str
