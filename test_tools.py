"""تست دستی اتصال واقعی به مدل و فراخوانی ابزار ثبت‌نام."""
import re
from unittest.mock import patch

from app.services import ai_service
from app.services.ai_service import get_ai_response


def main() -> None:
    print("Test 1: Normal Question")
    print(get_ai_response("لانچو چیست؟"))

    print("\nTest 2: Signup Draft Request")
    # تابع اصلی اجرا می‌شود؛ این پوشش فقط فراخوانی واقعی ابزار را ثبت می‌کند.
    with patch.object(
        ai_service, "create_signup_draft", wraps=ai_service.create_signup_draft
    ) as tool:
        reply = get_ai_response(
            "سلام، من می‌خوام ثبت‌نام کنم. اسم فروشگاهم نقرشی هست، "
            "دسته‌بندی پوشاک، قالب اول و دوره ۳ ماهه."
        )
        print(reply)
        tool.assert_called_once()

    if not isinstance(reply, str) or not re.search(
        r"https://launcho\.ir/start\?signup=sd_[A-Za-z0-9_-]+", reply
    ):
        raise AssertionError("لینک ثبت‌نام مورد انتظار در پاسخ پیدا نشد.")
    print("\nفراخوانی ابزار و لینک ثبت‌نام با موفقیت بررسی شدند.")


if __name__ == "__main__":
    main()
