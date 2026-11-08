# دستیار هوشمند لانچو

نسخهٔ MVP دستیار لانچو با معماری یکپارچهٔ ماژولار (Modular Monolith)، برای پاسخ به پرسش‌ها و ساخت پیش‌نویس ثبت‌نام با Function Calling.
سرویس ثبت‌نام فعلاً Mock است و ثبت‌نام واقعی یا پرداخت انجام نمی‌دهد.

## فناوری‌ها

Python 3.10+، FastAPI، Uvicorn، Pydantic، OpenAI SDK و python-dotenv.

## اجرای محلی در PowerShell

دستورها را از ریشهٔ پروژه اجرا کنید:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

فقط اگر فایل `.env` ندارید، نمونه را کپی کنید:

```powershell
Copy-Item env.example .env
```

در `.env`، مقدار `AI_API_KEY` را با کلید واقعی و `AI_MODEL_NAME` را با شناسهٔ مدل فعال در درگاه که از ابزارها پشتیبانی می‌کند جایگزین کنید. مقدار `AI_BASE_URL` برابر `https://api.vitaico.ir/v1` است. فایل `.env` را کامیت نکنید.

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- سلامت سرویس: http://127.0.0.1:8000/
- مستندات API: http://127.0.0.1:8000/docs
- ویجت: http://127.0.0.1:8000/static/widget.html
- لودر: http://127.0.0.1:8000/static/loader.js

پوشهٔ `static` فعلاً خالی است؛ برای استفاده از دو آدرس آخر باید فایل‌های فرانت‌اند در آن قرار بگیرند.

## ساختار پروژه

```text
app/
  main.py                  ساخت برنامه، CORS و انتشار فایل‌های استاتیک
  api/routes.py            مسیر گفتگو: POST /api/chat
  core/config.py           خواندن متغیرهای محیطی
  models/schemas.py        مدل درخواست و پاسخ
  services/ai_service.py   ارتباط با مدل و اجرای ابزار
  services/launcho_api.py  سرویس Mock ثبت‌نام
  prompts/system_prompts.py  دستورهای سیستمی
content/                   محتوای دانشی؛ فعلاً خالی
static/                    فایل‌های فرانت‌اند؛ فعلاً خالی
tests/                     تست‌های پروژه
test_tools.py              تست دستی مدل
requirements.txt           وابستگی‌ها
render.yaml                تنظیم استقرار Render
env.example                نمونهٔ تنظیمات بدون اطلاعات محرمانه
```

## تست دستی

```powershell
.\venv\Scripts\python.exe test_tools.py
```

این اسکریپت درخواست واقعی ارسال می‌کند و ممکن است هزینه داشته باشد. تست‌های قدیمی پوشهٔ `tests` ممکن است با تغییرات فعلی قرارداد API نیاز به به‌روزرسانی داشته باشند.

## استقرار روی Render

مخزن را به Render متصل و یک Blueprint از `render.yaml` ایجاد کنید. هنگام ساخت اولیه، کلید و شناسهٔ مدل را در داشبورد وارد کنید؛ کلید را در مخزن ننویسید.

فرمان ساخت: `pip install -r requirements.txt`

فرمان اجرا: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

مرجع تنظیمات: [مستندات رسمی Render](https://render.com/docs/blueprint-spec).

وابستگی‌ها قفل نسخه ندارند؛ پیش از انتشار نهایی، نسخه‌های محیط آزموده‌شده را تثبیت کنید.


## هسته گفتگو و تأیید پیش‌نویس

هسته جلسه پایدار و تأیید مستقل اضافه شده است. مدل دیگر ابزار ساخت پیش‌نویس ندارد؛
فقط اطلاعات غیرحساس را پیشنهاد می‌دهد. ساخت از مسیر دکمه تأیید و snapshot سرور انجام می‌شود.
اتصال قدیمی mock برای نوشتن استفاده نمی‌شود و تا تحویل adapter قراردادی، ساخت واقعی غیرفعال است.
قرارداد هم‌تیمی‌ها و محدودیت‌های استقرار در [راهنمای هسته](docs/core-api-contract.md) است.
دستور تست بدون تماس واقعی: `venv\Scripts\python.exe -m unittest discover -s tests -v`.
