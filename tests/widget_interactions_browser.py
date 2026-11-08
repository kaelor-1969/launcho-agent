"""Stage 2 checks on /widget/demo.html. No backend or API requests needed.

Start the frontend server, then run:
  python tests/widget_interactions_browser.py
  python tests/widget_interactions_browser.py --base-url http://127.0.0.1:8000
"""
import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'widget-stage2'


async def check(browser, base, name, width, height, mobile):
    context = await browser.new_context(viewport={'width': width, 'height': height},
        is_mobile=mobile, has_touch=mobile, reduced_motion='reduce')
    page = await context.new_page()
    errors, api_requests = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))

    async def block_api(route):
        api_requests.append(route.request.url)
        await route.abort()

    await page.route('**/api/**', block_api)
    response = await page.goto(base.rstrip('/') + '/widget/demo.html')
    assert response.status == 200
    launcher = page.locator('#launcho-widget button')
    panel = page.locator('#launcho-widget .panel')
    await expect(launcher).to_have_attribute('aria-expanded', 'false')
    await expect(panel).to_be_hidden()
    await launcher.click()
    frame = page.frame_locator('#launcho-widget iframe')
    entry = frame.locator('#message')
    await expect(entry).to_be_focused()
    await frame.locator('body').evaluate('() => document.fonts.ready')

    # Persian text and ZWNJ survive input, multiline editing and submission.
    persian = 'سلام، یک گل‌فروشی دارم؛ می‌خواهم شروع کنم.'
    await entry.fill(persian)
    await entry.press('Shift+Enter')
    await entry.press('End')
    await entry.type('LAUNCHO 123')
    message = await entry.input_value()
    assert message == persian + '\nLAUNCHO 123', repr(message)

    # IME composition must not send the unfinished word.
    await entry.dispatch_event('compositionstart')
    await entry.press('Enter')
    await expect(frame.locator('.user')).to_have_count(0)
    await entry.dispatch_event('compositionend')
    await entry.press('Enter')
    await expect(frame.locator('#waiting')).to_be_visible()
    await expect(frame.locator('#send')).to_be_disabled()
    await expect(frame.locator('.user')).to_have_count(1)
    await expect(frame.locator('.user')).to_have_text('شما: ' + message)
    await page.screenshot(path=str(OUT / f'{name}-waiting.png'), animations='disabled')
    await expect(frame.locator('.assistant')).to_have_count(1)
    await expect(frame.locator('#waiting')).to_be_hidden()

    # Fill another message and flood both keyboard and form submission while
    # the previous turn is pending. The extra draft must stay available.
    await entry.fill('آزمایش جلوگیری از ارسال تکراری')
    # Keep the repeated events in one browser task so a slow test host cannot
    # finish the 700 ms demo response between automation round trips.
    await entry.evaluate('''(el, draft) => {
        el.form.requestSubmit();
        el.value = draft;
        el.dispatchEvent(new Event('input', {bubbles:true}));
        for (let i = 0; i < 12; i++) {
            el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
            el.form.requestSubmit();
            document.querySelector('#send').click();
        }
    }''', 'پیش‌نویس پیام بعدی')
    await expect(frame.locator('.user')).to_have_count(2)
    await expect(frame.locator('.assistant')).to_have_count(2)
    await expect(frame.locator('#waiting')).to_be_hidden()
    await expect(entry).to_have_value('پیش‌نویس پیام بعدی')
    await expect(frame.locator('#send')).to_be_enabled()

    # Close-button and launcher preserve the iframe, conversation and draft.
    before_url = await page.locator('#launcho-widget iframe').get_attribute('src')
    await frame.locator('#close').click()
    await expect(panel).to_be_hidden()
    await expect(launcher).to_be_focused()
    await launcher.click()
    await expect(entry).to_be_focused()
    await expect(frame.locator('.user')).to_have_count(2)
    await expect(entry).to_have_value('پیش‌نویس پیام بعدی')
    assert await page.locator('#launcho-widget iframe').get_attribute('src') == before_url
    await entry.press('Escape')
    await expect(panel).to_be_hidden()
    await expect(launcher).to_be_focused()
    await launcher.click()
    await launcher.click()
    await expect(panel).to_be_hidden()
    await launcher.click()
    await expect(entry).to_be_focused()

    # Generate actual messages, then scroll with mouse wheel or touch gestures.
    await entry.fill('پیام بلند برای آزمایش پیمایش. ' * 18)
    await entry.press('Enter')
    await expect(frame.locator('.assistant')).to_have_count(3)
    await expect(frame.locator('#waiting')).to_be_hidden()
    scroll = frame.locator('#scroll-area')
    await expect(scroll).to_have_js_property('scrollTop', await scroll.evaluate('el => el.scrollHeight - el.clientHeight'))
    box = await scroll.bounding_box()
    x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
    if mobile:
        cdp = await context.new_cdp_session(page)
        async def gesture(start_y, end_y):
            await cdp.send('Input.dispatchTouchEvent', {'type':'touchStart', 'touchPoints':[{'x':x,'y':start_y}]})
            for step in range(1, 9):
                await cdp.send('Input.dispatchTouchEvent', {'type':'touchMove', 'touchPoints':[{'x':x,'y':start_y+(end_y-start_y)*step/8}]})
                await asyncio.sleep(.025)
            await cdp.send('Input.dispatchTouchEvent', {'type':'touchEnd', 'touchPoints':[]})
        for _ in range(30):
            await gesture(box['y'] + 25, box['y'] + box['height'] - 25)
            await asyncio.sleep(.15)
            if await scroll.evaluate('el => el.scrollTop < 10'):
                break
    else:
        await page.mouse.move(x, y)
        await page.mouse.wheel(0, -10000)
    # Wait for native scrolling/inertia to settle, without modifying scrollTop.
    for _ in range(40):
        if await scroll.evaluate('el => el.scrollTop < 10'):
            break
        await asyncio.sleep(.1)
    metrics = await scroll.evaluate('el => ({top:el.scrollTop, height:el.clientHeight, total:el.scrollHeight})')
    assert metrics['top'] < 10, f'Cannot scroll to older messages: {metrics}'
    await page.screenshot(path=str(OUT / f'{name}-scroll-top.png'), animations='disabled')
    await entry.fill('پیام تازه هنگام مرور پیام‌های قبلی')
    await entry.press('Enter')
    await expect(frame.locator('.assistant')).to_have_count(4)
    await expect(frame.locator('#waiting')).to_be_hidden()
    await expect(scroll).to_have_js_property('scrollTop', await scroll.evaluate('el => el.scrollHeight - el.clientHeight'))
    for selector in ['#send', '#message', '#close']:
        b = await frame.locator(selector).bounding_box()
        assert b['y'] >= 0 and b['y'] + b['height'] <= height
    await page.screenshot(path=str(OUT / f'{name}-conversation.png'), animations='disabled')
    assert not errors, errors
    assert not api_requests, api_requests
    await context.close()
    return {'viewport':name, 'size':[width,height], 'status':'passed',
            'checks':['open-close', 'state-preserved', 'escape-focus', 'persian-zwnj',
                      'shift-enter', 'composition', 'waiting', 'duplicate-submit-lock',
                      'draft-during-wait', 'native-scroll', 'scroll-after-send', 'controls-visible'],
            'user_messages':4, 'assistant_messages':4, 'page_errors':errors,
            'api_requests':api_requests}


async def check_transport(browser, base, mobile):
    """Exercise sendMessage and the pending lock, with no live backend calls."""
    context = await browser.new_context(viewport={'width':390 if mobile else 1280,
        'height':844 if mobile else 900}, is_mobile=mobile, has_touch=mobile)
    page = await context.new_page()
    requests = []
    started, release = asyncio.Event(), asyncio.Event()

    async def chat(route):
        requests.append(route.request.post_data_json)
        started.set()
        await release.wait()
        await route.fulfill(json={'reply':'پاسخ آزمایشی برای بررسی قفل ارسال'})

    async def installation(route):
        response = await route.fetch()
        # Only this isolated browser context uses the API installation.
        await route.fulfill(response=response,
            body=(await response.text()).replace('data-demo="true"', 'data-demo="false"'))

    await page.route('**/api/chat', chat)
    await page.route('**/widget/demo.html', installation)
    try:
        await page.goto(base.rstrip('/') + '/widget/demo.html')
        launcher = page.locator('#launcho-widget button')
        await launcher.click()
        f = page.frame_locator('#launcho-widget iframe')
        entry = f.locator('#message')
        text = 'سلام، یک گل‌فروشی دارم'
        await entry.fill(text)
        await entry.press('Enter')
        await asyncio.wait_for(started.wait(), timeout=10)
        await expect(f.locator('#waiting')).to_be_visible()
        await expect(f.locator('#send')).to_be_disabled()
        await entry.fill('پیش‌نویس بعدی')
        await entry.evaluate('''el => {
            for (let i=0;i<20;i++) {
                el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
                el.form.requestSubmit(); document.querySelector('#send').click();
            }
        }''')
        await f.locator('#close').click()
        await launcher.click()
        await expect(f.locator('#waiting')).to_be_visible()
        await expect(entry).to_have_value('پیش‌نویس بعدی')
        assert requests == [{'message':text}], requests
        release.set()
        await expect(f.locator('.assistant')).to_have_count(1)
        await expect(f.locator('#waiting')).to_be_hidden()
        await expect(f.locator('#send')).to_be_enabled()
        assert requests == [{'message':text}], requests
        return {'viewport':'mobile' if mobile else 'desktop', 'status':'passed',
            'mode':'mocked-api', 'request_count':len(requests),
            'checks':['one-request-during-repeated-submit', 'pending-close-reopen',
                      'waiting-visible-until-response', 'draft-preserved', 'send-reenabled']}
    finally:
        release.set()
        await context.close()


async def main(base, transport_only=False):
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        try:
            if not transport_only:
                for args in [('desktop',1280,900,False), ('mobile',390,844,True), ('mobile-small',320,568,True)]:
                    results.append(await check(browser, base, *args))
            for mobile in [False, True]:
                results.append(await check_transport(browser, base, mobile))
        finally:
            await browser.close()
            filename = 'transport-report.json' if transport_only else 'report.json'
            (OUT / filename).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--transport-only', action='store_true')
    args = parser.parse_args()
    asyncio.run(main(args.base_url, args.transport_only))
