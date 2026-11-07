from app.services.ai_service import get_ai_response


def main() -> None:
    # این تست دستی درخواست واقعی به سرویس هوش مصنوعی ارسال می‌کند.
    print("--- Test 1: Normal Question ---")
    print(get_ai_response("لانچو چیست؟"))

    print("--- Test 2: Signup Draft Request ---")
    print(get_ai_response(
        "سلام، من می‌خوام ثبت‌نام کنم. اسم فروشگاهم نقرشی هست، دسته‌بندی پوشاک، قالب اول و دوره ۳ ماهه."
    ))


if __name__ == "__main__":
    main()
