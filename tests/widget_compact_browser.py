"""Approved workspace regressions; stdlib host + intercepted APIs, no live backend.

Run: python tests/widget_compact_browser.py
Requires Playwright and installed Chrome. Evidence: artifacts/widget-compact/.
Use --reference to also photograph the live homepage and inject the local widget
there for comparisons at the exact same viewport, DPR and browser zoom.
"""
import argparse
import asyncio
import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/widget-compact"
PUBLIC = "https://widget-preview.example"
CATALOG = json.loads((ROOT / "content/launcho-public.json").read_text(encoding="utf-8"))
INTRO = CATALOG["overview"]


class Host(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/":
            data = '''<!doctype html><html lang="fa" dir="rtl"><head>
            <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Compact widget test host</title><style>body{margin:0;min-height:100vh;
            background:radial-gradient(at 80% 20%,#cbd9fc,transparent 65%),
            radial-gradient(at 40% 80%,#c4f4ef,transparent 70%),#f5f8fa}
            #host-action{margin:24px;padding:14px}</style>
            <script defer src="/widget/loader.js" data-theme="light" data-auto-open="false"></script>
            </head><body><button id="host-action">Host action</button></body></html>'''.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def translate_path(self, path):
        if path.startswith("/widget/"):
            path = path[len("/widget"):]
        return super().translate_path(path)


class MockApi:
    def __init__(self):
        self.calls = []
        self.revision = 0
        self.delay = .12
        self.mode = "success"

    async def handle(self, route):
        request = route.request
        path = request.url.split("/api/", 1)[1]
        body = request.post_data_json if request.post_data else None
        self.calls.append({"path": path, "method": request.method, "body": body})
        if path == "sessions":
            await route.fulfill(json={"sessionId": "mock-session", "sessionToken": "mock-owner", "revision": 0, "adapterMode": "test"})
        elif path == "chat":
            assert request.headers.get("x-session-token") == "mock-owner"
            await asyncio.sleep(self.delay)
            if self.mode == "failure":
                await route.fulfill(status=503, json={"detail": "test outage"})
                return
            self.revision += 1
            await route.fulfill(json={"sessionId": "mock-session", "revision": self.revision,
                "reply": INTRO if self.mode != "long" else (INTRO + "\n") * 25,
                # Deliberately hostile metadata must never authorize a mutation.
                "nextAction": "confirm" if self.mode == "hostile" else None,
                "confirmed": True, "confirmationToken": "untrusted-model-token"})
        else:
            await route.fulfill(status=500, json={"detail": "Unexpected operation in quick-question test"})
            raise AssertionError(f"Unexpected API operation: {path}")

    @property
    def turns(self):
        return [call for call in self.calls if call["path"] == "chat"]


async def geometry(chat):
    return await chat.locator("body").evaluate("""() => {
      const rect = selector => { const r=document.querySelector(selector).getBoundingClientRect();
        return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right}; };
      return {width:innerWidth,height:innerHeight,bodyWidth:document.body.scrollWidth,
        scroll:rect('#scroll-area'),composer:rect('.composer'),input:rect('.input-wrap'),
        chips:[...document.querySelectorAll('[data-question]')].map(el=>{
          const r=el.getBoundingClientRect();return {label:el.textContent,x:r.x,y:r.y,right:r.right,bottom:r.bottom};
        }),sidebar:getComputedStyle(document.querySelector('.service-sidebar')).display};
    }""")


async def assert_layout(page, chat, desktop=False):
    g = await geometry(chat)
    assert g["bodyWidth"] <= g["width"], g
    assert g["scroll"]["height"] > 24, g
    assert g["scroll"]["bottom"] <= g["composer"]["y"] + 1, g
    assert g["input"]["bottom"] <= g["height"] + 1, g
    assert g["input"]["right"] <= g["width"], g
    assert len(g["chips"]) == 7
    for chip in g["chips"]:
        assert 0 <= chip["x"] and chip["right"] <= g["width"], chip
        assert g["composer"]["y"] <= chip["y"] < chip["bottom"] <= g["input"]["y"], chip
    assert (g["sidebar"] != "none") == desktop, g
    assert await chat.locator("#minimize-workspace,#expand-workspace").count() == 0
    assert await page.locator("#launcho-widget .resize").count() == 0
    return g


async def open_widget(page):
    await page.evaluate("LaunchoWidget.open()")
    chat = page.frame_locator("#launcho-widget iframe")
    await expect(chat.locator('[data-question]').first).to_be_enabled()
    await chat.locator("body").evaluate("() => document.fonts.ready")
    await chat.locator("#message").blur()
    return chat


async def reference_comparisons(browser, report):
    for name, width, height in [("desktop", 1440, 900), ("mobile", 390, 844)]:
        context = await browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        mock = MockApi()
        # Keep the host's analytics separate from the widget's intercepted API.
        await context.route("https://launcho.ir/api/**", lambda route: route.fulfill(status=204))
        await context.route(PUBLIC + "/api/**", mock.handle)

        async def local_asset(route):
            relative = route.request.url.split("/widget/", 1)[1].split("?", 1)[0].split("#", 1)[0]
            target = (ROOT / "frontend" / relative).resolve()
            assert target.is_relative_to(ROOT / "frontend")
            import mimetypes
            await route.fulfill(body=target.read_bytes(), content_type=mimetypes.guess_type(str(target))[0] or "application/octet-stream",
                                headers={"Access-Control-Allow-Origin": "*"})

        await context.route(PUBLIC + "/widget/**", local_asset)
        page = await context.new_page()
        try:
            await page.goto("https://launcho.ir", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(4000)
            await page.screenshot(path=str(OUT / f"reference-{name}.png"))
            existing = await page.evaluate("!!window.LaunchoWidget")
            if existing:
                # The preview is a local replacement for photography only.
                await page.evaluate("document.querySelector('#launcho-widget')?.remove(); delete window.LaunchoWidget")
            await page.add_script_tag(url=PUBLIC + "/widget/loader.js")
            chat = await open_widget(page)
            await chat.get_by_role("button", name="معرفی لانچو", exact=True).click()
            await expect(chat.locator(".role-assistant .bubble")).to_have_count(1)
            await chat.locator("#message").blur()
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(250)
            await page.screenshot(path=str(OUT / f"implementation-{name}.png"))
            await page.locator("#launcho-widget iframe").screenshot(path=str(OUT / f"widget-{name}.png"))
            report.append({"reference": name, "viewport": [width, height], "DPR": 1, "zoom": 1,
                           "browser": browser.version, "source": "https://launcho.ir",
                           "api": "intercepted mock", "status": "passed"})
        except Exception as error:
            report.append({"reference": name, "status": "unavailable", "reason": str(error)})
        finally:
            await context.close()


async def comparison_images(browser):
    """Compose photographed browser outputs, keeping originals at native size."""
    for name, width in [("desktop",1440),("mobile",828)]:
        paths = [OUT / f"reference-{name}.png", OUT / f"implementation-{name}.png"]
        if not all(path.exists() for path in paths):
            continue
        images = [base64.b64encode(path.read_bytes()).decode() for path in paths]
        page = await browser.new_page(viewport={"width":width,"height":600},device_scale_factor=1)
        await page.set_content('''<html><meta charset="utf-8"><style>
          *{box-sizing:border-box}body{margin:0;padding:16px;background:#f2f5fb;color:#14244b;font:14px Tahoma}
          h1{font-size:18px;text-align:center;margin:4px 0 18px}main{display:grid;grid-template-columns:1fr 1fr;gap:16px}
          section{min-width:0;background:white;border:1px solid #d5d9eb;border-radius:12px;overflow:hidden}
          h2{font-size:14px;text-align:center;margin:0;padding:14px}img{display:block;width:100%;height:auto}
          </style><h1 dir="rtl">مرجع سایت و اجرای محلی با API ساختگی</h1><main>'''
          + ''.join(f'<section><h2>{label}</h2><img src="data:image/png;base64,{image}"></section>'
                    for label,image in zip(["launcho.ir — reference", "Local widget on reference page — mock API"], images))
          + '</main></html>')
        await page.locator("img").evaluate_all("els=>Promise.all(els.map(el=>el.decode()))")
        await page.screenshot(path=str(OUT / f"comparison-{name}.png"),full_page=True)
        await page.close()


async def main(reference=False):
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Host, directory=str(ROOT / "frontend")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    results = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome")
            for name, width, height, desktop in [
                ("desktop",1440,900,True), ("desktop-small",1280,720,True),
                ("desktop-wide",1920,1080,True), ("tablet",768,1024,True),
                ("mobile",390,844,False), ("mobile-small",320,568,False),
                ("keyboard-height",390,430,False), ("landscape",844,390,False),
            ]:
                context = await browser.new_context(viewport={"width":width,"height":height},device_scale_factor=1)
                mock = MockApi()
                await context.route("**/api/**", mock.handle)
                page = await context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                await page.goto(base)
                assert await page.locator("iframe").count() == 0, "lazy loading preserved"
                chat = await open_widget(page)
                g = await assert_layout(page, chat, desktop)
                panel = await page.locator("#launcho-widget .panel").bounding_box()
                if desktop:
                    assert panel["width"] == 580 and panel["height"] == min(580,height-48), panel
                await chat.get_by_role("button",name="معرفی لانچو",exact=True).click()
                await expect(chat.locator(".role-assistant .bubble")).to_have_count(1)
                await page.mouse.move(0,0)
                await page.screenshot(path=str(OUT / f"{name}.png"))
                await assert_layout(page,chat,desktop)
                # Long content scrolls internally; footer and chip geometry stay fixed.
                before = await geometry(chat)
                mock.mode = "long"
                await page.wait_for_timeout(700)
                await chat.get_by_role("button",name="امکانات",exact=True).click()
                await expect(chat.locator(".role-assistant .bubble")).to_have_count(2)
                await chat.locator("#scroll-area").evaluate("el => el.scrollTop=0")
                after = await geometry(chat)
                assert before["input"] == after["input"] and before["chips"] == after["chips"]
                assert await chat.locator("#scroll-area").evaluate("el=>el.scrollHeight>el.clientHeight")
                await assert_layout(page,chat,desktop)
                # Mobile service selection is a modal with restored focus and history.
                if not desktop:
                    await chat.locator("#change-service").click()
                    await expect(chat.locator("#service-sheet")).to_be_visible()
                    await chat.locator('#mobile-services [data-service=human]').click()
                    await expect(chat.locator("#unavailable-service")).to_be_visible()
                    await chat.locator("#change-service").click()
                    await chat.locator('#mobile-services [data-service=assistant]').click()
                    await expect(chat.locator("#change-service")).to_be_focused()
                    await expect(chat.locator(".role-assistant .bubble")).to_have_count(2)
                # Theme switching must retain legibility and layout.
                await page.evaluate("LaunchoWidget.setTheme('dark')")
                await expect(chat.locator("html")).to_have_attribute("data-theme","dark")
                await assert_layout(page,chat,desktop)
                await page.screenshot(path=str(OUT / f"{name}-dark.png"))
                await chat.locator("#close").click()
                await expect(page.locator("#launcho-widget .launcher")).to_be_visible()
                await page.locator("#host-action").click()
                await page.locator("#launcho-widget .launcher").click()
                await expect(chat.locator(".role-assistant .bubble")).to_have_count(2)
                assert not errors, errors
                assert not [c for c in mock.calls if c["path"] not in ("chat","sessions")]
                results.append({"case":name,"viewport":[width,height],"geometry":g,"status":"passed"})
                await context.close()

            # Interaction regression checks use one live iframe and owner session.
            context = await browser.new_context(viewport={"width":1440,"height":900})
            mock = MockApi()
            await context.route("**/api/**", mock.handle)
            page = await context.new_page()
            await page.goto(base)
            chat = await open_widget(page)
            chips = chat.locator("[data-question]")
            for index in range(7):
                mock.mode = "hostile"
                await page.wait_for_timeout(700)
                expected = await chips.nth(index).get_attribute("data-question")
                count = len(mock.turns)
                await chips.nth(index).click()
                await expect(chat.locator("#waiting")).to_be_hidden()
                assert len(mock.turns) == count+1
                assert mock.turns[-1]["body"]["message"] == expected
                assert set(mock.turns[-1]["body"]) == {"message","sessionId","requestId"}
                await expect(chat.locator("#confirm")).to_be_hidden()
            results.append({"case":"seven one-click questions; hostile metadata never confirms","status":"passed"})
            await page.wait_for_timeout(700)
            mock.delay = .7
            count = len(mock.turns)
            await chips.first.evaluate("el=>{for(let i=0;i<15;i++)el.click()}")
            await expect(chat.locator("#waiting")).to_be_hidden()
            assert len(mock.turns) == count+1, "burst must produce one API turn"
            await page.wait_for_timeout(700)
            mock.delay = 0
            count = len(mock.turns)
            await chips.first.click()
            await expect(chat.locator("#waiting")).to_be_hidden()
            await chips.nth(1).click()
            assert len(mock.turns) == count+1, "cross-chip rapid click after instant reply must be ignored"
            await page.wait_for_timeout(700)
            count = len(mock.turns)
            await chips.nth(1).click(click_count=2)
            await page.wait_for_timeout(100)
            assert len(mock.turns) == count+1, "double click must produce only one turn"
            await page.wait_for_timeout(700)
            count = len(mock.turns)
            await chips.first.dispatch_event("click", {"detail":2})
            assert len(mock.turns) == count, "second dblclick event must be ignored"
            results.append({"case":"slow and instant replies; rapid repeat and adjacent-chip clicks","status":"passed"})
            await page.wait_for_timeout(700)
            mock.mode = "failure"
            await chips.first.click()
            await expect(chat.locator("#error")).to_be_visible()
            assert await chips.first.is_disabled()
            count = len(mock.turns)
            request_id = mock.turns[-1]["body"]["requestId"]
            mock.mode = "success"
            await chat.locator("#retry").click()
            await expect(chat.locator("#error")).to_be_hidden()
            assert len(mock.turns) == count+1 and mock.turns[-1]["body"]["requestId"] == request_id
            assert all(call["path"] in ("sessions","chat") for call in mock.calls)
            results.append({"case":"failure locks starters; explicit retry retains request id; zero construction operations","status":"passed"})
            await context.close()
            if reference:
                await reference_comparisons(browser,results)
                await comparison_images(browser)
            await browser.close()
    finally:
        server.shutdown()
        (OUT / "report.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"passed":len([r for r in results if r["status"]=="passed"]),"results":results},ensure_ascii=False))
    if any(result["status"] != "passed" for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference",action="store_true")
    asyncio.run(main(parser.parse_args().reference))
