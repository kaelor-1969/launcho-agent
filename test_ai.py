from app.services.ai_service import get_ai_response

def main() -> None:
    message = "اطلاعات معتبر: لانچو یک فروشگاه‌ساز آنلاین با هوش مصنوعی است. سؤال: لانچو چیست؟"
    print("Sending a test request...")
    print(get_ai_response(message))

if __name__ == "__main__":
    main()
