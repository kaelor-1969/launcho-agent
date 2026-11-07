# قراردادهای اتصال ویجت

## API موجود

فقط `POST /api/chat` موجود است: ورودی `{ "message": "..." }` و خروجی `{ "reply": "..." }`. رابط production همین قرارداد را حفظ می‌کند. مدل فقط پیام جاری را می‌بیند. متغیرهای `LAUNCHO_API_*` در بک‌اند مصرف نمی‌شوند. endpoint مراحل، کاتالوگ، دامنه، quote، پیش‌نویس و تراکنش وجود ندارد. هیچ آدرسی برای این قابلیت‌ها حدس زده نشده است.

## adapter پیشنهادی نفر اول

با `data-workflow-url` یا `LaunchoWidget.configure({workflowUrl: 'https://…'})` آدرس واقعی تحویل‌داده‌شده را تعیین کنید. این API هنوز در پروژه پیاده نشده است. یک endpoint ساخت‌یافته با POST/JSON، CORS مخصوص origin ویجت، HTTPS و session سمت سرور لازم است. کلید سرور به مرورگر ارسال نمی‌شود. transport فعلی `credentials: omit` دارد؛ sessionId باید شناسه تصادفی غیرقابل حدس، کوتاه‌عمر و محدود به همان جلسه باشد. برای ورود حساب کاربری، قرارداد احراز هویت جدا باید قبل از استقرار نهایی تعیین شود؛ credential در URL قرار نگیرد.

هر درخواست:

```json
{"action":"next","sessionId":"opaque-session","revision":3,"data":{"field":"mobile","value":"09123456789"}}
```

برای شروع sessionId و revision مقدار null دارند. پاسخ همیشه یک view کامل است؛ تعیین مرحله و تصمیم بعدی فقط روی سرور است:

```json
{
  "sessionId":"opaque-session", "revision":4,
  "kind":"field", "field":"subscription",
  "title":"اشتراک را مشخص کن", "value":"6",
  "options":[{"id":"6","label":"شش‌ماهه"}],
  "actions":[{"id":"next","label":"ادامه"}]
}
```

`kind`: field، template، review، draft، payment، result.

`field`: businessName، category، domain، mobile، subscription، setupPayment. ورودی تلفن به ارقام ASCII تبدیل می‌شود؛ اعتبارسنجی و ذخیره نهایی سمت سرور است. `options` از داده سرور می‌آید. `value` مقدار فعلی همان فیلد است. در هر view فقط یک انتخاب/سؤال فعال است. `title`، `description`، `rows:[{label,value}]` و `actions:[{id,label,disabled?}]` فقط به شکل متن رندر می‌شوند.

| action | ورودی اضافه | پاسخ مورد انتظار / مسئولیت سرور |
| --- | --- | --- |
| start | بدون داده | ایجاد یا بازیابی جلسه و مرحله اول |
| next | field، value | اعتبارسنجی، ثبت مقدار، view بعدی |
| checkDomain | field:domain، value | domainStatus: unchecked/checking/available/unavailable/error؛ هیچ ثبت یا رزروی انجام نمی‌دهد |
| selectTemplate | template:{id,name,image} | بررسی شناسه واقعی و برگرداندن اطلاعات معتبر قالب و مرحله بعد |
| edit | بدون داده | انتخاب فیلد مورد ویرایش با actions |
| edit:نام‌فیلد | بدون داده | مقدار قبلی و فرم همان فیلد؛ پس از next بازگشت به مرور اصلاح‌شده |
| createDraft | idempotencyKey در ریشه درخواست | فقط از view مرور و تأیید صریح؛ draftId و confirmed:true برای موفقیت |
| continuePayment | بدون داده | quote معتبر و view هزینه |
| editPayment | بدون داده | اشتراک/روش پرداخت فعلی؛ quote جدید و ادامه همان draft طبق تصمیم سرور |
| refreshQuote | بدون داده | quote جدید بعد از انقضا |
| pay | sessionId، revision | ایجاد تراکنش طبق quote جاری؛ checkoutUrl از HTTPS و transactionId معتبر |
| checkPayment | بدون داده | استعلام تراکنش جاری از سرور؛ paymentStatus و verified |

شناسه اقدامات کمکی می‌تواند داده‌محور باشد. `browseTemplates` در مرورگر به hook میزبان تبدیل می‌شود و API را صدا نمی‌زند. ساخت و پرداخت باید دوباره روی سرور به مرحله، revision و تأیید کاربر محدود شوند. `createDraft` با قفل همزمانی و یک idempotencyKey ثابت در retry دستی ارسال می‌شود. هنگام ویرایش و دریافت مرور تازه، کلید تازه ساخته می‌شود. سرور باید ذخیره نتیجه و بازیابی نتیجه همان کلید، از جمله پس از timeout، را تضمین کند. پشتیبانی آن در بک‌اند فعلی وجود ندارد؛ نبود آن مانع فعال‌سازی ساخت واقعی است. هیچ retry خودکار وجود ندارد.

### دامنه، مرور و مبلغ

نام دامنه عوض شد، نتیجه قبلی قابل استفاده نیست. `available` به معنی رزرو نیست. متن هزینه دامنه باید از description/rows معتبر سرور بیاید. مرور باید businessName، category، domain و وضعیت، template، mobile، اشتراک و quote معتبر را شامل شود. کارت قالب از `template:{id,name,image}` استفاده می‌کند؛ برای امکان تغییر، action با id مناسب سرور و برچسب «تغییر قالب» ارائه شود.

```json
{"quote":{"id":"quote-id","currency":"TOMAN","today":7750000,"expiresAt":"2026-11-08T12:00:00Z"}}
```

واحد فعلی adapter صریحاً تومان است؛ پاسخ ریالی رد می‌شود، تبدیل حدسی نداریم. هزینه اشتراک، سهم راه‌اندازی امروز، مجموع راه‌اندازی، اقساط مانده و سررسیدهای واقعی به صورت rows از سرور دریافت می‌شوند. دکمه pay مبلغ `quote.today` را نشان می‌دهد و پس از انقضا غیرفعال است. action `refreshQuote` باید از سرور ارائه شود. هیچ فرمول مالی production در رابط نیست. pay در demo همیشه غیرفعال است. یک لینک درگاه فقط بعد از پاسخ معتبر و با اقدام کاربر در تب جدید باز می‌شود تا iframe حفظ شود.

### نتیجه و خطا

`paymentStatus`: success، failed، cancelled، unknown. success فقط با `verified:true` از سرور پذیرفته می‌شود. unknown نباید action pay داشته باشد و باید ابتدا checkPayment ارائه کند. callback مرورگر یا query string هیچ‌کدام وضعیت موفق نمی‌سازند. نتیجه ناموفق باید همان داده‌ها و retry کنترل‌شده را حفظ کند؛ تاریخچه تراکنش و جلوگیری از پرداخت مضاعف با سرور است.

پیشنهاد کدهای خطا: 422 مقدار نامعتبر، 409 revision قدیمی/درخواست در حال انجام، 410 جلسه یا quote منقضی، 429 محدودیت، 5xx اختلال. پاسخ‌های غیرموفق state موفق نمی‌سازند؛ رابط پیام ساده و retry دستی نشان می‌دهد و view قبلی را نگه می‌دارد. پاسخ موفق HTTP باید schema کامل و revision صعودی همان session را داشته باشد. برای پیام خطای اختصاصی فیلد و بازیابی session منقضی، قرارداد تکمیلی لازم است؛ رابط فعلی خطا را عمومی نمایش می‌دهد.

## اتصال سایت میزبان و قالب (نفر اول / تیم سایت)

بخش عمومی موجود در `https://launcho.ir/#templates` در تاریخ بررسی وجود داشت. slug عمومی `almas`، نام الماس و تصویر آن از همین صفحه خوانده شد؛ تأیید برابری slug عمومی با شناسه داخلی API هنوز لازم است. هیچ تعداد ثابت یا کاتالوگ تازه‌ای ساخته نشده است.

```javascript
window.addEventListener('launcho:templates:open', event => {
  // بخش موجود سایت را بدون navigation در همین صفحه نمایش دهید.
  // پس از انتخاب کاربر، داده معتبر همان قالب موجود را برگردانید:
  event.detail.select({id: realTemplate.id, name: realTemplate.name, image: realTemplate.image});
});
// جایگزین همان callback:
window.LaunchoWidget.selectTemplate({id, name, image});
```

میزبان لازم است hook را نصب کند؛ loader بدون حدس درباره DOM سایت رویداد صادر می‌کند. demo یک انتخاب از قالب عمومی موجود را شبیه‌سازی می‌کند، نه اتصال واقعی کاتالوگ. فقط iframe ثبت‌شده با origin، source و channel همان نصب پیام انتخاب را می‌پذیرد؛ قالب مجدداً در API بررسی می‌شود. مقادیر ناقص و پروتکل نامعتبر رد می‌شوند.

حفظ داده فعلاً فقط تا زنده‌بودن iframe در همین صفحه تضمین می‌شود. برای رفتن به صفحه دیگر در همان تب، API بازیابی جلسه و توکن امن مطابق سیاست سایت لازم است. در این نسخه هیچ اطلاعات شخصی در URL، console، localStorage یا sessionStorage نوشته نمی‌شود. درگاه/قالب در تب تازه یا پنل همان صفحه باید باز شود؛ حفظ جلسه میان navigation ادعا نمی‌شود.

## دارایی‌های نفر سوم

فونت Vazirmatn محلی و آیکن‌های فعلی آماده‌اند. برای تأیید نهایی برند: لوگو/آواتار نهایی، تصاویر و نام‌های canonical قالب‌ها از کاتالوگ معتبر و تأیید دسترسی استفاده از thumbnail دریافت‌شده لازم است. تصویر `template-almas.webp` فقط fixture demo از تصویر عمومی فعلی سایت است؛ دارایی یا شناسه جدیدی اختراع نشده است.
