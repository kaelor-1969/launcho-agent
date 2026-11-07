"""Browser coverage for structured views; called by widget_browser.py. No live services."""
from pathlib import Path
from playwright.async_api import expect

OUTPUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'widget'


async def run_workflow_checks(browser, base):
    results = []
    for width in [1280, 390, 320]:
        context = await browser.new_context(viewport={'width': width, 'height': 844}, reduced_motion='reduce')
        page = await context.new_page()
        errors, external, api_calls = [], [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        page.on('request', lambda request: external.append(request.url) if not request.url.startswith(base) else None)
        await page.route('**/api/chat', lambda route: (api_calls.append(route.request.url), route.abort())[1])
        await page.goto(base + '/widget/demo.html')
        launcher = page.locator('#launcho-widget button')
        await expect(launcher).to_have_accessible_name('دستیار لانچو')
        assert (await launcher.bounding_box())['width'] == 58
        await launcher.click()
        chat = page.frame_locator('#launcho-widget iframe')
        await expect(chat.locator('.demo-badge')).to_be_visible()
        await page.screenshot(path=str(OUTPUT / f'flow-{width}-start.png'))
        await chat.get_by_role('button', name='ساخت فروشگاه', exact=True).click()
        await expect(chat.locator('#flow-value')).to_be_visible()
        await expect(chat.locator('.starters')).to_be_hidden()
        await chat.locator('#flow-value').fill('فروشگاه من')
        await page.screenshot(path=str(OUTPUT / f'flow-{width}-collection.png'))
        await chat.locator('[data-action=next]').click()
        await expect(chat.locator('h2').last).to_have_text('دسته‌بندی را مشخص کن')
        await chat.locator('[data-action=next]').click()
        await expect(chat.locator('[data-action=checkDomain]')).to_be_visible()
        for domain, status in [('taken.ir','غیرقابل انتخاب'), ('error.ir','خطای بررسی'), ('my-shop.ir','آزاد؛ هنوز ثبت یا رزرو نشده')]:
            await chat.locator('#flow-value').fill(domain)
            await chat.locator('[data-action=checkDomain]').click()
            await expect(chat.locator('.flow-status')).to_have_text('در حال بررسی')
            await expect(chat.locator('.flow-card [role=status]')).to_have_text(status)
            if domain == 'error.ir':
                await page.screenshot(path=str(OUTPUT / f'flow-{width}-error.png'))
                await expect(chat.locator('[data-action=next]')).to_have_count(0)
        # Changing a checked domain cannot reuse its availability.
        await chat.locator('#flow-value').fill('other.ir')
        await expect(chat.locator('[data-action=next]')).to_be_disabled()
        await expect(chat.locator('.flow-card [role=status]')).to_have_text('بررسی‌نشده')
        await chat.locator('[data-action=checkDomain]').click()
        await expect(chat.locator('.flow-status')).to_have_count(0)
        await chat.locator('[data-action=next]').click()
        await expect(chat.locator('[data-action=browseTemplates]')).to_be_visible()
        assert not await page.evaluate("LaunchoWidget.selectTemplate({id:'x',name:'x',image:'javascript:alert(1)'})")
        await page.screenshot(path=str(OUTPUT / f'flow-{width}-template.png'))
        await chat.locator('[data-action=browseTemplates]').click()
        await expect(launcher).to_have_attribute('aria-expanded','false')
        await page.locator('#choose-template').click()
        await expect(chat.locator('#flow-value')).to_have_attribute('type','tel')
        await expect(chat.locator('#workflow img')).to_have_attribute('alt','الماس')
        await expect(chat.locator('[data-action=changeTemplate]')).to_be_visible()
        await chat.locator('[data-action=changeTemplate]').click()
        await chat.locator('[data-action=browseTemplates]').click()
        await page.locator('#choose-template').click()
        await expect(chat.locator('#flow-value')).to_have_attribute('type','tel')
        # Closing keeps the current form draft, not just submitted data.
        await chat.locator('#flow-value').fill('۰۹۱۲۳۴۵۶۷۸۹')
        await chat.locator('#flow-value').press('Escape')
        await expect(launcher).to_be_focused()
        await launcher.click()
        await expect(chat.locator('#flow-value')).to_have_value('۰۹۱۲۳۴۵۶۷۸۹')
        await chat.locator('[data-action=next]').click()
        await expect(chat.locator('#flow-value option')).to_have_count(3)
        await chat.locator('#flow-value').select_option('6')
        await chat.locator('[data-action=next]').click()
        await expect(chat.locator('#flow-value option')).to_have_count(2)
        await chat.locator('[data-action=next]').click()
        await expect(chat.locator('[data-action=createDraft]')).to_be_visible()
        await expect(chat.locator('#workflow')).to_contain_text('09123456789')
        await expect(chat.locator('#workflow')).to_contain_text('۷٬۷۵۰٬۰۰۰')
        await page.screenshot(path=str(OUTPUT / f'flow-{width}-review.png'))
        await chat.locator('[data-action=edit]').click()
        await chat.locator('[data-action="edit:businessName"]').click()
        await chat.locator('#flow-value').fill('نام اصلاح‌شده')
        await chat.locator('[data-action=next]').click()
        await expect(chat.locator('#workflow')).to_contain_text('نام اصلاح‌شده')
        await chat.locator('[data-action=createDraft]').click()
        await expect(chat.locator('.flow-status')).to_have_text('در حال ساخت پیش‌نویس…')
        await expect(chat.locator('[data-action=createDraft]')).to_be_disabled()
        await expect(chat.locator('[data-action=continuePayment]')).to_be_visible()
        await chat.locator('[data-action=continuePayment]').click()
        await expect(chat.locator('[data-action=pay]')).to_be_disabled()
        await expect(chat.locator('[data-action=pay]')).to_have_text('پرداخت ۷٬۷۵۰٬۰۰۰ تومان')
        await page.screenshot(path=str(OUTPUT / f'flow-{width}-cost.png'))
        await chat.locator('[data-action=fixtureFailed]').click()
        await expect(chat.locator('#workflow')).to_contain_text('ناموفق')
        await chat.locator('[data-action=continuePayment]').click()
        await chat.locator('[data-action=fixtureUnknown]').click()
        await expect(chat.locator('[data-action=checkPayment]')).to_be_visible()
        await expect(chat.locator('[data-action=pay]')).to_have_count(0)
        await chat.locator('[data-action=checkPayment]').click()
        await expect(chat.locator('#workflow')).to_contain_text('پاسخ آزمایشی: پرداخت تأیید شد')
        assert not api_calls and not external, (api_calls, external)
        assert await page.evaluate('localStorage.length') == 0
        assert await chat.locator('body').evaluate('localStorage.length') == 0
        assert await chat.locator('body').evaluate('document.documentElement.scrollWidth <= innerWidth')
        if width < 480:
            panel = await page.locator('#launcho-widget .panel').bounding_box()
            assert panel['x'] == 12 and panel['width'] == width - 24
            await page.set_viewport_size({'width':width,'height':430})
            await page.screenshot(path=str(OUTPUT / f'flow-{width}-short-viewport.png'))
            await expect(chat.locator('#close')).to_be_in_viewport(ratio=1)
            close = await chat.locator('#close').bounding_box()
            assert close['y'] >= 0 and close['y'] + close['height'] <= 430
        assert not errors, errors
        if width == 1280:
            # Six fixture totals are checked against the supplied specification.
            totals = await page.evaluate("""async base => {
              const {createDemoWorkflow} = await import(base+'/widget/workflow-demo.js');
              const timer=window.setTimeout; window.setTimeout=cb=>timer(cb,0);
              try {
                const totals=[];
                for (const plan of ['3','6','12']) for (const method of ['installments','upfront']) {
                  const api=createDemoWorkflow();
                  const send=(action,data={})=>api.request({action,data});
                  await send('start'); await send('next',{value:'name'}); await send('next',{value:'category'});
                  await send('checkDomain',{value:'example.ir'}); await send('next',{value:'example.ir'});
                  await send('selectTemplate',{template:{id:'almas',name:'Almas',image:base+'/widget/assets/template-almas.webp'}});
                  await send('next',{value:'09123456789'}); await send('next',{value:plan});
                  const view=await send('next',{value:method}); totals.push(view.quote.today);
                }
                return totals;
              } finally {window.setTimeout=timer;}
            }""",base)
            assert totals == [6150000,17400000,7750000,19000000,11750000,23000000], totals
        results.append({'workflow_width':width,'status':'passed','live_requests':0})
        await context.close()

    # Real adapter transport with a mocked server: uncertain creation, stable key,
    # repeated-click lock, invalid responses, and no production demo fallback.
    context = await browser.new_context(viewport={'width':1280,'height':900})
    page = await context.new_page()
    calls, modules = [], []
    page.on('request', lambda req: modules.append(req.url))
    attempt = 0
    async def workflow(route):
        nonlocal attempt
        payload = route.request.post_data_json
        calls.append(payload)
        a = payload['action']
        common = {'sessionId':'server-test','revision':len(calls),'actions':[]}
        if a == 'start':
            await route.fulfill(json={**common,'kind':'review','title':'مرور پاسخ سرور','quote':{'id':'q-test','currency':'TOMAN','today':7750000,'expiresAt':'2099-01-01T00:00:00Z'},'actions':[{'id':'createDraft','label':'تأیید و ساخت پیش‌نویس'}]})
        elif a == 'createDraft':
            attempt += 1
            if attempt == 1:
                await route.abort('failed')
            else:
                await route.fulfill(json={**common,'kind':'draft','title':'پیش‌نویس فروشگاهت آماده شد.','confirmed':True,'draftId':'test-draft','actions':[{'id':'continuePayment','label':'ادامه به پرداخت'}]})
        else:
            # An unverified success must be rejected, retaining existing view.
            await route.fulfill(json={**common,'kind':'result','title':'fake','paymentStatus':'success','verified':False})
    await page.route('**/test-workflow',workflow)
    # Use production installation, not demo.html.
    await page.goto(base + '/widget/widget.html')
    await page.evaluate("""url => {
        const script=document.createElement('script'); script.src=url+'/widget/loader.js';
        script.dataset.workflowUrl=url+'/test-workflow';document.body.append(script);
    }""",base)
    await page.locator('#launcho-widget button').click()
    chat = page.frame_locator('#launcho-widget iframe')
    await chat.locator('.primary-starter').click()
    await chat.locator('[data-action=createDraft]').click()
    await expect(chat.locator('.flow-error')).to_contain_text('پیش‌نویس ساخته نشد')
    await page.screenshot(path=str(OUTPUT/'flow-draft-error.png'))
    await chat.locator('.flow-error button').click()
    await expect(chat.locator('[data-action=continuePayment]')).to_be_visible()
    creates = [c for c in calls if c['action']=='createDraft']
    assert len(creates)==2 and creates[0]['idempotencyKey']==creates[1]['idempotencyKey']
    await chat.locator('[data-action=continuePayment]').click()
    await expect(chat.locator('.flow-error')).to_contain_text('هنوز تأیید نشده')
    assert not any('workflow-demo.js' in m for m in modules)
    await context.close()
    results.append({'production_adapter':'passed','idempotency':'stable','unverified_success':'rejected'})
    return results
