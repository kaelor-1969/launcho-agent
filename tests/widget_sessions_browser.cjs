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
const sid = 'browser-session-id', token = 'browser-session-token';
const server = http.createServer(async (req, res) => {
  const json = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
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
      if (lost) {
        lost = false;
        res.statusCode = 503;
        return json({detail: {code: 'draft_outcome_unknown'}});
      }
      return setTimeout(() => json({status: 'draft', ref: 'sd_browsertest',
        confirmUrl: 'https://launcho.ir/start?signup=sd_browsertest'}), 200);
    }
    res.writeHead(404); return res.end();
  }
  if (req.url === '/api/sessions/' + sid) {
    assert.equal(req.headers['x-session-token'], token);
    return json({sessionId: sid, revision: 1, history: [
      {role: 'user', content: 'confirm now'},
      {role: 'assistant', content: 'answer restored after refresh'},
    ]});
  }
  if (req.url === '/') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    return res.end('<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><script defer src="/widget/loader.js"></script>');
  }
  const file = path.resolve(root, decodeURIComponent(req.url.split('?')[0]).replace(/^\/widget\//, ''));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.setHeader('Content-Type', ({'.js':'text/javascript', '.html':'text/html', '.css':'text/css', '.woff2':'font/woff2'})[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});

(async () => {
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
    const pending = new Map(), errors = [];
    socket.addEventListener('message', event => {
      const data = JSON.parse(event.data);
      if (data.id) { const cb = pending.get(data.id); pending.delete(data.id); cb(data); }
      if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);
    });
    const command = (method, params = {}) => new Promise((resolve, reject) => {
      const key = ++id;
      pending.set(key, data => data.error ? reject(new Error(data.error.message)) : resolve(data.result));
      socket.send(JSON.stringify({id: key, method, params}));
    });
    const evaluate = async expression => {
      const result = await command('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
      if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    };
    const wait = async expression => {
      for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await sleep(50); }
      throw new Error(`Timed out: ${expression}`);
    };
    await command('Runtime.enable');
    for (const width of [1280, 390]) {
      calls.length = 0; lost = true;
      await command('Emulation.setDeviceMetricsOverride', {width, height: 844, deviceScaleFactor: 1, mobile: width < 480});
      await command('Page.navigate', {url: base});
      await wait('!!window.LaunchoWidget');
      assert.equal(calls.length, 0, 'session must be lazy');
      await evaluate('LaunchoWidget.open()');
      await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.contentDocument?.querySelector('#message')`);
      await evaluate(`window.frame = document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe'); window.doc = frame.contentDocument`);
      await wait(`frame.style.visibility === 'visible' && doc.querySelector('.primary-starter')?.disabled === false`);
      assert.equal(calls.length, 1);
      assert.ok(await evaluate(`frame.getAttribute('src').startsWith('/widget/widget.html#')`));
      await evaluate(`doc.querySelector('#message').value = 'confirm now'; doc.querySelector('#form').requestSubmit()`);
      await wait(`doc.querySelector('#review-button').hidden === false`);
      assert.equal(calls.length, 2);
      const {requestId, ...chatBody} = calls[1].body;
      assert.match(requestId, /^[a-f0-9-]{36}$/);
      assert.deepEqual(chatBody, {message: 'confirm now', sessionId: sid});
      assert.equal(calls[1].token, token);
      await evaluate(`doc.querySelector('#review-button').click()`);
      await wait(`doc.querySelector('#confirm').disabled === false`);
      assert.equal(calls.length, 3);
      await evaluate(`doc.querySelector('#confirm').click()`);
      await wait(`doc.querySelector('#error').hidden === false`);
      assert.equal(calls.length, 4, 'no automatic retry');
      await evaluate(`doc.querySelector('#message').dispatchEvent(new doc.defaultView.Event('input', {bubbles:true}))`);
      assert.equal(await evaluate(`doc.querySelector('#error').hidden`), false, 'typing must preserve unknown-outcome guidance');
      await evaluate(`doc.querySelector('#confirm').click(); doc.querySelector('#confirm').click()`);
      await wait(`doc.querySelector('#confirm').hidden === true`);
      assert.equal(calls.length, 5);
      assert.deepEqual(calls[3].body, calls[4].body);
      assert.equal(await evaluate(`doc.querySelector('#review-summary a').getAttribute('href')`), 'https://launcho.ir/start?signup=sd_browsertest');
      await evaluate('LaunchoWidget.close(); LaunchoWidget.open()');
      assert.equal(calls.filter(c => c.url === '/api/sessions').length, 1);
      assert.equal(await evaluate(`doc.querySelectorAll('input[type=tel], [autocomplete=tel], [data-action=pay]').length`), 0);
      assert.equal(await evaluate(`doc.defaultView.localStorage.length`), 0);
      assert.equal(await evaluate(`Object.keys(doc.defaultView.sessionStorage).filter(key => key.startsWith('launcho.chat.session:')).length`), 1);
      assert.equal(await evaluate(`doc.documentElement.scrollWidth <= frame.clientWidth`), true);
      for (const call of calls.slice(1)) {
        assert.equal(call.token, token, 'every owned request must be authenticated');
        assert.equal(JSON.stringify(call.body).includes(token), false);
      }
      assert.equal(await evaluate(`doc.body.textContent.includes('browser-session-token') || doc.body.textContent.includes('browser-confirmation-token')`), false);
      console.log(`PASS: Chrome ${width}px session, chat, review, manual confirmation retry, relative iframe, tab-scoped session`);

      await command('Page.reload');
      await wait('!!window.LaunchoWidget');
      await evaluate('LaunchoWidget.open()');
      await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.contentDocument?.body?.textContent.includes('answer restored after refresh')`);
      await evaluate(`window.frame = document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe'); window.doc = frame.contentDocument`);
      assert.equal(calls.filter(call => call.url === '/api/sessions').length, 1);

      // A separate page lifecycle checks failure recovery and invalidated reviews.
      await evaluate("Object.keys(doc.defaultView.sessionStorage).filter(key => key.startsWith('launcho.chat.session:')).forEach(key => doc.defaultView.sessionStorage.removeItem(key))");
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
      console.log(`PASS: Chrome ${width}px failed session retry, persistent error guidance, discarded stale review, manual review recovery`);
      await evaluate("Object.keys(doc.defaultView.sessionStorage).filter(key => key.startsWith('launcho.chat.session:')).forEach(key => doc.defaultView.sessionStorage.removeItem(key))");
    }
    calls.length = 0;
    await command('Page.navigate', {url: base + '/widget/demo.html'});
    await wait('!!window.LaunchoWidget');
    await evaluate('LaunchoWidget.open()');
    await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.style.visibility === 'visible'`);
    assert.equal(calls.length, 0, 'explicit demo must not make production API calls');
    console.log('PASS: explicit demo remains isolated from session and draft APIs');
    assert.deepEqual(errors, []);
  } finally {
    if (socket) socket.close();
    chrome.kill();
    // Retain the temporary profile for OS-managed cleanup; never delete a computed tree.
    server.closeAllConnections(); server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
