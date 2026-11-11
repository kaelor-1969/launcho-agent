"""Stage 3: browser checks for mocked chat replies and recovery.

With the frontend available locally:
  python tests/widget_responses_browser.py --base-url http://127.0.0.1:8000
Only the isolated test browser disables demo replies and intercepts /api/chat.
"""
import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect

OUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'widget-stage3'
CASES = [
    ('success', {'reply':'سلام! این پاسخ موفق آزمایشی است.'}),
    ('http-500', None),
    ('http-503', None),
    ('network', None),
    ('invalid-json', None),
    ('missing-reply', {}),
    ('numeric-reply', {'reply':123}),
    ('null-reply', {'reply':None}),
    ('blank-reply', {'reply':' \n\t '}),
    ('null-body', None),
    ('array-body', [{'reply':'این ساختار معتبر نیست'}]),
]


async def check(context, base, viewport, case, body):
    page = await context.new_page()
    requests, errors = [], []
    gate = asyncio.Event()
    arrived = asyncio.Queue()
    recovering = False
    reply = 'پاسخ آزمایشی پس از تلاش مجدد'
    text = 'سلام، می‌خواهم گل‌فروشی خودم را بسازم.'
    draft = 'پیش‌نویس بعدی من'
    page.on('pageerror', lambda e: errors.append(str(e)))

    async def installation(route):
        response = await route.fetch()
        await route.fulfill(response=response,
            body=(await response.text()).replace('data-demo="true"', 'data-demo="false"'))

    async def api(route):
        requests.append(route.request.post_data_json)
        arrived.put_nowait(len(requests))
        await gate.wait()
        if recovering:
            await route.fulfill(json={'reply':reply})
        elif case.startswith('http-'):
            await route.fulfill(status=int(case.split('-')[1]), body='server-private-detail')
        elif case == 'network':
            await route.abort('internetdisconnected')
        elif case == 'invalid-json':
            await route.fulfill(status=200, content_type='application/json', body='{broken')
        else:
            await route.fulfill(status=200, content_type='application/json',
                body=json.dumps(body, ensure_ascii=False))

    await page.route('**/widget/demo.html', installation)
    await page.route('**/api/**', api)
    result = {'viewport':viewport, 'case':case, 'status':'failed'}
    try:
        response = await page.goto(base.rstrip('/') + '/widget/demo.html')
        assert response.status == 200
        await page.locator('#launcho-widget .launcher').click()
        f = page.frame_locator('#launcho-widget iframe')
        entry, waiting = f.locator('#message'), f.locator('#waiting')
        send, retry, error = f.locator('#send'), f.locator('#retry'), f.locator('#error')
        await entry.fill(text)
        await entry.press('Enter')
        await asyncio.wait_for(arrived.get(), timeout=10)
        await expect(waiting).to_be_visible()
        await expect(send).to_be_disabled()
        gate.set()

        if case == 'success':
            await expect(f.locator('.assistant')).to_have_text('دستیار لانچو: ' + body['reply'])
            await expect(waiting).to_be_hidden()
            await expect(error).to_be_hidden()
            await entry.fill(draft)
            await expect(send).to_be_enabled()
            await page.screenshot(path=str(OUT / f'{viewport}-success.png'), animations='disabled')
        else:
            expected = ('ارسال پیام انجام نشد. دوباره تلاش کن.' if case.startswith('http-')
                else 'ارتباط برقرار نشد. اتصال اینترنتت را بررسی کن.' if case == 'network'
                else 'پاسخ معتبری دریافت نشد. دوباره تلاش کن.')
            await expect(f.locator('#error-text')).to_have_text(expected)
            await expect(waiting).to_be_hidden()
            await expect(retry).to_be_visible()
            await expect(retry).to_be_enabled()
            await expect(f.locator('.assistant')).to_have_count(0)
            await expect(f.locator('.user')).to_have_count(1)
            assert len(requests) == 1, 'Unexpected automatic retry'
            if case in ['http-500', 'network', 'invalid-json']:
                await page.screenshot(path=str(OUT / f'{viewport}-{case}-error.png'), animations='disabled')

            # A new message cannot bypass the failed turn or duplicate its bubble.
            await entry.fill(draft)
            await entry.press('Enter')
            await expect(f.locator('#error-text')).to_contain_text('تلاش مجدد')
            await expect(f.locator('.user')).to_have_count(1)
            assert requests == [{'message':text}]
            recovering = True
            gate.clear()
            await retry.click()
            await asyncio.wait_for(arrived.get(), timeout=10)
            await expect(waiting).to_be_visible()
            await expect(error).to_be_hidden()
            await expect(send).to_be_disabled()
            await entry.evaluate('''el => {
                for(let i=0;i<10;i++) {
                    document.querySelector('#retry').click();
                    el.form.requestSubmit();
                    el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
                }
            }''')
            assert requests == [{'message':text}, {'message':text}], requests
            await expect(f.locator('.user')).to_have_count(1)
            gate.set()
            await expect(f.locator('.assistant')).to_have_text('دستیار لانچو: ' + reply)
            await expect(waiting).to_be_hidden()
            await expect(error).to_be_hidden()
            await expect(entry).to_have_value(draft)
            await expect(send).to_be_enabled()
            if case in ['http-500', 'network', 'invalid-json']:
                await page.screenshot(path=str(OUT / f'{viewport}-{case}-recovered.png'), animations='disabled')

        # The next message works after either success or recovery.
        recovering = True
        await entry.press('Enter')
        await expect(f.locator('.assistant')).to_have_count(2)
        await expect(waiting).to_be_hidden()
        await expect(f.locator('.user')).to_have_count(2)
        await expect(error).to_be_hidden()
        expected_requests = [{'message':text}] * (1 if case == 'success' else 2) + [{'message':draft}]
        assert requests == expected_requests, requests
        assert not errors, errors
        result.update(status='passed', request_count=len(requests), user_messages=2,
            assistant_messages=2, page_errors=errors, retry_checked=case != 'success')
    except Exception as exc:
        result['failure'] = str(exc)
        await page.screenshot(path=str(OUT / f'{viewport}-{case}-FAILED.png'))
    finally:
        gate.set()
        await page.close()
    return result


async def main(base):
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        try:
            for name, width, height, mobile in [('desktop',1280,900,False), ('mobile',390,844,True)]:
                context = await browser.new_context(viewport={'width':width,'height':height},
                    is_mobile=mobile, has_touch=mobile, reduced_motion='reduce')
                try:
                    for case, body in CASES:
                        row = await check(context, base, name, case, body)
                        results.append(row)
                        (OUT / 'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
                        print(f"{name}/{case}: {row['status']}", flush=True)
                finally:
                    await context.close()
        finally:
            await browser.close()
    failures = [r for r in results if r['status'] != 'passed']
    print(f'{len(results)-len(failures)}/{len(results)} passed; report: {OUT / "report.json"}', flush=True)
    if failures:
        raise AssertionError(json.dumps(failures, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    asyncio.run(main(parser.parse_args().base_url))
