# Launcho Agent

> **دموی برچسب‌خورده:** این نسخه برای بررسی مسیر نمایشی است؛ اتصال واقعی ثبت‌نام و انتشار نهایی برای مشتری آماده نیست. لینک پیش‌نویس فقط به صفحهٔ ثابت مجاز کنار فایل‌های ویجت می‌رود.

دستیار فارسی لانچو با FastAPI، loader بدون build، چت ایزوله در iframe و رابط ساخت فروشگاه مبتنی بر view سرور.

ویجت فعلی از قرارداد سادهٔ `POST /api/chat` با `{message}` و `{reply}` استفاده می‌کند. هستهٔ جدید بک‌اند مسیرهای session، مرور و تأیید مستقل نیز دارد؛ قرارداد و محدودیت آن در [راهنمای هسته](docs/core-api-contract.md) است. این رابط هنوز به آن مسیرها متصل نیست و ساخت واقعی تا تحویل adapter معتبر غیرفعال است. دریافت شماره موبایل، روش پرداخت، محاسبه مبلغ و تراکنش از محدودهٔ دستیار حذف شده‌اند. انتخاب دورهٔ اشتراک باقی است. نصب واقعی fallback به mock ندارد.

مسیر demo فقط این مراحل را دارد: نام کسب‌وکار ← دسته‌بندی ← دوره اشتراک ← قالب ← مرور اطلاعات ← تأیید ← لینک پیش‌نویس نمایشی. سؤال دامنه حذف شده است. لینک پایانی یک نمونهٔ ثابت محلی باز می‌کند؛ به اطلاعات واردشده متصل نیست و فروشگاه واقعی ایجاد نمی‌شود.

## اجرا در PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

اگر `.env` موجود است آن را بازنویسی نکنید. برای چت واقعی سه متغیر `AI_API_KEY`، `AI_BASE_URL` و `AI_MODEL_NAME` را با اطلاعات سرور تنظیم کنید. اتصال رسمی لانچو از `LAUNCHO_API_URL` و `LAUNCHO_API_KEY` استفاده می‌کند. فعال‌سازی پیش‌نویس در [راهنمای اجرا](docs/local-launcho-simulation.md) توضیح داده شده است. کلیدها فقط در سرور تنظیم شوند.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

نمونه: http://127.0.0.1:8000/widget/demo.html — با برچسب «حالت نمایشی»، بدون AI یا عملیات واقعی. اجرای صرفاً demo بدون تنظیمات واقعی:

```powershell
$env:AI_API_KEY='demo-placeholder'
$env:AI_BASE_URL='https://example.invalid/v1'
$env:AI_MODEL_NAME='demo'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

برای بررسی فقط frontend بدون نصب وابستگی‌های بک‌اند، در یک ترمینال جدا اجرا کنید:

```powershell
python tests/widget_preview_server.py --port 8000
```

این سرور فقط فایل‌های `frontend/` را ارائه می‌کند و API ندارد؛ مخصوص توسعه و demo است.

## نصب واقعی

```html
<script defer src="https://YOUR-SERVER/widget/loader.js"
  data-theme="light" data-position="right"
  data-offset="24" data-mobile-offset="16"></script>
```

برای نصب روی سایت اصلی، اسکریپت را از دامنهٔ جداگانهٔ ویجت (مثل `https://ag.launchox.ir`) بارگذاری کنید. iframe فقط بعد از بازکردن ویجت ساخته می‌شود. iframe و `/api/chat` روی مبدأ loader قرار دارند و `data-api-url` هم به همان مبدأ محدود است. در نصب واقعی از HTTPS استفاده کنید. `data-demo="true"` فقط برای نمونه است.

```javascript
LaunchoWidget.configure({theme:'light', position:'right', offset:24, mobileOffset:16});
LaunchoWidget.setTheme('dark'); // light، dark، auto
LaunchoWidget.open();
LaunchoWidget.close();
```

طبق درخواست بعدی کاربر، ظاهر کامیت `04a8489` حفظ شده است: قاب گرادیانی متحرک، هدر LAUNCHO، اندازه‌های متن قبلی، دکمه ۵۸×۵۸ و پنجره ۳۸۰×۴۵۰ محدود به viewport. تم پیش‌فرض loader حالت auto و تم demo روشن است. در موبایل ۱۲ پیکسل از طرفین فاصله دارد و با visualViewport محدود می‌شود. میزبان برای جلوگیری از پوشاندن کنترل‌های اصلی می‌تواند position و offset را تنظیم کند. نصب تکراری بی‌اثر است، iframe در اولین بازشدن ساخته می‌شود و بستن آن state را پاک نمی‌کند. Tab بین میزبان و پنل non-modal حرکت می‌کند؛ Escape focus را به دکمه برمی‌گرداند.

چت محدودیت ۵۰۰۰ کاراکتر، timeout برابر ۴۵ ثانیه و تلاش مجدد بدون تکرار حباب کاربر دارد. ویجت هنگام بازشدن `POST /api/sessions` را فراخوانی می‌کند. پیام را با `sessionId` و `requestId` به `POST /api/chat` می‌فرستد و توکن جلسه را در هدر `X-Session-Token` می‌گذارد. تلاش مجدد همان شناسهٔ پیام را به کار می‌برد. شناسه و توکن در حافظهٔ iframe نگهداری می‌شوند و با رفرش ویجت، جلسهٔ تازه آغاز می‌شود. [قرارداد اتصال ویجت](docs/widget-api-contract.md)

برای فعال‌سازی مراحل واقعی، ابتدا نفر اول endpoint آماده مطابق [قرارداد adapter](docs/widget-api-contract.md) تحویل دهد، سپس `data-workflow-url` تنظیم شود. سایت میزبان باید `launcho:templates:open` را دریافت کند و با `LaunchoWidget.selectTemplate({id,name,image})` انتخاب واقعی را برگرداند. demo همین hook را با قالب عمومی الماس شبیه‌سازی می‌کند. حفظ جلسه بین صفحات هنوز پیاده نشده است؛ از پنل همان صفحه یا تب تازه استفاده شود.

## فایل‌ها

| فایل | نقش |
| --- | --- |
| frontend/loader.js | Shadow DOM، دکمه، iframe، handshake، viewport، فاصله‌ها و hook قالب |
| frontend/widget.html | ساختار RTL، هدر، گفتگو و محل مراحل |
| frontend/widget.css | توکن‌ها، تم روشن/تیره، حباب‌ها و کارت‌های مراحل |
| frontend/widget.js | چت متصل به API موجود و دریافت پیام امن میزبان |
| frontend/api.js | transport موجود chat و timeout؛ بدون تغییر |
| frontend/workflow.js | رندر view سرور، ورودی، مرور/ویرایش، قفل و retry با idempotencyKey |
| frontend/workflow-api.js | adapter قابل پیکربندی و schema پاسخ؛ بدون endpoint حدسی |
| frontend/workflow-demo.js | fixture و transitionهای صرفاً نمایشی، import فقط با نصب صریح demo |
| frontend/demo.html | نصب نمونه، تم و شبیه‌سازی hook سایت میزبان |
| frontend/draft-preview.html | مقصد ثابت و صریحاً نمایشی لینک پیش‌نویس؛ بدون دادهٔ کاربر یا عملیات واقعی |
| frontend/assets/template-almas.webp | thumbnail قالب عمومی موجود، فقط برای demo |
| frontend/assets/Vazirmatn.woff2 و OFL.txt | فونت محلی موجود و مجوز SIL OFL |
| tests/widget_browser.py | مرورگر واقعی چت، دو origin، دو تم، ورودی، شبکه، امنیت و viewport |
| tests/widget_workflow_browser.py | ترتیب مراحل، ویرایش هر چهار انتخاب، لینک پیش‌نویس، رد قرارداد قدیمی و idempotency |
| docs/widget-gap-review.md | وضعیت اولیه ۱۲ بخش |
| docs/widget-api-contract.md | قرارداد نفر اول، hook میزبان و دارایی‌های نفر سوم |
| docs/widget-delivery.md | نتیجه بررسی نهایی، محدودیت‌ها و تحویل |

## تست بدون هزینه

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe tests/widget_browser.py
```

اگر Chrome نصب است:

```powershell
$env:LAUNCHO_BROWSER_CHANNEL='chrome'
.\.venv\Scripts\python.exe tests/widget_browser.py
```

`test_ai.py` درخواست واقعی هزینه‌دار می‌فرستد؛ اجرا نکنید. آزمون‌ها فقط `tests/` را اجرا می‌کنند. سرور مرورگر هم mock می‌شود تا حتی درخواست رهگیری‌نشده به AI نرود. اسکرین‌شات شروع، جمع‌آوری، قالب، مرور، پیش‌نویس و خطا در عرض‌های ۱۲۸۰، ۳۹۰ و ۳۲۰ و گزارش JSON در `artifacts/widget/` تولید می‌شوند. این پوشه در git نادیده گرفته می‌شود. viewport کوتاه جای آزمون کیبورد واقعی گوشی را نمی‌گیرد.

برای بررسی فقط مسیر نمایشی روی سرور frontend موجود، بدون وابستگی به FastAPI:

```powershell
python tests/widget_workflow_browser.py --base-url http://127.0.0.1:8000
```

این اجرا از Chrome نصب‌شده استفاده می‌کند و خروجی آن در `artifacts/widget-stage6/` است. گزارش‌های مرحله‌ای در `docs/widget-stage2-review.md` تا `docs/widget-stage6-review.md` ثبت می‌شوند.

## استقرار

فایل‌های frontend با mount `/widget` ارائه می‌شوند و مسیر `/static` نیز حفظ شده است. HTTPS، محدودسازی درخواست‌ها و دامنه مجاز را در استقرار تنظیم کنید. CSP سند iframe باید header واقعی `frame-ancestors` متناسب با دامنه‌های مجاز داشته باشد؛ `X-Frame-Options: SAMEORIGIN` نصب cross-origin را مسدود می‌کند. CSP میزبان باید سرور widget را در script-src و frame-src و استایل Shadow DOM را مجاز کند؛ سند iframe نیز font-src و connect-src مناسب لازم دارد. iframe/API پیش‌فرض هم‌origin‌اند؛ API خارجی به CORS همان سرور نیاز دارد. CORS موجود پروژه در این اصلاح frontend تغییر نکرده است.

## هسته گفتگو و تأیید پیش‌نویس

هستهٔ جدید ریموت در ادغام حفظ شده است: جلسهٔ پایدار SQLite، پیشنهاد اطلاعات غیرحساس توسط مدل، مرور متصل به revision، توکن مستقل تأیید و مسیر جداگانه برای رویداد دکمه. مدل ابزار ساخت ندارد. اتصال mock قدیمی برای نوشتن استفاده نمی‌شود؛ factory فعلی `can_create=False` دارد و تا تحویل adapter قراردادی، ساخت واقعی با 503 متوقف است. جزئیات و متغیرهای استقرار در [راهنمای هسته](docs/core-api-contract.md) است.

چت ویجت از مسیرهای جلسهٔ همین هسته استفاده می‌کند. قرارداد `data-workflow-url` برای گردش مرحله‌ای در سند ویجت توضیح داده شده است. برای اجرای دمو با API ساختگی، [راهنمای شبیه‌سازی محلی](docs/local-launcho-simulation.md) را دنبال کنید.

## قواعد معماری موجود

پایتون برای بک‌اند (D-001)، مونولیت ماژولار (D-002)، چند مدل نقش‌محور (D-003). اسناد decisions/architecture/budget که قبلاً در README ذکر شده بودند در این checkout موجود نیستند.

## استقرار روی Render

مخزن را به Render متصل و یک Blueprint از `render.yaml` ایجاد کنید. هنگام ساخت اولیه، کلید و شناسهٔ مدل را در داشبورد وارد کنید؛ کلید را در مخزن ننویسید.

فرمان ساخت: `pip install -r requirements.txt`

فرمان اجرا: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

مرجع تنظیمات: [مستندات رسمی Render](https://render.com/docs/blueprint-spec).

وابستگی‌ها قفل نسخه ندارند؛ پیش از انتشار نهایی، نسخه‌های محیط آزموده‌شده را تثبیت کنید.
