// Run: node --experimental-vm-modules tests/widget_session_test.cjs
// Isolated widget runtime: no model, network, or draft service is used.
const {strict: assert} = require('node:assert');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.listeners = {}; this.children = []; this.style = {}; this.value = '';
    this.hidden = false; this.disabled = false; this.scrollHeight = 100;
    this.scrollTop = 0; this.clientHeight = 100; this.classList = {add() {}};
  }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  async emit(type, extra = {}) {
    for (const handler of this.listeners[type] || []) await handler({preventDefault() {}, ...extra});
  }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute() {}
  focus() {}
  blur() {}
}

async function widget({sessionFailure = false, canConfirm = true, embedded = false,
  reply = 'ready <script>bad()</script>'} = {}) {
  const nodes = new Map();
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  const calls = [];
  let failSession = sessionFailure, failConfirm = false, rejectConfirm = false, failReview = false;
  let releaseConfirm;
  let chatError;
  let revision = 0;
  const sid = 'session-id-for-testing', token = 'secret-session-token';
  const review = {sessionId: sid, revision: 1, reviewId: 'review-id-for-testing',
    confirmationToken: 'secret-confirmation-token', canConfirm,
    summary: {businessName: '<script>bad()</script>', category: 'fashion', planMonths: 3,
      template: 'classic', domain: {ownDomain: 'example.ir'}}};
  const location = {href: 'https://widget.example/widget/widget.html',
    origin: 'https://widget.example', hash: embedded ? '#parentOrigin=https%3A%2F%2Fwidget.example&channel=test' : ''};
  const windowListeners = {};
  const window = {addEventListener(type, cb) { windowListeners[type] = cb; }};
  window.parent = embedded ? {postMessage() {}} : window;
  const context = vm.createContext({
    URL, URLSearchParams, AbortController, setTimeout, clearTimeout, location, window,
    crypto: require('node:crypto').webcrypto,
    matchMedia: () => ({matches: false, addEventListener() {}}),
    ResizeObserver: class {observe() {}},
    document: {getElementById: get, documentElement: {dataset: {}}, addEventListener() {},
      querySelectorAll: () => [], querySelector: () => new Element(),
      createTextNode: textContent => ({textContent}), createElement: () => new Element(), createElementNS: () => new Element()},
    fetch: async (url, options) => {
      assert.ok(url.startsWith('/') && !url.startsWith('//'), 'fetch must use a relative URL');
      const body = options.body === undefined ? undefined : JSON.parse(options.body);
      calls.push({url, body, headers: options.headers});
      let data;
      if (url === '/api/sessions') {
        if (failSession) throw new TypeError('offline');
        data = {sessionId: sid, sessionToken: token, revision: 0};
      } else {
        assert.equal(options.headers['X-Session-Token'], token);
        assert.ok(!(JSON.stringify(body) || '').includes(token));
        if (url === '/api/chat') {
          assert.equal(body.sessionId, sid);
          if (chatError) {
            const code = chatError;
            chatError = null;
            if (code === 'offline') throw new TypeError('response lost');
            return {ok: false, status: 410, json: async () => ({detail: {code}})};
          }
          revision++;
          data = {reply, sessionId: sid, revision,
            nextAction: 'review'};
        } else if (url.endsWith('/review')) {
          if (failReview) throw new TypeError('review response lost after server invalidated previous review');
          data = {...review, revision};
        } else if (url.endsWith('/confirm')) {
          if (rejectConfirm) return {ok: false, status: 410,
            json: async () => ({detail: {code: 'review_expired', message: 'private-detail'}})};
          if (failConfirm) throw new TypeError('response lost');
          if (releaseConfirm) await new Promise(resolve => { releaseConfirm.resolve = resolve; });
          data = {status: 'draft', ref: 'sd_testdraft',
            confirmUrl: 'https://launcho.ir/start?signup=sd_testdraft'};
        } else assert.fail(`Unexpected endpoint ${url}`);
      }
      return {ok: true, json: async () => data};
    },
  });
  const modules = new Map();
  async function load(name) {
    if (modules.has(name)) return modules.get(name);
    const module = new vm.SourceTextModule(readFileSync(resolve(__dirname, '../frontend', name), 'utf8'), {context});
    modules.set(name, module);
    await module.link(specifier => {
      if (specifier.split('?')[0] === './workflow.js') {
        return new vm.SyntheticModule(['configureWorkflow','startWorkflow','workflowActive','selectWorkflowTemplate'], function () {
          this.setExport('configureWorkflow', () => {});
          this.setExport('startWorkflow', () => {});
          this.setExport('workflowActive', () => false);
          this.setExport('selectWorkflowTemplate', () => {});
        }, {context});
      }
      return load(specifier.replace('./', '').split('?')[0]);
    });
    return module;
  }
  const module = await load('widget.js');
  await module.evaluate();
  const settle = () => new Promise(resolve => setImmediate(resolve));
  await settle();
  return {get, calls, settle, window, windowListeners,
    relativeUrl: modules.get('api.js').namespace.relativeUrl,
    failChat: code => { chatError = code; },
    failReview: () => { failReview = true; },
    recoverSession: () => { failSession = false; },
    failConfirmation: () => { failConfirm = true; },
    rejectConfirmation: () => { rejectConfirm = true; },
    holdConfirmation: () => { failConfirm = false; releaseConfirm = {}; },
    releaseConfirmation: () => releaseConfirm.resolve(),
    async send(message = 'create a draft now') {
      get('message').value = message;
      await get('form').emit('submit'); await settle();
    },
  };
}

(async () => {
  const auditOnly = process.argv.includes('--audit');
  {
    const failures = [];
    const check = async (name, action) => {
      try { await action(); console.log(`PASS: ${name}`); }
      catch (error) { failures.push(name); console.error(`FAIL: ${name}: ${error.message}`); }
    };
    await check('relative URL cannot become an external protocol-relative URL', () => {
      // Checked below in a fresh runtime so session state cannot affect URLs.
      return widget().then(w => {
        for (const value of ['https://widget.example//outside.example/api/chat',
          '//outside.example/api/chat', 'javascript:alert(1)', 'https://outside.example/api/chat', '', null]) {
          assert.equal(w.relativeUrl(value), null);
        }
        assert.equal(w.relativeUrl('https://widget.example/api/chat'), '/api/chat');
      });
    });
    await check('typing preserves session initialization error and retry', async () => {
      const failed = await widget({sessionFailure: true});
      await failed.get('message').emit('input');
      assert.equal(failed.get('error').hidden, false);
      assert.equal(failed.get('retry').hidden, false);
    });
    await check('typing preserves guidance after unknown confirmation outcome', async () => {
      const w = await widget();
      await w.send(); await w.get('review-button').emit('click');
      w.failConfirmation(); await w.get('confirm').emit('click');
      await w.get('message').emit('input');
      assert.equal(w.get('error').hidden, false);
    });
    await check('failed review refresh cannot authorize an old review', async () => {
      const staleReview = await widget();
      await staleReview.send(); await staleReview.get('review-button').emit('click');
      staleReview.failReview(); await staleReview.get('review-button').emit('click');
      const count = staleReview.calls.length;
      await staleReview.get('confirm').emit('click');
      assert.equal(staleReview.calls.length, count);
      assert.equal(staleReview.get('session-review').hidden, true);
    });
    assert.deepEqual(failures, []);
    if (auditOnly) return;
  }
  const w = await widget();
  const linked = await widget({reply: '**https://launcho.ir/start**، https://launcho.ir/pricing. https://launcho.ir.evil.example/start'});
  await linked.send('\u200b\u200c\u202e\ufe0f');
  assert.equal(linked.calls.length, 1, 'invisible input must never reach chat');
  await linked.send('می‌روم');
  assert.equal(linked.calls.at(-1).body.message, 'می‌روم');
  const bubble = linked.get('messages').children.at(-1).children[1];
  const links = bubble.children.flatMap(node => [node, ...(node.children || [])]).filter(node => node.href);
  assert.deepEqual(links.map(node => node.href), ['https://launcho.ir/start', 'https://launcho.ir/pricing']);
  assert.ok(links.every(node => node.target === '_blank' && node.rel === 'noopener noreferrer'));
  assert.deepEqual(w.calls.map(c => c.url), ['/api/sessions']);
  await w.send();
  assert.equal(w.calls.length, 2, 'model response must never confirm or create a review');
  assert.equal(w.get('review-button').hidden, false);
  await w.get('review-button').emit('click');
  assert.equal(w.calls.length, 3, 'review must not create a draft');
  assert.equal(w.get('confirm').disabled, false);
  w.failConfirmation();
  await w.get('confirm').emit('click');
  const original = w.calls.at(-1).body;
  assert.deepEqual(original, {revision: 1, reviewId: 'review-id-for-testing',
    confirmationToken: 'secret-confirmation-token', confirmed: true});
  await w.send('edit while outcome is unknown');
  await w.get('review-button').emit('click');
  assert.equal(w.calls.length, 4, 'unknown outcome must block new chat and review');
  w.holdConfirmation();
  const pending = w.get('confirm').emit('click');
  await w.settle();
  assert.equal(w.get('confirm').disabled, true);
  await w.get('confirm').emit('click');
  assert.equal(w.calls.length, 5, 'concurrent confirm must be ignored');
  assert.deepEqual(w.calls.at(-1).body, original, 'manual retry must reuse exact confirmation');
  w.releaseConfirmation(); await pending;
  assert.equal(w.get('confirm').hidden, true);
  assert.equal(w.get('review-summary').children[0].href, 'https://launcho.ir/start?signup=sd_testdraft');

  const failed = await widget({sessionFailure: true});
  await failed.send();
  assert.equal(failed.calls.length, 1, 'session failure must block chat');
  failed.recoverSession(); await failed.get('retry').emit('click'); await failed.settle();
  await failed.send();
  assert.equal(failed.calls.at(-1).url, '/api/chat');

  const offline = await widget();
  offline.failChat('offline');
  await offline.send('keep my message');
  const originalRequest = offline.calls.at(-1).body;
  assert.match(originalRequest.requestId, /^[a-f0-9-]{36}$/);
  await offline.get('retry').emit('click');
  await offline.settle();
  assert.deepEqual(offline.calls.at(-1).body, originalRequest);
  assert.equal(offline.calls.filter(call => call.url === '/api/sessions').length, 1);
  assert.equal(JSON.stringify(offline.get('messages').children).split('keep my message').length, 2);

  offline.failChat('session_expired');
  await offline.send('continue after expiry');
  const [expired, newSession, retried] = offline.calls.slice(-3);
  assert.deepEqual([expired.url, newSession.url, retried.url], ['/api/chat', '/api/sessions', '/api/chat']);
  assert.equal(expired.body.requestId, retried.body.requestId);
  assert.match(JSON.stringify(offline.get('messages').children), /keep my message/);

  const readonly = await widget({canConfirm: false});
  await readonly.send(); await readonly.get('review-button').emit('click');
  await readonly.get('confirm').emit('click');
  assert.equal(readonly.get('confirm').disabled, true);
  assert.equal(readonly.calls.length, 3);

  const stale = await widget();
  await stale.send(); await stale.get('review-button').emit('click');
  stale.rejectConfirmation(); await stale.get('confirm').emit('click');
  assert.equal(stale.get('session-review').hidden, true);
  await stale.send('correct preferences');
  assert.equal(stale.calls.at(-1).url, '/api/chat', 'expired review must allow recovery');

  const embedded = await widget({embedded: true});
  assert.equal(embedded.calls.length, 0);
  const event = {source: embedded.window.parent, origin: 'https://widget.example',
    data: {scope: 'launcho', channel: 'test', type: 'configure', theme: 'light', apiUrl: '/api/chat', open: true}};
  await embedded.windowListeners.message(event); await embedded.settle();
  await embedded.windowListeners.message(event); await embedded.settle();
  assert.equal(embedded.calls.length, 1, 'reopening/configuring must reuse the in-memory session');
  console.log('PASS: session lifecycle, authentication, click-only confirmation, exact retry, concurrency, expiry, and read-only mode');
})().catch(error => { console.error(error); process.exitCode = 1; });
