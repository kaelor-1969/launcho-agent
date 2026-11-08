"""Verify untrusted messages remain literal text in the actual widget.

Run against a local frontend server:
  python tests/widget_security_browser.py --base-url http://127.0.0.1:8000
All chat responses are mocked. Payloads only set a local test marker.
"""
import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect

OUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'widget-stage4'
PAYLOADS = [
    ('script', "متن فارسی <script>window.__widgetXss=true;alert('widget-test')</script>"),
    ('img-onerror', '<img src="/__xss_probe__/image" onerror="window.__widgetXss=true">'),
    ('svg-onload', '<svg onload="window.__widgetXss=true"></svg>'),
    ('iframe-srcdoc', '<iframe srcdoc="<script>parent.__widgetXss=true</script>"></iframe>'),
    ('closing-tags', '</p></div><style>body{display:none}</style><img src="/__xss_probe__/breakout" onerror="window.__widgetXss=true">'),
    ('javascript-link', '<a href="javascript:window.__widgetXss=true">لینک آزمایشی</a>'),
    ('html-entities', '&lt;img src=x onerror="window.__widgetXss=true"&gt; &amp; &#60;script&#62;'),
    ('markdown', '[لینک](javascript:window.__widgetXss=true) ![تصویر](/__xss_probe__/markdown)'),
]

# Record the actual DOM sink used by the application, alongside behavioral checks.
INSTRUMENT = '''() => {
    window.__widgetXss = false;
    window.__textWrites = [];
    const descriptor = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
    Object.defineProperty(Node.prototype, 'textContent', {
        ...descriptor,
        set(value) {
            if (this instanceof Element && this.classList.contains('bubble'))
                window.__textWrites.push({className:this.className, value:String(value)});
            return descriptor.set.call(this, value);
        }
    });
}'''


async def check(browser, base, name, mobile):
    context = await browser.new_context(viewport={'width':390 if mobile else 1280,
        'height':844 if mobile else 900}, is_mobile=mobile, has_touch=mobile,
        reduced_motion='reduce')
    await context.add_init_script('(' + INSTRUMENT + ')()')
    results = []
    try:
        # Positive control: an intentionally unsafe page must trip our marker.
        control = await context.new_page()
        await control.set_content('<img src="data:," onerror="window.__widgetXss=true">')
        await control.wait_for_function('window.__widgetXss === true')
        await control.close()

        page = await context.new_page()
        errors, dialogs, probes, requests = [], [], [], []
        page.on('pageerror', lambda e: errors.append(str(e)))

        async def dialog(d):
            dialogs.append(d.message)
            await d.dismiss()

        async def probe(route):
            probes.append(route.request.url)
            await route.abort()

        async def installation(route):
            response = await route.fetch()
            await route.fulfill(response=response,
                body=(await response.text()).replace('data-demo="true"', 'data-demo="false"'))

        async def api(route):
            data = route.request.post_data_json
            requests.append(data)
            await route.fulfill(json={'reply':data['message']})

        page.on('dialog', dialog)
        await page.route('**/widget/demo.html', installation)
        await page.route('**/__xss_probe__/**', probe)
        await page.route('**/api/**', api)
        await page.goto(base.rstrip('/') + '/widget/demo.html')
        launcher = page.locator('#launcho-widget button')
        await launcher.click()
        f = page.frame_locator('#launcho-widget iframe')
        entry = f.locator('#message')
        await expect(entry).to_be_focused()
        frame_url = await page.locator('#launcho-widget iframe').get_attribute('src')
        for index, (case, payload) in enumerate(PAYLOADS, 1):
            await entry.fill(payload)
            await entry.press('Enter')
            await expect(f.locator('.assistant')).to_have_count(index)
            await expect(f.locator('#waiting')).to_be_hidden()
            for role, prefix in [('user','شما: '), ('assistant','دستیار لانچو: ')]:
                bubble = f.locator('.' + role).last
                assert await bubble.text_content() == prefix + payload
                structure = await bubble.evaluate('''el => ({
                    tags:Array.from(el.querySelectorAll('*'), n=>n.tagName),
                    rawText:el.lastChild.nodeType === Node.TEXT_NODE ? el.lastChild.data : null,
                    writes:window.__textWrites.filter(w=>w.className===el.className),
                    marker:window.__widgetXss
                })''')
                assert structure['tags'] == ['SPAN'], structure
                assert structure['rawText'] == payload, structure
                assert structure['writes'][-1]['value'] == payload, structure
                assert structure['marker'] is False, structure
            assert not dialogs and not probes and not errors, (dialogs, probes, errors)
            assert len(page.frames) == 2, 'Payload created a frame'
            assert await page.locator('#launcho-widget iframe').get_attribute('src') == frame_url
            assert await page.evaluate('window.__widgetXss') is False
            assert requests[-1] == {'message':payload}
            if case in ['script', 'img-onerror', 'javascript-link']:
                await page.screenshot(path=str(OUT / f'{name}-{case}.png'), animations='disabled')
            results.append({'viewport':name, 'case':case, 'status':'passed',
                'user_and_reply_literal':True, 'textContent_observed':True,
                'payload_elements_created':0, 'script_marker':False})
            print(f'{name}/{case}: passed', flush=True)

        # Session preservation must not re-parse earlier messages as HTML.
        await f.locator('#close').click()
        await launcher.click()
        await expect(f.locator('.assistant')).to_have_count(len(PAYLOADS))
        assert await f.locator('body').evaluate('window.__widgetXss') is False
        assert not dialogs and not probes and not errors
        assert len(requests) == len(PAYLOADS)
        return {'viewport':name, 'positive_control':'passed', 'payloads':results,
            'request_count':len(requests), 'dialogs':dialogs, 'payload_requests':probes,
            'page_errors':errors, 'close_reopen':'passed'}
    finally:
        await context.close()


async def main(base):
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome')
        try:
            for name, mobile in [('desktop',False), ('mobile',True)]:
                results.append(await check(browser, base, name, mobile))
        finally:
            await browser.close()
            (OUT / 'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{sum(len(r["payloads"]) for r in results)} payload scenarios passed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    asyncio.run(main(parser.parse_args().base_url))
