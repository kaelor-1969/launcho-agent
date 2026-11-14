// Native Chrome smoke test, no npm/Python dependencies or live services.
// Run: node tests/widget_sessions_browser.cjs
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const root = path.resolve(__dirname, '../frontend');
const calls = [];
let lost = true;
let failSession = false, failReview = false;
let confirmError;
let statusFailure = false, currentDraftStatus = 'draft';
let blockFrame = false;
let completeConfirmation;
const output = process.env.WIDGET_ARTIFACT_DIR ? path.resolve(process.env.WIDGET_ARTIFACT_DIR) : path.resolve(__dirname, '../artifacts/widget-person3/sessions');
const sid = 'browser-session-id', token = 'browser-session-token';
const server = http.createServer(async (req, res) => {
  const json = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
  if (req.url.endsWith('/draft-status')) {
    calls.push({url:req.url, token:req.headers['x-session-token'], method:req.method});
    assert.equal(req.method, 'GET'); assert.equal(req.headers['x-session-token'], token);
    return setTimeout(() => {
      if (statusFailure) { res.statusCode=503; return json({detail:{code:'draft_status_unavailable'}}); }
      json({status:currentDraftStatus});
    }, 150);
  }
  if (req.method === 'POST') {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw);
    calls.push({url: req.url, body, token: req.headers['x-session-token']});
    if (req.url === '/api/sessions') {
      if (failSession) { res.statusCode = 503; return json({detail: {code: 'internal_error'}}); }
      return json({sessionId: sid, sessionToken: token, revision: 0});
    }
    if (req.url === '/api/chat') return json({sessionId: sid, revision: 1, reply: '<script>bad()</script>', nextAction: 'review'});
    if (req.url.endsWith('/review')) {
      if (failReview) { res.statusCode = 503; return json({detail: {code: 'internal_error'}}); }
      return json({sessionId: sid, revision: 1, reviewId: 'browser-review-id',
      confirmationToken: 'browser-confirmation-token', canConfirm: true,
      summary: {kind: 'shop', businessName: 'نمونه', category: 'fashion', planMonths: 3,
        template: 'classic', domain: {ownDomain: 'example.ir'}}});
    }
    if (req.url.endsWith('/confirm')) {
      if (confirmError) { res.statusCode = 410; return json({detail:{code:confirmError, message:'private upstream detail'}}); }
      if (lost) {
        lost = false;
        // The server accepted the request, but the response connection breaks.
        // Flush partial JSON so Chrome cannot transparently retry an unopened socket.
        res.writeHead(200, {'Content-Type':'application/json'});
        res.flushHeaders(); res.write('{');
        return setTimeout(() => res.destroy(), 30);
      }
      // Hold the response until the test has observed locks and duplicate input.
      completeConfirmation = () => json({status: 'draft', ref: 'sd_browsertest',
        confirmUrl: 'https://launcho.ir/start?signup=sd_browsertest'});
      return;
    }
    res.writeHead(404); return res.end();
  }
  if (req.url === '/') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    return res.end('<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><script defer src="/widget/loader.js" data-auto-open="false"></script>');
  }
  if (blockFrame && req.url.startsWith('/widget/widget.html')) return;
  const file = path.resolve(root, decodeURIComponent(req.url.split('?')[0]).replace(/^\/widget\//, ''));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.setHeader('Content-Type', ({'.js':'text/javascript', '.html':'text/html', '.css':'text/css', '.woff2':'font/woff2'})[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});

(async () => {
  fs.mkdirSync(output, {recursive:true});
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'launcho-widget-browser-'));
  const chrome = spawn(process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
      '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], {windowsHide: true, stdio: 'ignore'});
  let socket;
  try {
    let port;
    for (let i = 0; i < 100; i++) {
      try { port = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]; break; } catch { await sleep(100); }
    }
    assert.ok(port, 'Chrome did not start');
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    socket = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
    await once(socket, 'open');
    let id = 0;
    const pending = new Map(), errors = [], networkRequests = [], dialogs = [];
    socket.addEventListener('message', event => {
      const data = JSON.parse(event.data);
      if (data.id) { const cb = pending.get(data.id); pending.delete(data.id); cb(data); }
      if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);
      if (data.method === 'Network.requestWillBeSent' && data.params.request.url.endsWith('/api/chat')) networkRequests.push(data.params.request);
      if (data.method === 'Page.javascriptDialogOpening') {
        dialogs.push(data.params.type);
        command('Page.handleJavaScriptDialog', {accept:false}).catch(error => errors.push(error.message));
      }
    });
    const command = (method, params = {}) => new Promise((resolve, reject) => {
      const key = ++id;
      const timer = setTimeout(() => {
        pending.delete(key);
        reject(new Error(`Browser did not respond to ${method}`));
      }, 10000);
      pending.set(key, data => {
        clearTimeout(timer);
        if (data.error) reject(new Error(data.error.message));
        else resolve(data.result);
      });
      socket.send(JSON.stringify({id: key, method, params}));
    });
    const evaluate = async expression => {
      const result = await command('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
      if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    };
    const screenshot = async name => {
      const shot = await command('Page.captureScreenshot', {format:'png'});
      fs.writeFileSync(path.join(output, name + '.png'), Buffer.from(shot.data, 'base64'));
    };
    const wait = async expression => {
      for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await sleep(50); }
      throw new Error(`Timed out: ${expression}`);
    };
    const confirmWithKeyboard = async () => {
      await evaluate(`doc.querySelector('#confirm').focus()`);
      await command('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r'});
      await command('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13});
    };
    const confirmWithDoubleClick = async () => {
      const point = await evaluate(`(() => {
        const button = doc.querySelector('#confirm'); button.scrollIntoView({block:'center'});
        const rect = button.getBoundingClientRect(), host = frame.getBoundingClientRect();
        return {x:host.left + rect.left + rect.width/2, y:host.top + rect.top + rect.height/2};
      })()`);
      for (const clickCount of [1, 2]) {
        await command('Input.dispatchMouseEvent', {type:'mousePressed', button:'left', ...point, clickCount});
        await command('Input.dispatchMouseEvent', {type:'mouseReleased', button:'left', ...point, clickCount});
      }
    };
    await command('Runtime.enable');
    await command('Page.enable');
    await command('Network.enable');
    for (const width of [1280, 390]) {
      calls.length = 0; lost = true;
      await command('Emulation.setDeviceMetricsOverride', {width, height: 844, deviceScaleFactor: 1, mobile: width < 480});
      await command('Page.navigate', {url: base});
      await wait('!!window.LaunchoWidget');
      await wait(`!!document.querySelector('#launcho-widget')`);
      assert.equal(await evaluate(`document.querySelector('#launcho-widget').shadowRoot.querySelectorAll('iframe').length`), 0);
      assert.equal(calls.length, 0, 'session must be lazy');
      await evaluate('LaunchoWidget.open()');
      await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.contentDocument?.querySelector('#message')`);
      await evaluate(`window.frame = document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe'); window.doc = frame.contentDocument`);
      await wait(`frame.style.visibility === 'visible' && doc.querySelector('.primary-starter')?.disabled === false`);
      assert.equal(calls.length, 1);
      assert.ok(await evaluate(`(() => {
        const url = new URL(frame.src);
        return url.origin === location.origin && url.pathname === '/widget/widget.html' &&
          new URLSearchParams(url.hash.slice(1)).get('parentOrigin') === location.origin;
      })()`));
      assert.equal(await evaluate(`frame.title.length > 0 && frame.referrerPolicy === 'no-referrer' && !frame.sandbox.contains('allow-modals')`), true);
      assert.equal(await evaluate(`document.querySelector('#launcho-widget').shadowRoot.querySelector('.feedback').hidden`), true);
      assert.equal(await evaluate(`document.querySelectorAll('#launcho-widget').length`), 1);
      // Real browser transport offline; never change the system network settings.
      await command('Network.emulateNetworkConditions', {offline:true, latency:0, downloadThroughput:-1, uploadThroughput:-1});
      await evaluate(`doc.querySelector('#message').value = 'confirm now'; doc.querySelector('#form').requestSubmit()`);
      await wait(`!doc.querySelector('#error').hidden && !doc.querySelector('#retry').disabled`);
      assert.equal(calls.length, 1, 'offline request must not reach the HTTP fixture');
      const offlineBody = JSON.parse(networkRequests.at(-1).postData);
      await command('Network.emulateNetworkConditions', {offline:false, latency:0, downloadThroughput:-1, uploadThroughput:-1});
      await sleep(100);
      assert.equal(calls.length, 1, 'reconnection must not retry automatically');
      await evaluate(`doc.querySelector('#retry').click()`);
      await wait(`doc.querySelector('#review-button').hidden === false`);
      assert.equal(calls.length, 2);
      assert.deepEqual(calls[1].body, offlineBody, 'offline retry must preserve message/session/requestId');
      assert.equal(await evaluate(`doc.querySelectorAll('#messages .role-user').length`), 1);
      const {requestId, ...chatBody} = calls[1].body;
      assert.match(requestId, /^[a-f0-9-]{36}$/);
      assert.deepEqual(chatBody, {message: 'confirm now', sessionId: sid});
      assert.equal(calls[1].token, token);
      await evaluate(`doc.querySelector('#review-button').click()`);
      await wait(`doc.querySelector('#confirm').disabled === false`);
      assert.equal(calls.length, 3);
      assert.equal(await evaluate(`(() => { const button=doc.querySelector('#confirm'); button.click(); return button.disabled; })()`), false,
        'a synthetic click must not enter the pending confirmation state');
      assert.equal(calls.length, 3, 'scripted clicks cannot authorize confirmation');
      await confirmWithKeyboard();
      await wait(`doc.querySelector('#error').hidden === false`);
      assert.equal(calls.length, 4, 'no automatic retry');
      assert.match(await evaluate(`doc.querySelector('#error-text').textContent`), /تازه نکن/);
      assert.equal(await evaluate(`doc.querySelector('#confirm').textContent`), 'بررسی نتیجهٔ همان درخواست');
      await screenshot(`${width}-unknown-confirmation`);
      // Invalid origins, channels, scopes and senders cannot clear host protection.
      await evaluate(`(() => {
        const channel = new URLSearchParams(new URL(frame.src).hash.slice(1)).get('channel');
        for (const override of [{origin:'https://evil.invalid'}, {source:window}, {data:{scope:'launcho',channel:'wrong',type:'confirmation-resolved'}}, {data:{scope:'wrong',channel,type:'confirmation-resolved'}}]) {
          window.dispatchEvent(new MessageEvent('message', {origin:location.origin,source:frame.contentWindow,data:{scope:'launcho',channel,type:'confirmation-resolved'},...override}));
        }
      })()`);
      const previousDialogs = dialogs.length;
      await command('Page.reload');
      for (let i=0; i<100 && dialogs.length === previousDialogs; i++) await sleep(50);
      assert.equal(dialogs.length, previousDialogs + 1, 'unknown confirmation must warn before refresh');
      assert.equal(dialogs.at(-1), 'beforeunload');
      assert.equal(calls.length, 4, 'cancelled refresh must retain the current pending request');
      await evaluate(`doc.querySelector('#message').dispatchEvent(new doc.defaultView.Event('input', {bubbles:true}))`);
      assert.equal(await evaluate(`doc.querySelector('#error').hidden`), false, 'typing must preserve unknown-outcome guidance');
      await confirmWithDoubleClick();
      assert.equal(await evaluate(`doc.querySelector('#confirm').disabled && doc.querySelector('#send').disabled && doc.querySelector('#review-button').disabled`), true);
      await confirmWithKeyboard();
      for (let i=0; i<100 && !completeConfirmation; i++) await sleep(50);
      assert.ok(completeConfirmation, 'the held confirmation must reach the fixture');
      completeConfirmation(); completeConfirmation = null;
      await wait(`doc.querySelector('#confirm').hidden === true`);
      assert.equal(calls.length, 5);
      assert.deepEqual(calls[3].body, calls[4].body);
      assert.equal(await evaluate(`doc.querySelector('#review-summary a').getAttribute('href')`), 'https://launcho.ir/start?signup=sd_browsertest');
      assert.equal(await evaluate(`doc.querySelector('#review-summary a').target === '_blank' && doc.querySelector('#review-summary a').rel === 'noopener noreferrer'`), true);
      await screenshot(`${width}-continuation`);
      // Every status is read-only, with one in-flight GET and explicit error retry.
      const statusCallCount = () => calls.filter(call=>call.url.endsWith('/draft-status')).length;
      statusFailure = true;
      await evaluate(`doc.querySelector('#review-summary button').click(); doc.querySelector('#review-summary button').click()`);
      assert.equal(await evaluate(`doc.querySelector('#review-summary button').disabled && doc.querySelector('#review-summary button').getAttribute('aria-busy') === 'true'`), true);
      await wait(`!doc.querySelector('#review-summary button').disabled`);
      assert.equal(statusCallCount(), 1);
      assert.match(await evaluate(`doc.querySelector('#review-notice').textContent`), /فعلاً در دسترس نیست/);
      statusFailure = false;
      for (const [status, text] of [['draft','پیش‌نویس آماده'],['opened','شمارهٔ موبایل'],['mobile_verified','ثبت‌نام را'],['invoiced','فاکتور'],['paid','پرداخت ثبت'],['active','فروشگاه فعال'],['unexpected','وضعیت ثبت‌نام دریافت نشد'],['expired','منقضی']]) {
        currentDraftStatus = status;
        await evaluate(`doc.querySelector('#review-summary button').click()`);
        await wait(`!doc.querySelector('#review-summary button').disabled`);
        assert.ok((await evaluate(`doc.querySelector('#review-notice').textContent`)).includes(text), status);
      }
      assert.equal(statusCallCount(), 9);
      assert.equal(calls.filter(call=>call.url.endsWith('/confirm')).length, 2, 'status reads must not create drafts');
      assert.equal(await evaluate(`!doc.querySelector('#review-summary a').hasAttribute('href') && doc.querySelector('#review-summary a').getAttribute('aria-disabled') === 'true'`), true);
      await screenshot(`${width}-expired-status`);
      await evaluate('LaunchoWidget.close(); LaunchoWidget.open()');
      assert.equal(calls.filter(c => c.url === '/api/sessions').length, 1);
      assert.equal(await evaluate(`doc.querySelectorAll('input[type=tel], [autocomplete=tel], [data-action=pay]').length`), 0);
      assert.equal(await evaluate(`doc.defaultView.localStorage.length + doc.defaultView.sessionStorage.length`), 0);
      assert.equal(await evaluate(`doc.documentElement.scrollWidth <= frame.clientWidth`), true);
      for (const call of calls.slice(1)) {
        assert.equal(call.token, token, 'every owned request must be authenticated');
        assert.equal((JSON.stringify(call.body) || '').includes(token), false);
      }
      assert.equal(await evaluate(`doc.body.textContent.includes('browser-session-token') || doc.body.textContent.includes('browser-confirmation-token')`), false);
      await evaluate('window.reloadMarker = true');
      await command('Page.reload');
      await wait('!!window.LaunchoWidget && !window.reloadMarker');
      await evaluate('LaunchoWidget.open()');
      await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.style.visibility === 'visible'`);
      await evaluate(`window.frame = document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe'); window.doc = frame.contentDocument`);
      await wait(`!doc.querySelector('.primary-starter').disabled`);
      assert.equal(calls.filter(call => call.url.endsWith('/confirm')).length, 2, 'refresh must never replay confirmation');
      assert.equal(calls.filter(call => call.url === '/api/sessions').length, 2, 'refresh starts an empty memory-only session');
      assert.equal(await evaluate(`doc.querySelector('#confirm').disabled && doc.querySelector('#session-review').hidden`), true);
      assert.equal(await evaluate(`doc.defaultView.localStorage.length + doc.defaultView.sessionStorage.length`), 0);
      assert.equal(dialogs.length, previousDialogs + 1, 'resolved confirmation must not warn on refresh');
      console.log(`PASS: Chromium ${width}px offline transport, exact chat retry, broken confirmation socket, native double-click, iframe origin, memory-only credentials`);

      // A separate page lifecycle checks failure recovery and invalidated reviews.
      failSession = true;
      calls.length = 0;
      await command('Page.navigate', {url: base});
      await wait('!!window.LaunchoWidget');
      await evaluate('LaunchoWidget.open()');
      await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.style.visibility === 'visible'`);
      await evaluate(`window.frame = document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe'); window.doc = frame.contentDocument`);
      await wait(`doc.querySelector('#error').hidden === false`);
      await evaluate(`doc.querySelector('#message').value = 'hello'; doc.querySelector('#message').dispatchEvent(new doc.defaultView.Event('input', {bubbles:true}))`);
      assert.equal(await evaluate(`doc.querySelector('#retry').hidden`), false);
      assert.equal(await evaluate(`doc.querySelector('#send').disabled`), true);
      failSession = false;
      await evaluate(`doc.querySelector('#retry').click()`);
      await wait(`doc.querySelector('#send').disabled === false`);
      await evaluate(`doc.querySelector('#form').requestSubmit()`);
      await wait(`doc.querySelector('#review-button').hidden === false`);
      await evaluate(`doc.querySelector('#review-button').click()`);
      await wait(`doc.querySelector('#confirm').disabled === false`);
      failReview = true;
      await evaluate(`doc.querySelector('#review-button').click()`);
      await wait(`doc.querySelector('#error').hidden === false`);
      const before = calls.length;
      await evaluate(`doc.querySelector('#confirm').click()`);
      assert.equal(calls.length, before, 'failed review refresh must discard the old confirmation');
      assert.equal(await evaluate(`doc.querySelector('#session-review').hidden`), true);
      failReview = false;
      await evaluate(`doc.querySelector('#review-button').click()`);
      await wait(`doc.querySelector('#confirm').disabled === false`);
      for (const code of ['review_expired', 'draft_expired', 'stale_confirmation']) {
        confirmError = code;
        const confirmsBefore = calls.filter(call => call.url.endsWith('/confirm')).length;
        await confirmWithKeyboard();
        await wait(`!doc.querySelector('#error').hidden && doc.querySelector('#session-review').hidden`);
        assert.equal(calls.filter(call => call.url.endsWith('/confirm')).length, confirmsBefore + 1);
        assert.match(await evaluate(`doc.querySelector('#error-text').textContent`), /دوباره مرور کن/);
        assert.equal(await evaluate(`doc.body.textContent.includes('private upstream detail')`), false);
        confirmError = null;
        await evaluate(`doc.querySelector('#review-button').click()`);
        await wait(`!doc.querySelector('#confirm').disabled`);
      }
      // Definite rejection clears host unload protection as well as the old review.
      confirmError = 'review_expired';
      await confirmWithKeyboard();
      await wait(`doc.querySelector('#session-review').hidden && !doc.querySelector('#error').hidden`);
      confirmError = null;
      const dialogsBeforeRejectionReload = dialogs.length;
      await evaluate('window.reloadMarker = true'); await command('Page.reload');
      await wait('!!window.LaunchoWidget && !window.reloadMarker');
      assert.equal(dialogs.length, dialogsBeforeRejectionReload);
      console.log(`PASS: Chrome ${width}px failed session retry, persistent error guidance, discarded stale review, manual review recovery`);
    }
    calls.length = 0;
    await command('Page.navigate', {url: base + '/widget/demo.html'});
    await wait('!!window.LaunchoWidget');
    await evaluate('LaunchoWidget.open()');
    await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.style.visibility === 'visible'`);
    assert.equal(calls.length, 0, 'explicit demo must not make production API calls');
    console.log('PASS: explicit demo remains isolated from session and draft APIs');
    blockFrame = true;
    await command('Page.navigate', {url:base}); await wait('!!window.LaunchoWidget');
    await evaluate('LaunchoWidget.open()');
    await wait(`!!document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')`);
    assert.equal(await evaluate(`document.querySelector('#launcho-widget').shadowRoot.querySelector('.feedback').hidden`), false);
    await sleep(15500);
    assert.match(await evaluate(`document.querySelector('#launcho-widget').shadowRoot.querySelector('.feedback').textContent`), /بارگذاری نشد/);
    await screenshot('loader-timeout');
    await evaluate('LaunchoWidget.close();LaunchoWidget.open()');
    assert.equal(await evaluate(`document.querySelector('#launcho-widget').shadowRoot.querySelectorAll('iframe').length`), 1);
    assert.equal(calls.length, 0, 'failed iframe loading must not create sessions or operations');
    console.log('PASS: lazy iframe, authenticated pending flags, status states/retry/locks, rejected unload clearing, loader timeout');
    assert.deepEqual(errors, []);
    const browser = await command('Browser.getVersion');
    fs.writeFileSync(path.join(output,'report.json'), JSON.stringify({browser:browser.product,userAgent:browser.userAgent,
      controlledResponses:true, widths:[1280,390], offlineTransport:true, brokenConfirmationSocket:true,
      exactChatRetry:true, exactConfirmationRetry:true, nativeDoubleClick:true, syntheticApprovalRejected:true,
      pendingRefreshCancelled:true, resolvedRefreshNoReplay:true, rejectionClearsUnload:true, credentialsMemoryOnly:true,
      invalidHostFlagsRejected:true, statusStates:true, statusErrorRetry:true, expiredLinkDisabled:true, lazyIframe:true,
      loaderTimeout:true, demoIsolated:true, errors, untested:['production backend effects','durable refresh recovery','physical devices','Firefox','Safari']},null,2)+'\n');
  } finally {
    if (socket) socket.close();
    chrome.kill();
    // Retain the temporary profile for OS-managed cleanup; never delete a computed tree.
    server.closeAllConnections(); server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
