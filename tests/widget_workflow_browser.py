"""Browser checks for the demo-only, restricted store workflow; no live services."""
from pathlib import Path
from playwright.async_api import expect

OUTPUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'widget'


def untrusted_draft_urls(base):
    from urllib.parse import urlsplit
    origin = urlsplit(base)
    allowed = base + '/widget/draft-preview.html'
    return [
        'https://fake-site.example/login',
        'http://fake-site.example/login',
        'https://fake-site.example/widget/draft-preview.html',
        f'{origin.scheme}://{origin.hostname}.fake-site.example/widget/draft-preview.html',
        f'{origin.scheme}://{origin.netloc}@fake-site.example/widget/draft-preview.html',
        f'{origin.scheme}://user:pass@{origin.netloc}/widget/draft-preview.html',
        f'{origin.scheme}://{origin.hostname}:{int(origin.port or 80) + 1}/widget/draft-preview.html',
        ('https' if origin.scheme == 'http' else 'http') + '://' + origin.netloc + '/widget/draft-preview.html',
        base + '/login',
        base + '/widget/draft-preview.html.evil',
        base + '/widget/draft-preview.html/login',
        allowed + '?next=https://fake-site.example/login',
        allowed + '#https://fake-site.example/login',
        base + '/widget/%64raft-preview.html',
        base + '/widget/../widget/draft-preview.html',
        '//' + origin.netloc + '/widget/draft-preview.html',
        allowed + '\n',
        ' ' + allowed,
    ]


async def run_workflow_checks(browser, base):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    for width in [1280, 390, 320]:
        context = await browser.new_context(viewport={'width':width,'height':844},
            is_mobile=width < 480, has_touch=width < 480, reduced_motion='reduce')
        try:
            page = await context.new_page()
            errors, external, api_calls = [], [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            context.on('request', lambda req: external.append(req.url) if not req.url.startswith(base) else None)
            await page.route('**/api/**', lambda route: (api_calls.append(route.request.url), route.abort())[1])
            await page.goto(base + '/widget/demo.html')
            launcher = page.locator('#launcho-widget .launcher')
            await launcher.click()
            chat = page.frame_locator('#launcho-widget iframe')
            await expect(chat.locator('.demo-badge')).to_contain_text('حالت نمایشی')
            await page.screenshot(path=str(OUTPUT/f'flow-{width}-start.png'))
            await chat.locator('.primary-starter').click()
            entry = chat.locator('#flow-value')
            await expect(entry).to_be_visible()
            await entry.fill('فروشگاه من')
            await page.screenshot(path=str(OUTPUT/f'flow-{width}-collection.png'))
            await chat.locator('[data-action=next]').click()
            await expect(chat.locator('#workflow h2')).to_have_text('دسته‌بندی را مشخص کن')
            await entry.select_option('سایر')
            await chat.locator('[data-action=next]').click()
            await expect(chat.locator('#workflow h2')).to_have_text('دامنهٔ پیشنهادی را مشخص کن')
            await entry.fill('Sara Shop')
            await chat.locator('[data-action=next]').click()
            await expect(chat.locator('#workflow h2')).to_have_text('قالب فروشگاهت را انتخاب کن')
            await chat.locator('[data-action="style:catalog"]').click()
            await expect(chat.locator('#workflow')).to_contain_text('فیلتر رنگ و سایز')
            await page.screenshot(path=str(OUTPUT/f'flow-{width}-template.png'))
            assert not await page.evaluate("LaunchoWidget.selectTemplate({id:'x',name:'x',image:'javascript:alert(1)'})")
            await chat.locator('[data-action=browseTemplates]').click()
            await expect(launcher).to_have_attribute('aria-expanded','false')
            await page.locator('#choose-template').click()
            await expect(chat.locator('#workflow h2')).to_have_text('دوره اشتراک را مشخص کن')
            await chat.locator('[data-action=costHelp]').click()
            await expect(chat.locator('#workflow')).to_contain_text('دورهٔ سه‌ماهه')
            await expect(entry).to_have_value('')
            await entry.select_option('6')
            await entry.press('Escape')
            await launcher.click()
            await expect(entry).to_have_value('6')
            await chat.locator('[data-action=next]').click()
            await expect(chat.locator('#workflow h2')).to_have_text('مرور اطلاعات')
            await expect(chat.locator('#workflow dt')).to_have_text(['نام کسب‌وکار','دسته‌بندی','دامنهٔ پیشنهادی','قالب','دوره اشتراک'])
            await expect(chat.locator('#workflow dd')).to_have_text(['فروشگاه من','سایر','sarashop.ir','الماس','شش‌ماهه'])
            await expect(chat.locator('#workflow a')).to_have_count(0)
            await page.screenshot(path=str(OUTPUT/f'flow-{width}-review.png'))

            # Every editable field returns directly to review; the plan stays put.
            for field, value in [('businessName','نام اصلاح‌شده'),('category','زیبایی'),('subscription','12'),('template',None)]:
                await chat.locator('[data-action=edit]').click()
                await expect(chat.locator('#workflow button')).to_have_count(5)
                await chat.locator(f'[data-action="edit:{field}"]').click()
                if field == 'template':
                    await chat.locator('[data-action=browseTemplates]').click()
                    await page.locator('#choose-template').click()
                else:
                    if field == 'businessName':
                        await entry.fill(value)
                    else:
                        await entry.select_option(value)
                    await chat.locator('[data-action=next]').click()
                await expect(chat.locator('#workflow h2')).to_have_text('مرور اطلاعات')
            await expect(chat.locator('#workflow dd')).to_have_text(['نام اصلاح‌شده','زیبایی','sarashop.ir','الماس','سالانه'])
            await chat.locator('[data-action=createDraft]').click()
            await expect(chat.locator('[data-action=createDraft]')).to_be_disabled()
            await expect(chat.locator('#workflow h2')).to_have_text('پیش‌نویس نمایشی آماده شد.')
            await expect(chat.locator('#workflow button')).to_have_count(0)
            await expect(chat.locator('input[type=tel]')).to_have_count(0)
            link = chat.get_by_role('link', name='مشاهده نمونهٔ پیش‌نویس (نمایشی)')
            await expect(link).to_have_attribute('href',base + '/widget/draft-preview.html')
            await expect(link).to_have_attribute('rel','noopener noreferrer')
            await link.scroll_into_view_if_needed()
            await page.screenshot(path=str(OUTPUT/f'flow-{width}-draft.png'))
            async with page.expect_popup() as popup_info:
                await link.click()
            popup = await popup_info.value
            await popup.wait_for_load_state()
            await expect(popup.get_by_text('صرفاً نمایشی — فروشگاه واقعی نیست')).to_be_visible()
            await expect(popup.locator('h1')).to_have_text('نمونهٔ پیش‌نویس فروشگاه')
            assert await popup.evaluate('window.opener === null')
            assert await popup.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert await popup.locator('img').evaluate('el => el.complete && el.naturalWidth > 0')
            await popup.screenshot(path=str(OUTPUT/f'flow-{width}-preview.png'), full_page=True)
            await popup.close()
            await chat.locator('#close').click()
            await launcher.click()
            await expect(link).to_be_visible()
            assert not api_calls and not external and not errors, (api_calls,external,errors)
            assert await page.evaluate('localStorage.length + sessionStorage.length') == 0
            assert await chat.locator('body').evaluate('localStorage.length + sessionStorage.length') == 0
            assert await chat.locator('body').evaluate('document.documentElement.scrollWidth <= innerWidth')
            if width < 480:
                await page.set_viewport_size({'width':width,'height':430})
                await expect(chat.locator('#close')).to_be_in_viewport(ratio=1)
                await link.scroll_into_view_if_needed()
                await expect(link).to_be_in_viewport(ratio=1)
                await page.screenshot(path=str(OUTPUT/f'flow-{width}-short-viewport.png'))
            results.append({'workflow_width':width,'status':'passed','live_requests':0,
                'sequence':['businessName','category','subscription','template','review','confirm','draft-link'],
                'edit_all_fields':'passed','preview':'passed','close_reopen':'passed'})
        finally:
            await context.close()

    context = await browser.new_context(viewport={'width':1280,'height':900})
    try:
        page = await context.new_page()
        calls, modules = [], []
        page.on('request', lambda req: modules.append(req.url))
        attempt = 0
        starts = 0
        untrusted = untrusted_draft_urls(base)

        async def workflow(route):
            nonlocal attempt, starts
            payload = route.request.post_data_json
            calls.append(payload)
            common = {'sessionId':'server-test','revision':len(calls),'actions':[]}
            if payload['action'] == 'start':
                starts += 1
                if starts < 3:
                    await route.fulfill(json={**common,'kind':'field','field':'domain' if starts == 1 else 'mobile','title':'legacy'})
                else:
                    await route.fulfill(json={**common,'kind':'review','title':'مرور پاسخ سرور','actions':[{'id':'createDraft','label':'تأیید'}]})
            elif payload['action'] == 'createDraft':
                attempt += 1
                if attempt == 1:
                    await route.abort('failed')
                elif attempt <= 3:
                    await route.fulfill(json={**common,'kind':'draft','title':'پیش‌نویس آزمایشی',
                        'confirmed':attempt > 2,'draftId':'test-draft',
                        'draftUrl':'javascript:alert(1)' if attempt == 3 else base+'/widget/draft-preview.html'})
                else:
                    index = attempt - 4
                    await route.fulfill(json={**common,'kind':'draft','title':'پیش‌نویس آزمایشی',
                        'confirmed':True,'draftId':'test-draft',
                        'draftUrl':untrusted[index] if index < len(untrusted) else base+'/widget/draft-preview.html'})
            else:
                raise AssertionError(payload)

        await page.route('**/test-workflow',workflow)
        await page.goto(base + '/widget/widget.html')
        await page.evaluate("""url => {
            const script=document.createElement('script'); script.src=url+'/widget/loader.js';
            script.dataset.workflowUrl=url+'/test-workflow';script.dataset.autoOpen='false';document.body.append(script);
        }""",base)
        await page.locator('#launcho-widget .launcher').click()
        chat = page.frame_locator('#launcho-widget iframe')
        await chat.locator('.primary-starter').click()
        for _ in range(2):
            await expect(chat.locator('.flow-error')).to_contain_text('پاسخ معتبر نیست')
            await expect(chat.locator('#flow-value')).to_have_count(0)
            await chat.locator('.flow-error button').click()
        await chat.locator('[data-action=createDraft]').click()
        for _ in range(3 + len(untrusted)):
            await expect(chat.locator('.flow-error')).to_contain_text('پیش‌نویس ساخته نشد')
            await expect(chat.locator('#workflow a')).to_have_count(0)
            await chat.locator('.flow-error button').click()
        await expect(chat.locator('#workflow h2')).to_have_text('پیش‌نویس آزمایشی')
        await expect(chat.locator('#workflow a')).to_have_count(1)
        creates = [c for c in calls if c['action']=='createDraft']
        assert len(creates)==4 + len(untrusted) and len({c['idempotencyKey'] for c in creates})==1
        assert not any('workflow-demo.js' in m for m in modules)
        schema = await page.evaluate("""async ({base, untrusted}) => {
            const {validateView} = await import(base+'/widget/workflow-api.js');
            const common={sessionId:'schema-test',revision:1,title:'test',kind:'review',actions:[]};
            const draft={...common,kind:'draft',draftId:'test',confirmed:true,draftUrl:base+'/widget/draft-preview.html'};
            const invalid=[
                ...['mobile','setupPayment','domain'].map(field=>({...common,kind:'field',field})),
                ...['payment','result'].map(kind=>({...common,kind})),
                ...['pay','continuePayment','editPayment','refreshQuote','checkPayment','fixtureSuccess',
                    'fixtureFailed','fixtureUnknown','edit:mobile','edit:setupPayment','checkDomain','edit:domain','changeTemplate']
                    .map(id=>({...common,actions:[{id,label:'legacy'}]})),
                ...['mobile','setupPayment','domain','domainStatus','quote','checkoutUrl','transactionId','paymentStatus','verified']
                    .map(key=>({...common,[key]:null})),
                ...['javascript:alert(1)','data:text/html,test','https://user:pass@example.invalid','/relative',undefined]
                    .map(draftUrl=>({...draft,draftUrl})),
                ...untrusted.map(draftUrl=>({...draft,draftUrl})),
                {...common,draftUrl:draft.draftUrl}, {...draft,confirmed:false}
            ];
            let rejected=0;
            for(const value of invalid) {try {validateView(value);} catch {rejected++;}}
            validateView(draft);
            validateView({...common,actions:[{id:'createDraft',label:'confirm'}]});
            return {rejected,total:invalid.length};
        }""",{'base':base, 'untrusted':untrusted})
        assert schema['rejected'] == schema['total'] == 34 + len(untrusted), schema
        plans = await page.evaluate("""async base => {
            const {createDemoWorkflow} = await import(base+'/widget/workflow-demo.js');
            const {validateView} = await import(base+'/widget/workflow-api.js');
            return Promise.all(['3','6','12'].map(async plan => {
                const api=createDemoWorkflow();
                const send=async (action,data={})=>validateView(await api.request({action,data}), {demo:true});
                await send('start');
                for(const payload of [{action:'createDraft'}, {action:'checkDomain',data:{value:'example.ir'}},
                    {action:'next',data:{field:'mobile',value:'legacy'}}]) {
                    let rejected=false;
                    try {await api.request(payload);} catch {rejected=true;}
                    if(!rejected) throw new Error('Out-of-sequence action accepted');
                }
                await send('next',{value:'name'}); await send('next',{value:'سایر'});
                const template=await send('next',{value:'Sara Shop'});
                if(template.kind!=='template') throw new Error('Wrong order');
                const subscription=await send('selectTemplate',{template:{id:'almas',name:'Almas',image:base+'/widget/assets/template-almas.webp'}});
                if(subscription.field!=='subscription') throw new Error('Wrong order');
                let rejected=false;
                try {await send('next',{value:'invalid-plan'});} catch {rejected=true;}
                if(!rejected) throw new Error('Invalid plan accepted');
                const review=await send('next',{value:plan});
                if(review.kind!=='review' || 'quote' in review) throw new Error('Unexpected review');
                const draft=await send('createDraft');
                if(draft.kind!=='draft' || draft.actions.length || !draft.draftUrl) throw new Error('Unexpected draft');
                return plan;
            }));
        }""",base)
        assert plans == ['3','6','12'], plans
        results.append({'production_adapter':'passed','idempotency':'stable','invalid_draft':'rejected',
            'legacy_schema':schema,'demo_plans':plans,'untrusted_draft_destinations_rejected':len(untrusted)})
    finally:
        await context.close()
    return results


if __name__ == '__main__':
    import argparse
    import asyncio
    import json
    from playwright.async_api import async_playwright

    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    OUTPUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'widget-stage6'

    async def main():
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome')
            try:
                report = await run_workflow_checks(browser, args.base_url)
                (OUTPUT/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps(report, indent=2))
            finally:
                await browser.close()

    asyncio.run(main())
