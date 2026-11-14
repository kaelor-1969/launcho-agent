// Run: node tests/widget_signup_browser.cjs
// Main loader + widget, controlled HTTP responses, native Chrome keyboard input.
// No Python, model calls, external requests, or real draft creation.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const root = path.resolve(__dirname, '../frontend');
const output = process.env.WIDGET_ARTIFACT_DIR ? path.resolve(process.env.WIDGET_ARTIFACT_DIR) : path.resolve(__dirname, '../artifacts/widget-signup-stage1');
const fixture = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../content/launcho-mock.json'), 'utf8'));
const sid = 'signup-browser-session', token = 'signup-browser-token';
let revision = 0, preferences = {}, reviewId = 0;
let optionFailure = false, malformedOptions = false, saveFailure = false, reviewFailure = false, unknown = false;
let calls = [], currentReview;
const server = http.createServer(async (req, res) => {
  const json = (data, status = 200) => { res.writeHead(status, {'Content-Type': 'application/json'}); res.end(JSON.stringify(data)); };
  if (req.url.startsWith('/api/')) {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    const body = raw ? JSON.parse(raw) : undefined;
    calls.push({url: req.url, method: req.method, body, token: req.headers['x-session-token']});
    if (req.url === '/api/sessions') return json({sessionId: sid, sessionToken: token, revision, adapterMode: 'local_mock'});
    if (req.url.startsWith('/api/local-signup-options?')) {
      await sleep(60);
      if (optionFailure) return json({detail: {code: 'options_unavailable'}}, 503);
      if (malformedOptions) return json({businessCategories: 'invalid'});
      const kind = new URL(req.url, 'http://localhost').searchParams.get('kind');
      return json({...fixture.signupOptions[kind], periods: fixture.pricing.plans.map(x => x.months), suffixes: fixture.pricing.domains.map(x => x.tld)});
    }
    assert.equal(req.headers['x-session-token'], token);
    if (req.url.endsWith('/preferences')) {
      assert.equal(req.method, 'PATCH');
      assert.equal(body.revision, revision);
      await sleep(150);
      if (saveFailure) return json({detail: {code: 'invalid_preferences'}}, 422);
      preferences = body.preferences;
      revision++;
      return json({sessionId: sid, revision, preferences});
    }
    if (req.url.endsWith('/review')) {
      assert.equal(body.revision, revision);
      if (reviewFailure) return json({detail: {code: 'options_unavailable'}}, 503);
      currentReview = {sessionId: sid, revision, summary: preferences, canConfirm: true,
        reviewId: `review-${++reviewId}`, confirmationToken: `confirmation-${reviewId}`};
      return json(currentReview);
    }
    if (req.url.endsWith('/confirm')) {
      assert.deepEqual(body, {revision, reviewId: currentReview.reviewId, confirmationToken: currentReview.confirmationToken, confirmed: true});
      await sleep(100);
      if (unknown) return json({detail: {code: 'draft_outcome_unknown'}}, 503);
      return json({adapterMode: 'local_mock', status: 'draft', ref: 'sd_signupbrowser', confirmUrl: '/api/local-drafts/sd_signupbrowser/preview'});
    }
    return json({}, 404);
  }
  if (req.url === '/') {
    res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
    return res.end('<!doctype html><html lang="fa" dir="rtl"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Widget test host</title><body style="margin:0;background:#eef5f7"><script defer src="/widget/loader.js" data-theme="light"></script></body></html>');
  }
  const file = path.resolve(root, decodeURIComponent(req.url.split('?')[0]).replace(/^\/widget\//, ''));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.setHeader('Content-Type', ({'.js': 'text/javascript', '.html': 'text/html', '.css': 'text/css', '.woff2': 'font/woff2', '.png': 'image/png'})[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});

(async () => {
  fs.mkdirSync(output, {recursive: true});
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'launcho-signup-browser-'));
  const chrome = spawn(process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], {windowsHide: true, stdio: 'ignore'});
  let socket;
  try {
    let port;
    for (let i = 0; i < 100; i++) {
      try { port = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]; break; } catch { await sleep(100); }
    }
    assert.ok(port, 'Chrome did not start');
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    socket = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl); await once(socket, 'open');
    let id = 0;
    const pending = new Map(), errors = [], results = [], accessibility = [];
    socket.addEventListener('message', event => {
      const data = JSON.parse(event.data);
      if (data.id) { const callback = pending.get(data.id); pending.delete(data.id); callback?.(data); }
      if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);
    });
    const command = (method, params = {}) => new Promise((resolve, reject) => {
      const key = ++id;
      const timer = setTimeout(() => { pending.delete(key); reject(new Error(`Timeout: ${method}`)); }, 10000);
      pending.set(key, data => { clearTimeout(timer); data.error ? reject(new Error(data.error.message)) : resolve(data.result); });
      socket.send(JSON.stringify({id: key, method, params}));
    });
    const evaluate = async expression => {
      const result = await command('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
      if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    };
    const wait = async expression => {
      for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(50); }
      const state = await evaluate(`({text: window.doc?.body.innerText, active: window.doc?.activeElement?.outerHTML})`);
      throw new Error(`Timed out: ${expression}\n${JSON.stringify({state, calls, errors})}`);
    };
    const key = async (name, code = name) => {
      await command('Input.dispatchKeyEvent', {type: 'keyDown', key: name, code, windowsVirtualKeyCode: {Tab: 9, Enter: 13, Escape: 27}[name], ...(name === 'Enter' ? {text: '\r', unmodifiedText: '\r'} : {})});
      await command('Input.dispatchKeyEvent', {type: 'keyUp', key: name, code, windowsVirtualKeyCode: {Tab: 9, Enter: 13, Escape: 27}[name]});
    };
    const screenshot = async name => {
      await evaluate('doc.fonts.ready');
      const shot = await command('Page.captureScreenshot', {format: 'png'});
      fs.writeFileSync(path.join(output, name + '.png'), Buffer.from(shot.data, 'base64'));
      if (name.endsWith('-form') || name.endsWith('-review')) {
        const position = await evaluate(`doc.querySelector('#scroll-area').scrollTop`);
        await evaluate(`doc.querySelector('#scroll-area').scrollTop = doc.querySelector('#scroll-area').scrollHeight`);
        const bottom = await command('Page.captureScreenshot', {format: 'png'});
        fs.writeFileSync(path.join(output, name + '-bottom.png'), Buffer.from(bottom.data, 'base64'));
        await evaluate(`doc.querySelector('#scroll-area').scrollTop = ${position}`);
      }
    };
    const change = (name, value) => evaluate(`(() => { const field = doc.querySelector('#local-signup').elements[${JSON.stringify(name)}]; field.value = ${JSON.stringify(value)}; field.dispatchEvent(new doc.defaultView.Event('input', {bubbles:true})); field.dispatchEvent(new doc.defaultView.Event('change', {bubbles:true})); })()`);
    const confirmCalls = () => calls.filter(c => c.url.endsWith('/confirm')).length;
    const save = async () => {
      await evaluate(`doc.querySelector('#signup-save').focus()`);
      await key('Enter');
      await wait(`doc.querySelector('#session-review').hidden === false && doc.querySelector('#confirm').disabled === false`);
      assert.equal(await evaluate(`doc.activeElement.id`), 'review-title');
    };
    const edit = async () => {
      await evaluate(`doc.querySelector('#edit-signup').focus()`);
      await key('Enter');
      await wait(`doc.querySelector('#local-signup').hidden === false && doc.querySelector('#signup-save').disabled === false`);
      assert.equal(await evaluate(`doc.querySelector('#session-review').hidden && doc.querySelector('#confirm').disabled`), true);
    };
    await command('Runtime.enable');
    // Block accidental network access beyond the controlled server.
    await command('Fetch.enable', {patterns: [{urlPattern: '*', requestStage: 'Request'}]});
    socket.addEventListener('message', event => {
      const data = JSON.parse(event.data);
      if (data.method === 'Fetch.requestPaused') {
        const allowed = data.params.request.url.startsWith(base + '/') || data.params.request.url.startsWith('data:');
        if (!allowed) errors.push(`Unexpected external request: ${data.params.request.url}`);
        command(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest', {requestId: data.params.requestId, ...(!allowed ? {errorReason: 'BlockedByClient'} : {})}).catch(error => errors.push(error.message));
      }
    });
    for (const [width, height] of [[1280, 900], [390, 844], [320, 568]]) {
      for (const kind of ['shop', 'website']) {
        revision = 0; preferences = {}; calls = []; currentReview = null;
        await command('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width < 480});
        await command('Page.navigate', {url: base});
        await wait('!!window.LaunchoWidget');
        await evaluate('LaunchoWidget.open()');
        await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.style.visibility === 'visible'`);
        await evaluate(`window.frame = document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe'); window.doc = frame.contentDocument`);
        await wait(`doc.querySelector('#local-signup').hidden === false && doc.querySelector('#signup-save').disabled === false`);
        if (kind === 'shop') {
          if (width < 600) {
            await evaluate(`doc.querySelector('[name=businessName]').value='حفظ انتخاب'; doc.querySelector('#change-service').focus()`);
            await key('Enter'); await wait(`doc.querySelector('#service-sheet').open`);
            assert.equal(await evaluate('doc.activeElement.dataset.service'), 'assistant');
            await key('Tab'); assert.equal(await evaluate('doc.activeElement.dataset.service'), 'callcenter');
            await key('Enter'); await wait(`!doc.querySelector('#service-sheet').open`);
            assert.equal(await evaluate(`doc.querySelector('#assistant-content').hidden && !doc.querySelector('#unavailable-service').hidden`), true);
            assert.equal(await evaluate('doc.activeElement.id'), 'change-service');
            await key('Enter'); await wait(`doc.querySelector('#service-sheet').open`);
            await key('Escape'); await wait(`!doc.querySelector('#service-sheet').open`);
            assert.equal(await evaluate(`!document.querySelector('#launcho-widget').shadowRoot.querySelector('.panel').hidden`), true, 'Escape dismisses sheet before widget');
            await key('Enter'); await wait(`doc.querySelector('#service-sheet').open`);
            await evaluate(`doc.querySelector('#mobile-services [data-service=assistant]').focus()`);
            await key('Enter'); await wait(`!doc.querySelector('#assistant-content').hidden`);
            assert.equal(await evaluate(`doc.querySelector('[name=businessName]').value`), 'حفظ انتخاب');
          }
          const tree = await command('Page.getFrameTree');
          const frameId = tree.frameTree.childFrames.find(item => item.frame.url.includes('/widget/widget.html')).frame.id;
          const ax = await command('Accessibility.getFullAXTree', {frameId});
          const controls = ax.nodes.filter(node => !node.ignored && ['button','link','textbox','combobox'].includes(node.role?.value));
          assert.ok(controls.length >= 10);
          assert.deepEqual(controls.filter(node => !node.name?.value?.trim()).map(node => node.role.value), [], 'visible controls need accessible names');
          accessibility.push({width, namedControls:controls.length});
          await command('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:'reduce'}]});
          assert.equal(await evaluate(`doc.defaultView.matchMedia('(prefers-reduced-motion: reduce)').matches && getComputedStyle(doc.querySelector('.typing-dots i')).animationName === 'none'`), true);
          await command('Emulation.setEmulatedMedia', {features:[]});
        }
        if (kind === 'website') { await change('kind', kind); await wait(`!doc.querySelector('#signup-save').disabled`); }
        const options = fixture.signupOptions[kind];
        // Exercise every catalog-backed choice without navigating to the public site.
        if (width === 1280) {
          const available = options.templates.filter(item => item.available);
          assert.equal(await evaluate(`doc.querySelector('[name=template]').options.length`), available.length);
          for (const template of available) {
            await change('template', template.id);
            assert.equal(await evaluate(`doc.querySelector('#local-template-preview').hidden`), !template.previewUrl);
            if (template.previewUrl) assert.equal(await evaluate(`doc.querySelector('#local-template-preview').href`), template.previewUrl);
          }
          for (const category of options.businessCategories) {
            await change('category', category.id);
            const actual = await evaluate(`Array.from(doc.querySelector('[name=template]').options).filter(option => option.textContent.includes('(پیشنهادی)')).map(option => option.value)`);
            assert.deepEqual(actual, available.filter(item => item.recommendedFor?.includes(category.id)).map(item => item.id));
          }
          await change('category', options.businessCategories[0].id);
          await change('template', available[0].id);
          console.log(`PASS: ${kind} catalog ${available.length} choices, every preview binding and category recommendation`);
        }
        await change('businessName', kind === 'shop' ? 'ماه‌چهره' : 'استودیو ماه');
        await change('label', 'mahchehre');
        await change('planMonths', '6');
        // Actual Tab navigation in the iframe, including all seven form controls.
        await evaluate(`doc.querySelector('#local-signup [name=kind]').focus()`);
        for (const name of ['businessName', 'category', 'template']) {
          await key('Tab');
          assert.equal(await evaluate('doc.activeElement.name'), name);
          assert.equal(await evaluate(`doc.activeElement.getBoundingClientRect().bottom <= doc.querySelector('#scroll-area').getBoundingClientRect().bottom + 1`), true);
        }
        if (await evaluate(`!doc.querySelector('#local-template-preview').hidden`)) {
          await key('Tab'); assert.equal(await evaluate('doc.activeElement.id'), 'local-template-preview');
        }
        for (const name of ['planMonths', 'label', 'tld']) {
          await key('Tab'); assert.equal(await evaluate('doc.activeElement.name'), name);
        }
        await key('Tab'); assert.equal(await evaluate('doc.activeElement.id'), 'signup-save');
        await evaluate(`doc.querySelector('#signup-title').focus(); doc.querySelector('#scroll-area').scrollTop = doc.querySelector('#local-signup').offsetTop - 85`);
        await screenshot(`${width}-${kind}-form`);
        await save();
        await key('Enter');
        assert.equal(confirmCalls(), 0, 'saving and reviewing must not confirm');
        // Review title -> edit -> confirm, with native scrolling to offscreen controls.
        await key('Tab'); assert.equal(await evaluate('doc.activeElement.id'), 'edit-signup');
        await key('Tab'); assert.equal(await evaluate('doc.activeElement.id'), 'confirm');
        assert.equal(await evaluate(`(() => { const button = doc.querySelector('#confirm').getBoundingClientRect(); const area = doc.querySelector('#scroll-area').getBoundingClientRect(); return button.top >= area.top && button.bottom <= area.bottom + 1; })()`), true);
        await evaluate(`doc.querySelector('#review-title').focus(); doc.querySelector('#scroll-area').scrollTop = doc.querySelector('#session-review').offsetTop - 85`);
        assert.equal(await evaluate(`doc.querySelector('#local-signup').hidden`), true);
        const text = await evaluate(`doc.querySelector('#review-summary').textContent`);
        assert.ok(text.includes(kind === 'shop' ? 'فروشگاه' : 'سایت‌ساز'));
        assert.ok(text.includes(options.businessCategories[0].label));
        assert.ok(text.includes('۶ ماهه'));
        assert.ok(text.includes('mahchehre.ir'));
        await screenshot(`${width}-${kind}-review`);
        // Every choice is editable, and reopening preserves the current selection.
        await edit();
        assert.equal(await evaluate(`doc.querySelector('[name=businessName]').value`), kind === 'shop' ? 'ماه‌چهره' : 'استودیو ماه');
        await change('businessName', 'نام ویرایش‌شده');
        await change('category', options.businessCategories[1].id);
        const templates = options.templates.filter(x => x.available);
        await change('template', templates.at(-1).id);
        await change('planMonths', '12'); await change('label', 'edited-name'); await change('tld', 'com');
        await save();
        const updated = await evaluate(`doc.querySelector('#review-summary').textContent`);
        for (const value of ['نام ویرایش‌شده', options.businessCategories[1].label, templates.at(-1).label, '۱۲ ماهه', 'edited-name.com']) assert.ok(updated.includes(value), value);
        assert.equal(confirmCalls(), 0);
        await screenshot(`${width}-${kind}-edited-review`);
        await edit();
        // Change service type as part of editing; only that service's choices survive.
        const otherKind = kind === 'shop' ? 'website' : 'shop';
        await change('kind', otherKind); await wait(`!doc.querySelector('#signup-save').disabled`);
        assert.equal(await evaluate(`doc.querySelector('[name=planMonths]').value`), '12');
        assert.equal(await evaluate(`doc.querySelector('[name=tld]').value`), 'com');
        await save();
        assert.equal(preferences.kind, otherKind);
        assert.ok(fixture.signupOptions[otherKind].businessCategories.some(x => x.id === preferences.category));
        assert.ok(fixture.signupOptions[otherKind].templates.some(x => x.id === preferences.template));
        assert.equal(await evaluate(`doc.documentElement.scrollWidth <= frame.clientWidth && doc.body.scrollWidth <= frame.clientWidth && getComputedStyle(doc.documentElement).direction === 'rtl'`), true);
        await edit();
        // Browser validation prevents invalid domain and empty/invisible business names.
        const before = calls.length;
        await change('label', '-bad domain');
        await evaluate(`doc.querySelector('#local-signup').requestSubmit()`); await sleep(100);
        assert.equal(calls.length, before);
        await change('label', 'edited-name'); await change('businessName', '\u200b\u200c');
        await evaluate(`doc.querySelector('#local-signup').requestSubmit()`); await sleep(100);
        assert.equal(calls.length, before);
        await change('businessName', 'نام ویرایش‌شده');
        saveFailure = true;
        await evaluate(`doc.querySelector('#local-signup').requestSubmit()`);
        await wait(`doc.querySelector('#local-signup-status').textContent.length > 0 && !doc.querySelector('#signup-save').disabled`);
        assert.equal(await evaluate(`doc.querySelector('[name=businessName]').value`), 'نام ویرایش‌شده');
        assert.equal(await evaluate(`doc.querySelector('#confirm').disabled`), true);
        saveFailure = false;
        // While saving, chat, editing and duplicate submits cannot race the revision.
        const savesBefore = calls.filter(c => c.url.endsWith('/preferences')).length;
        await evaluate(`doc.querySelector('#local-signup').requestSubmit(); doc.querySelector('#local-signup').dispatchEvent(new doc.defaultView.Event('submit',{cancelable:true})); doc.querySelector('#form').requestSubmit()`);
        assert.equal(await evaluate(`doc.querySelector('[name=businessName]').disabled && doc.querySelector('#send').disabled && doc.querySelector('#edit-signup').disabled`), true);
        await wait(`!doc.querySelector('#session-review').hidden && !doc.querySelector('#confirm').disabled`);
        assert.equal(calls.filter(c => c.url.endsWith('/preferences')).length, savesBefore + 1);
        assert.equal(confirmCalls(), 0);
        // A lost confirmation freezes editing. Only a second explicit action retries.
        unknown = true;
        await evaluate(`doc.querySelector('#confirm').focus()`); await key('Enter');
        await wait(`!doc.querySelector('#error').hidden && !doc.querySelector('#confirm').disabled`);
        assert.equal(confirmCalls(), 1);
        assert.equal(await evaluate(`doc.querySelector('#edit-signup').disabled`), true);
        await evaluate(`doc.querySelector('#edit-signup').click(); doc.querySelector('#local-signup').dispatchEvent(new doc.defaultView.Event('submit',{cancelable:true}));`);
        assert.equal(confirmCalls(), 1);
        unknown = false;
        await key('Enter');
        await wait(`doc.querySelector('#confirm').hidden`);
        assert.equal(confirmCalls(), 2);
        const confirms = calls.filter(c => c.url.endsWith('/confirm'));
        assert.deepEqual(confirms[0].body, confirms[1].body);
        assert.equal(await evaluate(`doc.querySelector('#review-summary a').getAttribute('href')`), base + '/api/local-drafts/sd_signupbrowser/preview');
        await key('Escape');
        await wait(`document.querySelector('#launcho-widget').shadowRoot.activeElement?.tagName === 'BUTTON'`);
        results.push({width, height, kind, passed: true});
        console.log(`PASS: ${width}px ${kind}, form, edits, Persian review, service switch, validation, keyboard, locks, explicit confirm retry`);
      }
    }
    // Recovery when options are unavailable or malformed, followed by review failure.
    optionFailure = true;
    await command('Page.navigate', {url: base}); await wait('!!window.LaunchoWidget'); await evaluate('LaunchoWidget.open()');
    await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.style.visibility === 'visible'`);
    await evaluate(`window.frame = document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe'); window.doc = frame.contentDocument`);
    await wait(`!doc.querySelector('#signup-retry').hidden && !doc.querySelector('#signup-retry').disabled`);
    assert.equal(await evaluate(`doc.querySelector('#signup-save').disabled`), true);
    optionFailure = false; malformedOptions = true;
    await evaluate(`doc.querySelector('#signup-retry').click()`);
    await wait(`!doc.querySelector('#signup-retry').hidden && !doc.querySelector('#signup-retry').disabled`);
    assert.equal(await evaluate(`doc.querySelector('#signup-save').disabled`), true);
    malformedOptions = false;
    await evaluate(`doc.querySelector('#signup-retry').click()`); await wait(`!doc.querySelector('#signup-save').disabled`);
    await change('businessName', 'آزمون بازیابی'); await change('label', 'recovery');
    reviewFailure = true;
    await evaluate(`doc.querySelector('#local-signup').requestSubmit()`);
    await wait(`!doc.querySelector('#error').hidden && !doc.querySelector('#review-button').disabled`);
    assert.equal(await evaluate(`doc.querySelector('#confirm').disabled`), true);
    reviewFailure = false;
    await evaluate(`doc.querySelector('#review-button').click()`);
    await wait(`!doc.querySelector('#session-review').hidden && !doc.querySelector('#confirm').disabled`);
    await screenshot('320-recovered-review');
    await evaluate(`LaunchoWidget.setTheme('dark')`);
    await wait(`doc.documentElement.dataset.theme === 'dark'`);
    await screenshot('320-dark-review');
    assert.equal(await evaluate(`doc.documentElement.scrollWidth <= frame.clientWidth`), true);
    assert.deepEqual(errors, []);
    const browserVersion = await command('Browser.getVersion');
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify({browser: browserVersion.product, userAgent:browserVersion.userAgent, accessibility,
      mainWidget: true, controlledResponses: true, externalNetworkBlocked: true, results, optionsRecovery: true, reviewRecovery: true,
      darkThemeScreenshot: true, mobileServiceKeyboard:true, reducedMotion:true, untested: ['real backend integration', 'real draft creation', 'physical mobile keyboard', 'screen reader speech', 'Safari', 'Firefox'],
      backendLimitation: {evidence: 'app/api/routes.py:52-62 (read only)', verification: 'source inspection; backend not executed',
        reproduce: ['Start the existing backend with an adapter mode other than local_mock.', 'GET /api/local-signup-options?kind=shop or kind=website returns 404 by the mode guard.', 'The main widget therefore has no catalog-backed form in that mode.']}, errors}, null, 2));
    console.log('PASS: unavailable/malformed options and review error recovery; no external network or browser exceptions');
    console.log(`Screenshots and report: ${output}`);
  } finally {
    socket?.close(); chrome.kill(); server.closeAllConnections(); server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
