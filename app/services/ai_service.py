import logging
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, AuthenticationError, PermissionDeniedError, RateLimitError
from app.core.config import settings

logger = logging.getLogger(__name__)
client = OpenAI(base_url=settings.AI_BASE_URL, api_key=settings.AI_API_KEY,
                timeout=30.0, max_retries=0)

SYSTEM_PROMPT = (
    "تو دستیار لانچو هستی. فقط بر اساس اطلاعات ارائه‌شده پاسخ بده. "
    "اگر پاسخ را نمی‌دانی یا اطلاعات کافی نداری، صریح بگو نمی‌دانم و چیزی نساز. "
    "پاسخ‌ها کوتاه و به زبان فارسی باشند."
)

def get_ai_response(user_message: str) -> str:
    message = user_message.strip()
    if not message:
        return "لطفاً پیام خود را وارد کنید."
    try:
        response = client.chat.completions.create(
            model=settings.AI_MODEL_NAME,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": message}],
            temperature=0.3,
        )
        if not response.choices:
            return "پاسخی از سرویس دریافت نشد. لطفاً دوباره تلاش کنید."
        reply = response.choices[0].message.content
        if not reply or not reply.strip():
            return "پاسخ سرویس خالی بود. لطفاً دوباره تلاش کنید."
        return reply.strip()
    except AuthenticationError:
        logger.error("AI gateway authentication failed.")
        return "اتصال دستیار به سرویس پیکربندی نشده است. لطفاً با پشتیبانی تماس بگیرید."
    except PermissionDeniedError:
        logger.error("AI gateway permission denied (403).")
        return "سرویس اجازه دسترسی به این درخواست را نداد. لطفاً با پشتیبانی تماس بگیرید."
    except RateLimitError:
        logger.warning("AI gateway rate limit reached.")
        return "سرویس فعلاً با محدودیت درخواست روبه‌رو است. کمی بعد تلاش کنید."
    except APITimeoutError:
        logger.warning("AI gateway request timed out.")
        return "دریافت پاسخ بیش از حد طول کشید. لطفاً دوباره تلاش کنید."
    except APIConnectionError:
        logger.warning("Could not connect to AI gateway.")
        return "ارتباط با سرویس برقرار نشد. لطفاً کمی بعد تلاش کنید."
    except APIError as exc:
        logger.error("AI gateway API error: %s", type(exc).__name__)
        return "سرویس پاسخ‌گویی موقتاً دچار خطا شده است. لطفاً دوباره تلاش کنید."
