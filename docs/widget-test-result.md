# گزارش تست خودکار ویجت

- تاریخ: ۲۰۲۶-۱۱-۱۱
- شاخه: `test/conversation-widget-scenarios`
- نسخه کد برنامه: `ba2a6fc057c6aabc82783f931b57119a86651695`
- نتیجه اجرای مجدد: PASS، کد خروج صفر

```bash
node --experimental-vm-modules tests/widget_session_test.cjs
```

```text
PASS: relative URL cannot become an external protocol-relative URL
PASS: typing preserves session initialization error and retry
PASS: typing preserves guidance after unknown confirmation outcome
PASS: failed review refresh cannot authorize an old review
PASS: session lifecycle, authentication, click-only confirmation, exact retry, concurrency, expiry, and read-only mode
```

هشدار ExperimentalWarning مربوط به قابلیت VM Modules در Node است؛ تست‌ها موفق بودند.

این تست در محیط ایزوله با شبیه‌سازی رابط و شبکه اجرا می‌شود؛ کیفیت مدل واقعی، نمایش واقعی مرورگر و سرویس ساخت پیش‌نویس را بررسی نمی‌کند. گزارش شبیه‌سازی API در `docs/local-simulation-test-result.md` قرار دارد.
