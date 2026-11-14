# شواهد اجرا

اجراهای این تحویل در ۱۴ نوامبر ۲۰۲۶ انجام شدند. پاسخ‌های API در آزمون‌های محلی کنترل‌شده‌اند؛ ایجاد فروشگاه، پرداخت، پیام مدل یا سازگاری اتصال رسمی تأیید نشده است. فایل‌های شاهد در Git و زیر همین پوشه نگهداری می‌شوند. مسیر تولید و SHA-256 هر نسخه در [evidence-manifest.json](evidence-manifest.json) آمده است.

## گزارش‌های آزمون

| گزارش | پوشش واقعی |
| --- | --- |
| [Chrome فرم](evidence/chrome-signup.json) | هر دو سرویس در عرض‌های ۱۲۸۰، ۳۹۰ و ۳۲۰، تمام ۲۳ انتخاب قالب و پیشنهادها، ویرایش/مرور، خطا، صفحه‌کلید، نام کنترل‌ها و کاهش حرکت |
| [Edge فرم](evidence/edge-signup.json) | همان مجموعه در مرورگر Edge؛ موتور همچنان Chromium است |
| [Chrome جلسه و لودر](evidence/chrome-sessions.json) | آفلاین واقعی مرورگر، پاسخ ناقص سوکت، retry با هویت ثابت، کلیک صریح/دابل‌کلیک، refresh، وضعیت، پیام جعلی iframe و timeout |
| [Edge جلسه و لودر](evidence/edge-sessions.json) | همان مجموعهٔ کامل با مرورگر Edge |
| [کاتالوگ HTTP](catalog-audit.json) | ۲۳ لینک پاسخ موفق؛ دو ردیف عمومی و نمونهٔ سایت‌ساز فاقد لینک |
| [رندر صفحات عمومی](public-preview-browser.json) | هر ۲۳ صفحه در Chrome، متن و حداقل یک تصویر بارگذاری‌شده؛ تضمین کامل تصاویر یا موجودبودن در ثبت‌نام نیست |

`node tests/widget_quality_check.cjs` در Chrome و Edge با کد خروج صفر تمام شد. پس از افزودن انتظار پایان انیمیشن برای تصاویر، آزمون فرم Chrome دوباره با خروج صفر اجرا شد. گزارش‌ها هیچ استثنای runtime ثبت نکردند. جزئیات مرز دسترس‌پذیری و مرورگرها در [browser-coverage.md](browser-coverage.md) است.

## تصاویر منتخب

این‌ها snapshotهای نقطه‌ای‌اند؛ بعضی کارت‌ها عمداً در موقعیت اسکرول پایین ثبت شده‌اند و تصویر کل گردش را نشان نمی‌دهد.

- [مرور فارسی فروشگاه در دسکتاپ](evidence/desktop-shop-review.png)
- [فرم سایت‌ساز در موبایل](evidence/mobile-website-form.png)
- [انتخاب سرویس در عرض ۳۲۰ با فوکوس مشخص](evidence/mobile-service-sheet.png)
- [مرور در تم تیره](evidence/mobile-dark-review.png)
- [نتیجهٔ نامعلوم و دکمهٔ بررسی همان درخواست](evidence/unknown-confirmation.png)
- [لینک ادامه پس از پاسخ معتبر fixture](evidence/continuation.png)
- [غیرفعال‌شدن لینک پس از گزارش انقضا](evidence/expired-status.png)
- [خطای بارگذاری iframe روی میزبان](evidence/loader-timeout.png)
- [نمونهٔ عمومی کلاسیک](evidence/public-classic.png) و [مدا](evidence/public-moda.png)

تصاویر ۲۳ پیش‌نمایش عمومی در `artifacts/widget-person3/public-previews/` محلی تولید شده‌اند؛ فقط دو نمونهٔ منتخب در Git هستند. تمام ۲۳ نتیجه در گزارش JSON ثبت شده‌اند. بعضی تصاویر محصول هنگام ثبت هنوز placeholder داشتند؛ رندر کامل همهٔ assetها و مقایسهٔ بصری تمام قالب‌ها ادعا نمی‌شود. متن `<script>bad()</script>` در برخی تصاویر fixture، دادهٔ عمدی آزمون متن امن است و اجرا نمی‌شود.

مسیرهای تولید: `artifacts/widget-signup-stage1/`، `artifacts/widget-person3/sessions/` و `artifacts/widget-person3/edge-final/{signup,sessions}/`. این پوشه‌ها خروجی محلی‌اند؛ نسخه‌های منتخب قابل بازبینی در `docs/widget-person3/evidence/` کپی شده‌اند. هیچ توکن جلسه یا بدنهٔ تأییدی در گزارش‌های منتخب ثبت نشده است.
