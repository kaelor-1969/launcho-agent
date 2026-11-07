# Launcho Agent

دستیار هوش مصنوعی لانچو و ویجت فارسی قابل نصب روی سایت.

## وضعیت
نسخه اولیه — FastAPI و رابط چت داخل iframe، بدون build، ابزار، دیتابیس یا اتصال به کاتالوگ. هیچ منبع تعرفه یا امکاناتی به مدل متصل نیست؛ دکمه‌های شروع فقط سؤال را به API می‌فرستند.

## نصب و اجرا (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

اگر `.env` از قبل دارید، آن را بازنویسی نکنید. این متغیرها را در فایل ریشه تنظیم کنید:

```dotenv
AI_API_KEY=YOUR_SERVER_SIDE_KEY
AI_BASE_URL=https://YOUR-AI-GATEWAY/v1
AI_MODEL_NAME=YOUR_MODEL_NAME
LAUNCHO_API_URL=
LAUNCHO_API_KEY=
```

سه متغیر `AI_` الزامی‌اند. دو متغیر `LAUNCHO_` فعلاً استفاده نمی‌شوند. کلیدها فقط در سرور هستند؛ هرگز در تگ نصب، فایل‌های frontend یا آدرس API قرارشان ندهید.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- نمونه: http://127.0.0.1:8000/widget/demo.html
- سلامت: http://127.0.0.1:8000/
- API: `POST /api/chat` با `{"message":"سلام"}` و پاسخ `{"reply":"..."}`.

پیام پس از حذف فاصله ابتدا و انتها باید بین ۱ و ۵۰۰۰ کاراکتر باشد. فایل‌های static با مسیر مطلق نسبت به کد برنامه ارائه می‌شوند و به working directory وابسته نیستند.

## نصب روی سایت

```html
<script defer
  src="https://YOUR-SERVER/widget/loader.js"
  data-theme="auto"
  data-position="right"
  data-api-url="https://YOUR-SERVER/api/chat"></script>
```

`data-api-url` اختیاری است؛ پیش‌فرض `/api/chat` روی سرور loader است، نه سایت میزبان. آدرس نسبی API نسبت به آدرس loader تفسیر می‌شود. iframe نیز نسبت به همان فایل پیدا می‌شود. نصب باید از HTTP یا HTTPS انجام شود، نه `file://`.

- تم: `light`، `dark` یا `auto` (تم سیستم).
- موقعیت: `right` یا `left`.
- تغییر تنظیمات پس از اجرای loader:

```javascript
window.LaunchoWidget.setTheme('dark');
window.LaunchoWidget.configure({
  theme: 'light',
  position: 'left',
  apiUrl: 'https://YOUR-SERVER/api/chat'
});
window.LaunchoWidget.open();
window.LaunchoWidget.close();
```

میزبان باید تغییر تم خودش را با `setTheme` اعلام کند؛ CSS سایت به iframe منتقل نمی‌شود. در حالت `auto` تغییر تم سیستم پیگیری می‌شود. نمونه نیز همین API عمومی را استفاده می‌کند.

دکمه و محفظه در Shadow DOM هستند. iframe فقط در اولین بازشدن ساخته می‌شود و بستن آن جلسه را پاک نمی‌کند. اجرای دوباره loader بی‌اثر است. پنجره non-modal است؛ Tab امکان جابه‌جایی بین میزبان و گفتگو را دارد، Escape آن را می‌بندد و focus را به دکمه برمی‌گرداند. ارتباط با `postMessage` دارای بررسی دقیق origin، source و شناسه تصادفی جلسه است و تنظیمات پس از handshake ارسال می‌شوند.

## فایل‌های رابط

| فایل | کاربرد |
| --- | --- |
| `frontend/loader.js` | نصب دکمه و iframe، موقعیت، viewport موبایل و ارتباط با میزبان |
| `frontend/widget.html` | ساختار فارسی و دسترس‌پذیر گفتگو |
| `frontend/widget.css` | توکن‌های طراحی، دو تم و چیدمان واکنش‌گرا |
| `frontend/widget.js` | ورودی، پیام‌ها، انتظار، تلاش مجدد، focus و handshake |
| `frontend/api.js` | درخواست JSON، اعتبارسنجی پاسخ و timeout برابر ۴۵ ثانیه |
| `frontend/demo.html` | نصب واقعی با تگ script و انتخاب تم |
| `frontend/assets/Vazirmatn.woff2` | فونت محلی استفاده‌شده در iframe و نمونه |
| `frontend/assets/OFL.txt` | مجوز فونت |
| `tests/test_widget_static.py` | بررسی ارائه فایل‌ها، سلامت، API، محدودیت پیام و مسیر مستقل |
| `tests/widget_browser.py` | آزمون اختیاری Chromium و تولید اسکرین‌شات |
| `requirements-dev.txt` | وابستگی‌های آزمایش، جدا از اجرای برنامه |

`app/main.py` فقط برای mount مسیر `/widget` تغییر کرده است. در `app/api/routes.py` اعتبارسنجی trim قبل از محدودیت طول انجام می‌شود تا پیام ۵۰۰۰ کاراکتری همراه فاصله اضافی پذیرفته شود. قرارداد API، سرویس AI و CORS موجود حفظ شده‌اند.

## منبع طراحی و فونت

ظاهر فعلی مطابق مرجع «Paperclip-free light and dark chat panels» پیاده شده است: قاب ۳۸۰×۴۵۰ با حاشیه گرادیانی آبی/فیروزه‌ای، هدر گرادیانی و جداکننده عمودی، نام LAUNCHO در چپ، بستن در راست، خوش‌آمدگویی به شکل حباب کنار ربات، آواتارهای کاربر و دستیار، سه پیشنهاد کپسولی در یک ردیف و ورودی با دکمه ارسال گرد آبی. هر دو تم روشن و تیره مستقل طراحی شده‌اند. خوش‌آمدگویی و پیشنهادها در محتوای قابل اسکرول باقی می‌مانند. پیوست وجود ندارد، چون API فعلی ارسال فایل ندارد. تصاویر `reference-light.png` و `reference-dark.png` در خروجی تست مرورگر، یک گفتگوی کوتاه با پاسخ mock برای مقایسه ظاهری نشان می‌دهند؛ پیام نمایشی در خود برنامه درج نشده است.

رنگ‌ها و سطوح با CSS سایت [لانچو](https://launcho.ir/) بررسی شدند: آبی `#143EF2`، فیروزه‌ای `#00D8D1` و پس‌زمینه‌های روشن و تیره مطابق توکن‌های سایت‌اند. سایت فعلی در بخش اصلی از Dana استفاده می‌کند؛ این ویجت طبق مشخصات از Vazirmatn استفاده می‌کند. فونت متغیر از [مخزن رسمی Vazirmatn، نسخه v33.003](https://github.com/rastikerdar/vazirmatn/tree/v33.003) دریافت شده و تحت SIL Open Font License 1.1 است؛ متن کامل مجوز کنار فونت نگهداری می‌شود. آیکن‌های ساده SVG بخشی از رابط‌اند و لوگوی جدیدی ساخته نشده است.

## آزمایش بدون درخواست واقعی به مدل

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe tests/widget_browser.py
```

`test_ai.py` را اجرا نکنید: درخواست واقعی به مدل می‌فرستد. discovery بالا فقط پوشه `tests` را بررسی می‌کند. تست‌های سرور با mock اجرا می‌شوند. تست مرورگر نیز سرویس AI را در سرور آزمایشی جایگزین می‌کند و پاسخ‌های موفق و خطا را در مرورگر شبیه‌سازی می‌کند؛ کلید واقعی لازم ندارد.

تست مرورگر دو origin محلی، دسکتاپ و viewport موبایل، دو تم، نصب تکراری، بارگذاری تنبل، حفظ پیام، focus و Escape، ارسال کارت، متن امن، محدودیت ورودی، composition، Shift+Enter، قفل درخواست، خطاهای شبکه/HTTP/پاسخ نامعتبر، تلاش مجدد بدون تکرار پیام، رد پیام جعلی، اسکرول و تغییر تم سیستم را بررسی می‌کند. خروجی در `artifacts/widget/` است: هشت تصویر از شروع و گفتگو در دو تم و دو اندازه، و `report.json`. این مسیر وارد git نمی‌شود. آزمون viewport کوتاه جای آزمون کیبورد واقعی روی گوشی را نمی‌گیرد.

اگر Chrome روی سیستم نصب است، می‌توانید به‌جای دریافت Chromium از آن استفاده کنید:

```powershell
$env:LAUNCHO_BROWSER_CHANNEL='chrome'
.\.venv\Scripts\python.exe tests/widget_browser.py
```

## محدودیت‌ها و استقرار

- تاریخچه فقط در حافظه همین iframe است و با تازه‌سازی صفحه پاک می‌شود. مدل در هر درخواست فقط پیام جاری را می‌بیند؛ حافظه گفتگو ندارد.
- پاسخ‌ها متکی به دانش و دستور فعلی مدل‌اند؛ کاتالوگ، تعرفه و امکانات تأییدشده به آن متصل نیستند.
- بعضی خطاهای سرویس AI با HTTP 200 و متن `reply` برمی‌گردند؛ رابط همان متن را نمایش می‌دهد و از روی عبارت فارسی خطا تشخیص نمی‌دهد. تلاش مجدد برای خطاهای قابل تشخیص شبکه/HTTP/ساختار پاسخ با اقدام کاربر است. تا رفع خطای پیام قبلی، پیام تازه ارسال نمی‌شود تا ترتیب گفتگو حفظ شود.
- timeout رابط ۴۵ ثانیه و timeout سرویس AI ۳۰ ثانیه است؛ retry خودکار وجود ندارد. پس از timeout، تلاش مجدد ممکن است پردازش سرور را دوباره آغاز کند؛ API فعلی شناسه idempotency ندارد.
- در reverse proxy، برای سند `/widget/widget.html` هدر CSP مانند `Content-Security-Policy: frame-ancestors 'self' https://launcho.ir https://www.launcho.ir` را مطابق دامنه‌های واقعاً مجاز تنظیم کنید. این دستور باید هدر HTTP باشد؛ meta کافی نیست. هدر `X-Frame-Options: SAMEORIGIN` نصب روی دامنه متفاوت را مسدود می‌کند و باید برای این مسیر با سیاست CSP هماهنگ شود.
- CSP سایت میزبان باید سرور ویجت را در `script-src` و `frame-src` مجاز کند؛ برای loader فعلی اجازه style درون Shadow DOM نیز لازم است. CSP سند ویجت باید `connect-src` API و `font-src 'self'` را مجاز کند.
- در حالت پیش‌فرض، iframe و API هم‌origin هستند و نیازی به تغییر CORS نیست. API روی سرور جدا نیازمند CORS مناسب همان سرور است. CORS فعلی پروژه تغییر نکرده است.
- HTTPS را در استقرار استفاده کنید. پیش از استفاده عمومی، محدودسازی درخواست‌ها و سیاست دامنه‌های مجاز را در لایه استقرار تنظیم کنید.

## قواعد معماری
- پایتون، زبان بک‌اند (D-001)
- مونولیت ماژولار (D-002)
- چند مدل، نقش‌محور (D-003)

## اسناد
- `docs/decisions.md`
- `docs/architecture.md`
- `docs/budget.md`
