// Controlled transport/storage tests; no model or production service.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const key = 'launcho:tab-session:v1:https://host.example';
const saved = {version:1, id:'saved-session', token:'owner-capability', pending:false};
const snapshot = {sessionId:saved.id, revision:4, preferences:{kind:'shop', businessName:'نمونه'},
  history:[{role:'user', content:'سلام'}, {role:'assistant', content:'درود'}],
  adapterMode:'local_mock', expiresAt:'2099-01-01T00:00:00Z'};
async function runtime({values = new Map(), broken = false, response = snapshot, error = null} = {}) {
  const calls = [];
  const storage = {
    getItem(k) { if (broken) throw new Error('blocked'); return values.get(k) ?? null; },
    setItem(k,v) { if (broken) throw new Error('quota'); values.set(k,v); },
    removeItem(k) { if (broken) throw new Error('blocked'); values.delete(k); },
  };
  const context = vm.createContext({URL, AbortController, setTimeout, clearTimeout,
    window:{sessionStorage:storage}, location:{href:'https://widget.example/widget/widget.html', origin:'https://widget.example'},
    fetch:async (url, options) => {
      calls.push({url, ...options, body:options.body && JSON.parse(options.body)});
      if (url === '/api/sessions') return {ok:true, json:async () => ({sessionId:'new-session', sessionToken:'new-token', revision:0})};
      if (error) return {ok:false, status:410, json:async () => ({detail:{code:error}})};
      return {ok:true, json:async () => response};
    }});
  const mod = new vm.SourceTextModule(fs.readFileSync('frontend/api.js','utf8'), {context});
  await mod.link(() => assert.fail('unexpected import')); await mod.evaluate();
  return {api:mod.namespace.createSessionApi(), calls, values};
}
(async () => {
  const values = new Map([[key, JSON.stringify(saved)]]);
  const restored = await runtime({values});
  restored.api.configureRecovery(true,'https://host.example');
  const s = await restored.api.start();
  assert.equal(s.revision,4); assert.equal(s.restored.preferences.businessName,'نمونه');
  assert.equal(restored.calls.length,1); assert.equal(restored.calls[0].method,'GET');
  assert.equal(restored.calls[0].headers['X-Session-Token'],saved.token);
  assert.deepEqual(JSON.parse(values.get(key)),saved, 'no history, revision, preferences or confirmation token persisted');
  await restored.api.confirm({revision:4, reviewId:'review',confirmationToken:'one-use-secret'});
  assert.equal(JSON.parse(values.get(key)).pending,true, 'marker persisted before potentially accepted mutation');
  assert.ok(!values.get(key).includes('one-use-secret'));
  restored.api.resolveConfirmation(); assert.equal(JSON.parse(values.get(key)).pending,false);

  for (const state of ['creating','unknown','rejected','awaiting']) {
    const w = await runtime({values:new Map([[key,JSON.stringify(saved)]]), response:{...snapshot,draftState:state}});
    w.api.configureRecovery(true,'https://host.example');
    const current = await w.api.start();
    assert.equal(current.confirmationUnresolved === true,['creating','unknown'].includes(state));
    assert.equal(w.calls.length,1); assert.equal(w.calls[0].method,'GET');
  }
  const interrupted = await runtime({values:new Map([[key,JSON.stringify({...saved,pending:true})]]),response:{...snapshot,draftState:'awaiting'}});
  interrupted.api.configureRecovery(true,'https://host.example');
  assert.equal((await interrupted.api.start()).confirmationUnresolved,true,'interrupted send stays locked without confirmation token');
  const completed = await runtime({values:new Map([[key,JSON.stringify({...saved,pending:true})]]),
    response:{...snapshot,draftState:'completed',draft:{status:'draft'}}});
  completed.api.configureRecovery(true,'https://host.example');
  assert.equal((await completed.api.start()).confirmationUnresolved,false);
  for (const pending of [false,true]) {
    const w = await runtime({values:new Map([[key,JSON.stringify({...saved,pending})]]),error:'session_expired'});
    w.api.configureRecovery(true,'https://host.example');
    if (pending) {
      await assert.rejects(w.api.start()); await assert.rejects(w.api.start());
      assert.equal(w.calls.length,2); assert.ok(w.calls.every(c => c.method === 'GET'));
    } else { await w.api.start(); assert.equal(w.calls.at(-1).url,'/api/sessions'); }
  }
  for (const response of [{...snapshot,sessionId:'wrong'}, {...snapshot,revision:-1},
    {...snapshot,history:[{role:'system',content:'bad'}]}, {...snapshot,expiresAt:'2000-01-01'},
    {...snapshot,draftState:'invented'}, {...snapshot,draftState:'completed'}]) {
    const w = await runtime({values:new Map([[key,JSON.stringify(saved)]]),response});
    w.api.configureRecovery(true,'https://host.example');
    await assert.rejects(w.api.start()); assert.equal(w.calls.length,1);
    assert.equal(w.calls[0].method,'GET','invalid authoritative state must not trigger replacement');
  }
  for (const opts of [{broken:true}, {values:new Map([[key,'{invalid']])}]) {
    const w = await runtime(opts); w.api.configureRecovery(true,'https://host.example');
    assert.equal((await w.api.start()).id,'new-session');
    assert.equal(w.api.storageAvailable,false);
  }
  const scoped = await runtime({values}); scoped.api.configureRecovery(true,'https://other-host.example');
  assert.equal((await scoped.api.start()).id,'new-session');
  const memory = await runtime({values});
  assert.equal((await memory.api.start()).id,'new-session','recovery remains explicit opt-in');
  console.log('PASS: opt-in recovery, authoritative state, scope, pending marker, expiry, invalid and blocked storage');
})().catch(error => {console.error(error); process.exitCode=1;});
