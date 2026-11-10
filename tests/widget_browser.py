"""Optional real Chromium checks. All AI calls are replaced locally.

Run: python tests/widget_browser.py
Screenshots and report: artifacts/widget/
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from playwright.async_api import async_playwright, expect
from widget_workflow_browser import run_workflow_checks

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "widget"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    class Host(BaseHTTPRequestHandler):
        def do_GET(self):
            body = f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
            <script src="{base}/widget/loader.js" data-theme="light"></script></head>
            <body><button id="host-action">Host action</button><p>Separate origin installation</p></body></html>'''.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    host = ThreadingHTTPServer(("127.0.0.1", 0), Host)
    threading.Thread(target=host.serve_forever, daemon=True).start()
    host_url = f"http://127.0.0.1:{host.server_port}"
    env = {**os.environ, "AI_API_KEY": "browser-test-placeholder", "AI_BASE_URL": "https://example.invalid/v1", "AI_MODEL_NAME": "test-model"}
    # Patch on the server as well, so even a missed interception cannot call AI.
    code = f"from app.main import app; import app.api.routes as r; r.get_ai_response=lambda message: 'test server reply'; import uvicorn; uvicorn.run(app,host='127.0.0.1',port={port},log_level='error')"
    log = (OUTPUT / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdout=log, stderr=log)
    results = []
    try:
        async with httpx.AsyncClient() as client:
            for _ in range(100):
                try:
                    if (await client.get(base + "/")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.1)
            else:
                raise RuntimeError("Local test server did not start")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel=os.getenv("LAUNCHO_BROWSER_CHANNEL") or None)
            for mobile in [False, True]:
                for theme in ["light", "dark"]:
                    context = await browser.new_context(viewport={"width": 390 if mobile else 1280, "height": 844 if mobile else 900}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1, reduced_motion="reduce" if mobile else "no-preference")
                    page = await context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    requests = []
                    mode = {"value": "success"}

                    async def api(route):
                        requests.append(route.request.post_data_json)
                        if mode["value"] == "network":
                            await route.abort("failed")
                        elif mode["value"] == "http":
                            await route.fulfill(status=503, body="unavailable")
                        elif mode["value"] == "invalid":
                            await route.fulfill(json={"reply": 123})
                        elif mode["value"] == "delayed":
                            await asyncio.sleep(.5)
                            await route.fulfill(json={"reply": "پاسخ آزمایشی تازه"})
                        else:
                            await route.fulfill(json={"reply": "این پاسخ فقط برای آزمون رابط است.\nمتن فارسی با API و English خوانا می‌ماند.\n<script>alert('xss')</script>"})

                    await page.route("**/api/chat", api)
                    await page.goto(host_url)
                    await expect(page.locator("#launcho-widget")).to_have_count(1)
                    assert await page.locator("iframe").count() == 0, "Iframe must load lazily"
                    await page.evaluate("LaunchoWidget.setTheme('" + theme + "')")
                    launcher = page.locator("#launcho-widget button")
                    await launcher.click()
                    frame = page.locator("#launcho-widget iframe")
                    await expect(frame).to_have_attribute("referrerpolicy", "no-referrer")
                    assert (await frame.get_attribute("src")).startswith(base + "/widget/widget.html#")
                    sandbox = (await frame.get_attribute("sandbox")).split()
                    assert set(sandbox) == {
                        "allow-scripts", "allow-same-origin", "allow-forms",
                        "allow-popups", "allow-top-navigation-by-user-activation",
                    }
                    chat = page.frame_locator("#launcho-widget iframe")
                    await expect(chat.locator("html")).to_have_attribute("data-theme", theme)
                    await expect(chat.locator("#message")).to_be_focused()
                    await chat.locator("body").evaluate("() => document.fonts.ready")
                    # Match the approved launcher gradient and keep starter actions
                    # outside the scrolling message body in both themes/viewports.
                    gradient = await launcher.evaluate("el => getComputedStyle(el).backgroundImage")
                    assert gradient == "linear-gradient(135deg, rgb(23, 75, 255) 0%, rgb(8, 125, 223) 55%, rgb(0, 158, 174) 100%)", gradient
                    assert await chat.locator("#scroll-area .starters").count() == 0
                    starter_box = await chat.locator(".starters").bounding_box()
                    input_box = await chat.locator(".input-row").bounding_box()
                    for action in await chat.locator(".starters button").all():
                        box = await action.bounding_box()
                        assert box["y"] >= starter_box["y"]
                        assert box["y"] + box["height"] <= input_box["y"]
                        assert 0 <= box["x"] and box["x"] + box["width"] <= page.viewport_size["width"]
                    await chat.locator("#messages").evaluate("""el => {
                        const fixture = document.createElement('p');
                        fixture.id = 'scroll-fixture'; fixture.textContent = 'آزمون پیمایش '.repeat(300);
                        el.append(fixture);
                    }""")
                    await chat.locator("#scroll-area").evaluate("el => {el.scrollTop = el.scrollHeight;}")
                    after_scroll = await chat.locator(".starters").bounding_box()
                    assert abs(after_scroll["y"] - starter_box["y"]) < 1
                    await chat.locator("#scroll-fixture").evaluate("el => el.remove()")
                    await chat.locator("#scroll-area").evaluate("el => {el.scrollTop = 0;}")
                    await page.screenshot(path=str(OUTPUT / f"{'mobile' if mobile else 'desktop'}-{theme}-welcome.png"), animations="disabled")
                    await chat.get_by_role("button", name="ساخت فروشگاه", exact=False).click()
                    await expect(chat.locator(".assistant")).to_have_count(1)
                    assert requests[0] == {"message": "برای ساخت فروشگاه با لانچو از کجا شروع کنم؟"}
                    assert await chat.locator("#messages script").count() == 0
                    await expect(chat.locator(".assistant")).to_contain_text("<script>")
                    await page.screenshot(path=str(OUTPUT / f"{'mobile' if mobile else 'desktop'}-{theme}-chat.png"), animations="disabled")

                    # Close with keyboard, restore focus and preserve the iframe session.
                    await chat.locator("#message").focus()
                    await page.keyboard.press("Escape")
                    await expect(launcher).to_have_attribute("aria-expanded", "false")
                    await expect(launcher).to_be_focused()
                    await launcher.click()
                    await expect(chat.locator(".bubble")).to_have_count(2)
                    await page.add_script_tag(url=base + "/widget/loader.js")
                    await expect(page.locator("#launcho-widget")).to_have_count(1)

                    # Forged origins, sources, channels and malformed config must be ignored.
                    await page.evaluate("""() => {
                        const frame=document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe');
                        const channel=new URLSearchParams(new URL(frame.src).hash.slice(1)).get('channel');
                        window.dispatchEvent(new MessageEvent('message',{origin:new URL(frame.src).origin,source:window,data:{scope:'launcho',channel,type:'close'}}));
                        frame.contentWindow.postMessage({scope:'launcho',channel:'wrong',type:'configure',theme:'auto',apiUrl:'https://evil.invalid',open:true},new URL(frame.src).origin);
                    }""")
                    await chat.locator("body").evaluate("""() => {
                        const p=new URLSearchParams(location.hash.slice(1));
                        const data={scope:'launcho',channel:p.get('channel'),type:'configure',theme:'auto',apiUrl:'https://evil.invalid',open:true};
                        window.dispatchEvent(new MessageEvent('message',{origin:'https://evil.invalid',source:parent,data}));
                        window.dispatchEvent(new MessageEvent('message',{origin:p.get('parentOrigin'),source:window,data}));
                        parent.postMessage({scope:'launcho',channel:'wrong',type:'close'},p.get('parentOrigin'));
                    }""")
                    await expect(launcher).to_have_attribute("aria-expanded", "true")
                    await expect(chat.locator("html")).to_have_attribute("data-theme", theme)

                    # Length, blank input, composition, Shift+Enter and request lock.
                    entry = chat.locator("#message")
                    for value in ["   ", "a" * 5001]:
                        await entry.fill(value)
                        await expect(chat.locator("#send")).to_be_disabled()
                    await entry.fill("متن")
                    await entry.press("Shift+Enter")
                    assert "\n" in await entry.input_value()
                    count = len(requests)
                    await entry.dispatch_event("compositionstart")
                    await entry.press("Enter")
                    assert len(requests) == count
                    await entry.dispatch_event("compositionend")
                    mode["value"] = "delayed"
                    await entry.fill("پیام انتظار")
                    await entry.press("Enter")
                    await expect(chat.locator("#waiting")).to_be_visible()
                    await expect(chat.locator("#send")).to_be_disabled()
                    await entry.press("Enter")
                    await expect(chat.locator(".assistant")).to_have_count(2)
                    assert len(requests) == count + 1

                    for failure in ["network", "http", "invalid"]:
                        mode["value"] = failure
                        await entry.fill("تست خطا " + failure)
                        await entry.press("Enter")
                        await expect(chat.locator("#retry")).to_be_visible()
                        users = await chat.locator(".user").count()
                        mode["value"] = "success"
                        await chat.locator("#retry").click()
                        await expect(chat.locator("#error")).to_be_hidden()
                        await expect(chat.locator("#waiting")).to_be_hidden()
                        assert await chat.locator(".user").count() == users

                    # Long mixed content must wrap. A reader scrolled up stays there.
                    await chat.locator("#messages").evaluate("""el => { for(let i=0;i<20;i++){const p=document.createElement('p');p.className='bubble assistant';p.textContent='پیام بلند '+('https://example.invalid/very-long-link'.repeat(8));el.append(p);} }""")
                    mode["value"] = "delayed"
                    await entry.fill("آزمون اسکرول")
                    await entry.press("Enter")
                    await chat.locator("#scroll-area").evaluate("el => {el.scrollTop=0;el.dispatchEvent(new Event('scroll'));}")
                    await expect(chat.locator("#waiting")).to_be_hidden()
                    assert await chat.locator("#scroll-area").evaluate("el => el.scrollTop") < 10
                    assert await chat.locator("body").evaluate("() => document.documentElement.scrollWidth <= innerWidth")
                    assert await chat.locator("#scroll-area").evaluate("el => el.scrollWidth <= el.clientWidth")

                    # Explicit host themes, system auto theme, configurable position.
                    await page.evaluate("LaunchoWidget.configure({theme:'auto', position:'left'})")
                    await page.emulate_media(color_scheme="dark")
                    await expect(chat.locator("html")).to_have_attribute("data-theme", "dark")
                    await page.emulate_media(color_scheme="light")
                    await expect(chat.locator("html")).to_have_attribute("data-theme", "light")
                    assert (await launcher.bounding_box())["x"] < 30
                    if mobile:
                        # Approximate reduced usable viewport; physical IME still needs a device.
                        await page.set_viewport_size({"width": 390, "height": 430})
                        box = await chat.locator("#send").bounding_box()
                        assert box["y"] >= 0 and box["y"] + box["height"] <= 430
                    await chat.locator("#close").click()
                    await expect(launcher).to_have_attribute("aria-expanded", "false")
                    if mobile:
                        await page.locator("#host-action").click()
                        await page.locator("#host-action").focus()
                        await page.keyboard.press("Tab")
                        await expect(launcher).to_be_focused()
                    assert not errors, errors
                    if not mobile and theme == "light":
                        timeout_result = await page.evaluate("""async base => {
                            const {sendMessage} = await import(base+'/widget/api.js');
                            const realFetch=window.fetch, realTimer=window.setTimeout;
                            let timeout;
                            window.setTimeout=(callback, ms) => {timeout=ms;return realTimer(callback,0);};
                            window.fetch=(_url, options) => new Promise((_resolve,reject) => {
                                options.signal.addEventListener('abort',()=>reject(new DOMException('timeout','AbortError')));
                            });
                            try {await sendMessage('/api/chat','timeout test');return {failed:false};}
                            catch(error){return {failed:true,timeout,message:error.message};}
                            finally {window.fetch=realFetch;window.setTimeout=realTimer;}
                        }""", base)
                        assert timeout_result["failed"] and timeout_result["timeout"] == 45000
                        assert "دریافت پاسخ طول کشید" in timeout_result["message"]
                    results.append({"viewport": "mobile" if mobile else "desktop", "theme": theme, "cross_origin": mobile, "requests": len(requests), "status": "passed"})
                    if not mobile:
                        # A short, explicitly mocked exchange for comparing the supplied design.
                        preview = await context.new_page()
                        await preview.route("**/api/chat", lambda route: route.fulfill(json={"reply": "از کجا شروع کنیم؟"}))
                        await preview.goto(host_url)
                        await preview.evaluate("LaunchoWidget.setTheme('" + theme + "')")
                        await preview.locator("#launcho-widget button").click()
                        preview_chat = preview.frame_locator("#launcho-widget iframe")
                        await expect(preview_chat.locator("#message")).to_be_focused()
                        await preview_chat.locator("#message").fill("می‌خوام فروشگاهم رو بسازم")
                        await preview_chat.locator("#message").press("Enter")
                        await expect(preview_chat.locator(".assistant")).to_have_text("دستیار لانچو: از کجا شروع کنیم؟")
                        await expect(preview_chat.locator(".robot")).to_be_in_viewport()
                        await expect(preview_chat.locator(".starters")).to_be_visible()
                        await preview.locator("#launcho-widget .panel").screenshot(path=str(OUTPUT / f"reference-{theme}.png"), animations="disabled")
                    await context.close()
            results.extend(await run_workflow_checks(browser, base))
            await browser.close()
        (OUTPUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        server.terminate()
        server.wait(timeout=10)
        host.shutdown()
        host.server_close()
        log.close()


if __name__ == "__main__":
    asyncio.run(main())
