# نصب و بازیابی ویجت

این راهنما مکمل مستندات قبلی است؛ ادعاهای تاریخی README دربارهٔ refresh فقط برای حالت پیش‌فرض حافظه‌ای معتبرند. اتصال production، کاتالوگ رسمی و بازیابی نتیجهٔ نامعلوم هنوز وابستگی خارجی دارند.

## نصب

فایل‌های frontend و assets را در `/widget/` روی همان مبدأ API موجود ارائه کنید. نمونهٔ متصل `/widget/host-example.html` پاسخ ساختگی ندارد و فقط پس از بازکردن، جلسه ایجاد می‌کند. در سایت میزبان:

```html
<script defer src="https://YOUR-WIDGET-HOST/widget/loader.js?v=person1-1"
  data-auto-open="false" data-theme="light"
  data-session-recovery="tab"></script>
```

حذف `data-session-recovery` رفتار قبلی حافظه‌ای را حفظ می‌کند. این گزینه هنگام نصب ثابت است؛ configure در میانهٔ جلسه آن را تغییر نمی‌دهد. با `LaunchoWidget.open()` و `close()` همان iframe حفظ می‌شود؛ اجرای تکراری loader بی‌اثر است. برای آزمایش مستقل بدون API از demo.html استفاده کنید؛ این نمونه عمداً به بازیابی API متصل نمی‌شود.

برای نصب cross-origin آدرس مطلق loader لازم است. HTTPS، CSP میزبان با script-src/frame-src مناسب و header واقعی frame-ancestors سرویس باید توسط مالک استقرار تنظیم شوند. iframe نباید با X-Frame-Options:SAMEORIGIN از نصب روی مبدأ دیگر منع شود. API و توکن در مبدأ ویجت می‌مانند؛ data-api-url خارجی رد می‌شود. postMessage فقط با source، origin، scope و channel معتبر پذیرفته می‌شود؛ توکن و بدنهٔ تأیید به میزبان ارسال نمی‌شوند.

## بازیابی و حریم داده

در حالت tab فقط sessionId، sessionToken مالک و پرچم نتیجهٔ نامشخص در sessionStorage مبدأ ویجت با کلیدی وابسته به مبدأ میزبان ذخیره می‌شوند. تاریخچه، ترجیحات، revision، لینک پیش‌نویس و confirmationToken ذخیره نمی‌شوند. سرور منبع معتبر است. این سیاست opt-in است و تصویب production آن با مالک داده است. sessionStorage مجوز مقابله با XSS نیست؛ اسکریپت‌های هم‌مبدأ ویجت باید مورد اعتماد باشند. بعضی مرورگرها storage شخص ثالث را مسدود یا پارتیشن‌بندی می‌کنند؛ بازیابی میان تب‌ها/دستگاه‌ها تضمین نشده است.

پس از refresh میزبان یا iframe، GET جلسه با هدر X-Session-Token انجام می‌شود. تاریخچه و ترجیحات بازسازی می‌شوند؛ مرور قبلی قابل تأیید نیست و مرور تازه نیاز به اقدام کاربر دارد. completed فقط پس از GET draft-status لینک معتبر می‌دهد؛ انقضا لینک را غیرفعال می‌کند. creating/unknown یا پرچم pending قبلی، همهٔ مسیرهای تغییردهنده را قفل می‌کند. «تلاش مجدد» در این وضعیت فقط GET است. GET وضعیت ذخیره‌شده را می‌خواند و تضمین حل نتیجهٔ نامعلوم نمی‌دهد؛ برای ادامه به پشتیبانی/بک‌اند نیاز است.

با session_expired/not_found، جلسهٔ بدون عملیات معلق می‌تواند جایگزین شود؛ جلسهٔ معلق خودکار جایگزین نمی‌شود. storage خراب/مسدود رابط را crash نمی‌کند و هشدار بازیابی نشان داده می‌شود؛ در آن شرایط تداوم پس از refresh تضمین نیست. پاک‌کردن storage یا بستن تب می‌تواند قابلیت بازیابی را از دسترس خارج کند.

قطع/وصل شبکه صرفاً اعلان رابط را تغییر می‌دهد. پیام ناموفق با همان requestId و تأیید نامعلوم در همان اجرای iframe با همان بدنه و اقدام دستی retry می‌شود؛ نتیجهٔ timeout شکست قطعی نیست. پس از refresh توکن تأیید عمداً نگهداری نشده و retry تأیید بازسازی نمی‌شود. هشدار beforeunload بهترین تلاش مرورگر است و روی موبایل تضمین ندارد.

## قرارداد و اجرا

مسیرها: POST sessions؛ GET sessions/{id}؛ POST chat؛ PATCH sessions/{id}/preferences؛ POST review؛ POST confirm؛ GET draft-status. بدنه‌ها و خطاها در [قرارداد هسته](../core-api-contract.md) و ممیزی [progress.md](progress.md) هستند. گزینه‌ها فقط از GET local-signup-options?kind=shop|website در local_mock دریافت می‌شوند؛ endpoint production حدس زده نشده است.

برای سرویس محلی بدون AI، راهنمای [شبیه‌سازی محلی](../local-launcho-simulation.md) را دنبال کنید؛ هیچ `.env` موجودی را بازنویسی نکنید. مثال متصل به سرویس API نیاز دارد؛ static preview server فقط demo را اجرا می‌کند. ابعاد مرجع فعلی کد: workspace دسکتاپ67vw/85dvh، legacy380×450؛ موبایل<=600px و نمای کوتاه<=960×480 تمام‌صفحه می‌شوند. visualViewport فضای قاب را محدود می‌کند؛ کیبورد واقعی دستگاه بررسی نشده است.

از ریشهٔ مخزن، با Node دارای WebSocket و Chrome نصب‌شده:

```powershell
node --experimental-vm-modules tests/widget_recovery_test.cjs
node tests/widget_recovery_browser.cjs
node tests/widget_quality_check.cjs
```

CHROME_PATH مسیر Edge/Chrome و WIDGET_ARTIFACT_DIR پوشهٔ گزارش/تصویر را تعیین می‌کند. تست‌ها پاسخ کنترل‌شده دارند؛ موفقیت آن‌ها اتصال production را اثبات نمی‌کند. نیازهای دینا در [dependencies.md](dependencies.md) ثبت شده‌اند. نسخهٔ loader نصب و کش HTML/ماژول/CSS را هنگام تحویل واقعی به‌روز کنید؛ این کار در این وظیفه deployment انجام نمی‌دهد.
