// Native Chromium, controlled HTTP only; never calls a model or production API.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
const root = path.resolve(__dirname,'../frontend');
const output = path.resolve(process.env.WIDGET_ARTIFACT_DIR || 'artifacts/widget-person1/recovery');
const catalog = JSON.parse(fs.readFileSync('content/launcho-widget-catalog.json','utf8')).signupOptions;
const pricing = JSON.parse(fs.readFileSync('content/launcho-mock.json','utf8')).pricing;
const sid = 'recovery-browser-session', token = 'recovery-owner-token';
const calls = [];
let draftState, status = 'draft', failRead = false, failStatus = false, delayOptions = false, obsoleteOptionsFailure = false;
const prefs = {kind:'shop',businessName:'نمونهٔ بازیابی',category:catalog.shop.businessCategories[0].id,
  template:catalog.shop.templates.find(t => t.available).id,planMonths:3,domain:{ownDomain:'example.ir'}};
const draft = {ref:'sd_recovery',status:'draft',expiresAt:'2099-01-01T00:00:00Z',
  confirmUrl:'/api/local-drafts/sd_recovery/preview'};
const server = http.createServer(async (req,res) => {
  const json = (body,code=200) => {res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
  if (req.url.startsWith('/api/')) {
    let raw=''; for await (const chunk of req) raw+=chunk;
    calls.push({url:req.url,method:req.method,body:raw && JSON.parse(raw),token:req.headers['x-session-token']});
    if (req.url === '/api/sessions') return json({sessionId:sid,sessionToken:token,revision:0,adapterMode:'local_mock'});
    if (req.url.startsWith('/api/local-signup-options?')) {
      const kind = new URL(req.url,'http://localhost').searchParams.get('kind');
      if (delayOptions) await sleep(kind === 'website' ? 250 : 20);
      if (obsoleteOptionsFailure && kind === 'website') return json({detail:{code:'options_unavailable'}},503);
      return json({...catalog[kind],periods:pricing.plans.map(x=>x.months),suffixes:pricing.domains.map(x=>x.tld)});
    }
    assert.equal(req.headers['x-session-token'],token);
    if (req.url === '/api/sessions/'+sid) {
      if (failRead) return json({detail:{code:'session_expired'}},410);
      return json({sessionId:sid,revision:4,expiresAt:'2099-01-01T00:00:00Z',preferences:prefs,
        history:[{role:'user',content:'پیام پیش از تازه‌سازی'},{role:'assistant',content:'پاسخ معتبر سرور'}],
        adapterMode:'local_mock',draftState,...(draftState==='completed'?{draft}:{})});
    }
    if (req.url.endsWith('/draft-status')) return failStatus ? json({status:'untrusted'}) : json({status});
    if (req.url === '/api/chat') {
      await sleep(150);
      return json({sessionId:sid,revision:4,reply:'پاسخ معتبر سرور',nextAction:'collect_preferences'});
    }
    return json({},404);
  }
  if (req.url === '/') {
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
    return res.end('<!doctype html><html lang="fa" dir="rtl"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Controlled recovery host</title><body><script defer src="/widget/loader.js" data-session-recovery="tab" data-auto-open="false"></script></body></html>');
  }
  const file = path.resolve(root,decodeURIComponent(req.url.split('?')[0]).replace(/^\/widget\//,''));
  if (!file.startsWith(root+path.sep) || !fs.existsSync(file)) {res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',({'.js':'text/javascript','.html':'text/html','.css':'text/css','.woff2':'font/woff2'})[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});
(async () => {
  fs.mkdirSync(output,{recursive:true}); server.listen(0,'127.0.0.1'); await once(server,'listening');
  const base = 'http://127.0.0.1:'+server.address().port;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(),'launcho-recovery-'));
  const chrome = spawn(process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],
    {windowsHide:true,stdio:'ignore'});
  let socket;
  try {
    let port; for(let i=0;i<100;i++) {try {port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;} catch {await sleep(100);}}
    assert.ok(port,'browser did not start');
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    socket = new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);await once(socket,'open');
    let id=0;const pending=new Map(),errors=[];
    socket.addEventListener('message',e=>{const data=JSON.parse(e.data);if(data.id) {const cb=pending.get(data.id);pending.delete(data.id);cb?.(data);}
      if(data.method==='Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);});
    const command=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;
      const timer=setTimeout(()=>{pending.delete(key);reject(new Error('CDP timeout '+method));},10000);
      pending.set(key,data=>{clearTimeout(timer);data.error?reject(new Error(data.error.message)):resolve(data.result);});
      socket.send(JSON.stringify({id:key,method,params}));});
    const evaluate=async expression=>{const r=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
      if(r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
    const wait=async expression=>{for(let i=0;i<160;i++){if(await evaluate(expression)) return;await sleep(50);}throw new Error('Timed out '+expression);};
    const shot=async name=>{const r=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(r.data,'base64'));};
    const open=async()=>{
      await wait('!!window.LaunchoWidget');await evaluate('LaunchoWidget.open()');
      await wait(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.contentDocument?.querySelector('#message')`);
      await evaluate(`window.frame=document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe');window.doc=frame.contentDocument`);
      await wait(`frame.style.visibility==='visible'`);
    };
    const reload=async()=>{await evaluate('window.oldPage=true');await command('Page.reload');await wait('!window.oldPage');await open();};
    await command('Page.enable');await command('Runtime.enable');await command('Network.enable');
    await command('Page.navigate',{url:base});await open();await wait(`!doc.querySelector('.primary-starter').disabled`);
    assert.equal(calls.filter(c=>c.url==='/api/sessions').length,1);
    await reload();await wait(`doc.querySelector('[name=businessName]').value==='نمونهٔ بازیابی' && !doc.querySelector('#signup-save').disabled`);
    assert.equal(calls.filter(c=>c.url==='/api/sessions').length,1,'refresh must restore instead of creating another session');
    assert.equal(await evaluate(`doc.querySelector('[name=ownDomain]').value`),'example.ir');
    assert.match(await evaluate(`doc.querySelector('#messages').textContent`),/پاسخ معتبر سرور/);
    assert.equal(calls.filter(c=>c.method==='POST' && c.url!=='/api/sessions').length,0,'restoration is read-only');
    await shot('restored-preferences');
    // Reloading only the iframe must use the same tab capability too.
    await evaluate(`frame.contentWindow.location.reload()`);await wait(`frame.contentDocument!==doc && frame.contentDocument?.querySelector('#message')`);
    await evaluate('window.doc=frame.contentDocument');await wait(`doc.querySelector('#messages').textContent.includes('پاسخ معتبر سرور') && !doc.querySelector('#signup-save').disabled`);
    const question = await evaluate(`(() => {const b=doc.querySelectorAll('[data-question]')[1];b.focus();return b.dataset.question;})()`);
    const beforeQuestion = calls.length;
    await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
    await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await evaluate(`doc.querySelectorAll('[data-question]')[1].click();doc.querySelectorAll('[data-question]')[1].click();doc.querySelector('#message').value='overlapping form';doc.querySelector('#form').requestSubmit()`);
    await wait(`!doc.querySelectorAll('[data-question]')[1].disabled`);
    const questionCalls = calls.slice(beforeQuestion);
    assert.equal(questionCalls.length,1,'question activation sends exactly one action');
    assert.equal(questionCalls[0].url,'/api/chat');assert.equal(questionCalls[0].body.message,question);
    assert.match(questionCalls[0].body.requestId,/^[a-f0-9-]{36}$/);
    const beforeOptions = calls.length;
    delayOptions=true;
    for (const failObsolete of [false,true]) {
    obsoleteOptionsFailure=failObsolete;
    await evaluate(`(() => {const k=doc.querySelector('[name=kind]');k.value='website';k.dispatchEvent(new Event('change',{bubbles:true}));k.value='shop';k.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await wait(`!doc.querySelector('#signup-save').disabled`);await sleep(300);
    assert.equal(await evaluate(`doc.querySelector('[name=kind]').value`),'shop');
    assert.deepEqual(await evaluate(`Array.from(doc.querySelector('[name=template]').options).map(o=>o.value)`),catalog.shop.templates.filter(t=>t.available).map(t=>t.id));
    assert.equal(await evaluate(`doc.querySelector('#local-signup-status').textContent`),'','obsolete failure cannot overwrite latest successful options');
    }
    assert.ok(calls.slice(beforeOptions).every(c=>c.method==='GET'),'choice changes must not save/review/confirm automatically');
    delayOptions=false;obsoleteOptionsFailure=false;
    for(const state of ['creating','unknown']) {
      draftState=state;await reload();await wait(`!doc.querySelector('#retry').hidden && !doc.querySelector('#retry').disabled`);
      assert.equal(await evaluate(`doc.querySelector('#signup-save').disabled`),true);
      const before=calls.length;
      await evaluate(`doc.querySelector('#message').value='نباید ارسال شود';doc.querySelector('#form').requestSubmit();doc.querySelector('#local-signup').dispatchEvent(new Event('submit',{cancelable:true}));doc.querySelector('#review-button').click()`);
      await sleep(100);assert.equal(calls.length,before,'unknown state locks all mutation handlers');
      await evaluate(`doc.querySelector('#retry').click()`);await wait(`!doc.querySelector('#retry').disabled`);
      assert.equal(calls.at(-1).method,'GET');await shot('recovery-'+state);
    }
    failRead=true;await reload();await wait(`!doc.querySelector('#retry').hidden && !doc.querySelector('#retry').disabled`);
    assert.equal(calls.filter(c=>c.url==='/api/sessions').length,1,'expired unresolved owner cannot create replacement');
    failRead=false;draftState='completed';await evaluate(`doc.querySelector('#retry').click()`);
    await wait(`!!doc.querySelector('#review-summary a[href]')`);
    assert.equal(calls.at(-1).url,'/api/sessions/'+sid+'/draft-status');
    assert.equal(await evaluate(`doc.querySelector('#confirm').hidden`),true);
    await shot('recovered-completed');
    status='expired';await reload();await wait(`doc.querySelector('#review-summary a')?.getAttribute('aria-disabled')==='true'`);
    await shot('recovered-expired');
    failStatus=true;await reload();await wait(`!doc.querySelector('#retry').hidden && !doc.querySelector('#retry').disabled`);
    assert.equal(await evaluate(`!!doc.querySelector('#review-summary a[href]')`),false,'invalid status must not expose continuation');
    const beforeOffline=calls.length;
    await command('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:-1,uploadThroughput:-1});
    await wait(`!doc.querySelector('#network-status').hidden`);
    await evaluate(`doc.querySelector('#retry').click()`);await wait(`!doc.querySelector('#retry').disabled`);
    assert.equal(calls.length,beforeOffline,'offline recovery GET cannot reach server');
    await shot('recovery-offline');
    await command('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
    await wait(`doc.querySelector('#network-status').hidden`);await sleep(100);
    assert.equal(calls.length,beforeOffline,'online event never retries automatically');
    failStatus=false;await evaluate(`doc.querySelector('#retry').click()`);
    await wait(`doc.querySelector('#review-summary a')?.getAttribute('aria-disabled')==='true'`);
    assert.equal(calls.filter(c=>c.url.endsWith('/confirm')).length,0,'no recovery path may confirm');
    assert.deepEqual(errors,[]);
    const browser=await command('Browser.getVersion');
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({browser:browser.product,controlledResponses:true,
      restoredPreferences:true,hostRefresh:true,iframeRefresh:true,unknownLocked:true,expiredPendingNoReplacement:true,
      keyboardQuestionExactlyOnce:true,lateOptionsIgnored:true,choicesReadOnly:true,
      completedReadBeforeLink:true,expiredDisabled:true,malformedStatusBlocked:true,offlineRecovery:true,reconnectNoMutation:true,confirmRequests:0,errors},null,2)+'\n');
    console.log('PASS: native browser opt-in host/iframe refresh, preferences/history, unknown locks, expiry and GET-only recovery');
  } finally {socket?.close();chrome.kill();server.closeAllConnections();server.close();}
})().catch(error=>{console.error(error);server.closeAllConnections();server.close();process.exitCode=1;});
