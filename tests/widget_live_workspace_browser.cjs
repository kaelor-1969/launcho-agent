// Checks the running local host and its real iframe/API. Never confirms a draft.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const host = process.env.WIDGET_HOST_URL || 'http://127.0.0.1:8001';
const reviewOnly = process.env.WIDGET_REVIEW_ONLY === '1';
const profile = fs.mkdtempSync(path.join(os.tmpdir(),'launcho-live-workspace-'));
const output = process.env.WIDGET_ARTIFACT_DIR ? path.resolve(process.env.WIDGET_ARTIFACT_DIR) : path.resolve(__dirname,'../artifacts/widget-connected-live');
fs.mkdirSync(output,{recursive:true});
const chrome = spawn(process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  ['--headless=new','--disable-gpu','--disable-background-timer-throttling','--disable-renderer-backgrounding','--no-first-run','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],
  {windowsHide:true,stdio:'ignore'});
let socket;
(async () => {
  let port;
  for(let i=0;i<100;i++) {
    try { port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]; break; } catch {}
    await sleep(50);
  }
  assert.ok(port);
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(targets.find(item=>item.type==='page').webSocketDebuggerUrl);
  await once(socket,'open');
  let id=0;
  const pending=new Map(), errors=[], calls=[], responses=[];
  socket.addEventListener('message',event=>{
    const data=JSON.parse(event.data);
    if(data.id) { const cb=pending.get(data.id); pending.delete(data.id); cb?.(data); }
    if(data.method==='Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);
    if(data.method==='Network.requestWillBeSent' && data.params.request.url.includes('/api/')) calls.push(data.params.request.url);
    if(data.method==='Network.responseReceived' && data.params.response.url.includes('/api/')) responses.push({url:data.params.response.url,status:data.params.response.status});
  });
  const command=(method,params={})=>new Promise((resolve,reject)=>{
    const key=++id;
    const timer=setTimeout(()=>{pending.delete(key);reject(new Error(method+' timed out'));},15000);
    pending.set(key,data=>{clearTimeout(timer);data.error ? reject(new Error(data.error.message)) : resolve(data.result);});
    socket.send(JSON.stringify({id:key,method,params}));
  });
  const evaluate=async (expression,contextId)=>{
    const result=await command('Runtime.evaluate',{expression,contextId,awaitPromise:true,returnByValue:true});
    if(result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  let widgetContextId;
  const wait=async fn=>{
    for(let i=0;i<150;i++){if(await fn())return;await sleep(100);}
    const state = widgetContextId ? await evaluate(`({error: document.querySelector('#error-text')?.textContent, signup: document.querySelector('#local-signup-status')?.textContent, invalid: Array.from(document.querySelectorAll('#local-signup :invalid')).map(el => el.name), fields: Array.from(document.querySelector('#local-signup').elements).map(el => ({name:el.name, value:el.value, disabled:el.disabled})), formHidden: document.querySelector('#local-signup')?.hidden, reviewHidden: document.querySelector('#session-review')?.hidden})`, widgetContextId) : null;
    throw new Error('Live widget condition timed out: ' + JSON.stringify({state, calls, responses, errors}));
  };
  await command('Runtime.enable'); await command('Network.enable');
  for(const width of [1280,390]) {
    await command('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:width<600});
    await command('Page.navigate',{url:host});
    await wait(()=>evaluate('!!window.LaunchoWidget'));
    const assetVersion = await evaluate(`new URL(document.querySelector('script[src*="/widget/loader.js"]').src).searchParams.get('v')`);
    // Asset fingerprinting belongs to the host; the widget also supports hosts
    // that install loader.js without a version query.
    if (assetVersion) assert.match(assetVersion, /^[A-Za-z0-9_-]+$/, 'host asset version is well formed');
    await evaluate('LaunchoWidget.open()');
    await wait(()=>evaluate(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.style.visibility==='visible'`));
    assert.equal(await evaluate(`document.querySelectorAll('#launcho-widget').length`),1);
    const tree=await command('Page.getFrameTree');
    const child=tree.frameTree.childFrames.find(item=>item.frame.url.includes('/widget/widget.html'));
    assert.ok(child,'main installation loads the actual widget');
    if (assetVersion) assert.equal(new URL(child.frame.url).searchParams.get('v'), assetVersion, 'iframe forwards the host asset version');
    const world=await command('Page.createIsolatedWorld',{frameId:child.frame.id,worldName:'live-widget-check'});
    widgetContextId=world.executionContextId;
    const chat=expr=>evaluate(expr,world.executionContextId);
    assert.equal(await chat(`document.body.dataset.interface`),'workspace');
    await wait(()=>chat(`!document.querySelector('#signup-save').disabled && !document.querySelector('#local-signup').hidden`));
    const shot=await command('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(output,`${width}-main.png`),Buffer.from(shot.data,'base64'));
    if (process.env.WIDGET_TYPING_ONLY === '1') {
      let paused;
      const pauseChat = event => {
        const data = JSON.parse(event.data);
        if (data.method === 'Fetch.requestPaused') paused = data.params.requestId;
      };
      socket.addEventListener('message', pauseChat);
      await command('Fetch.enable', {patterns:[{urlPattern:'*/api/chat',requestStage:'Request'}]});
      await chat(`document.querySelector('#message').value='لانچو چه امکاناتی دارد؟'; document.querySelector('#form').requestSubmit()`);
      await wait(async () => paused && await chat(`!document.querySelector('#waiting').hidden`));
      assert.equal(await chat(`document.querySelectorAll('#waiting .typing-dots i').length`),3);
      await wait(()=>chat(`document.querySelector('#waiting .typing-avatar img').naturalWidth>0`));
      assert.equal(await chat(`getComputedStyle(document.querySelector('#waiting .typing-dots i')).animationName`),'typing-dot');
      assert.ok(await chat(`(() => { const r=document.querySelector('#waiting').getBoundingClientRect(), area=document.querySelector('#scroll-area').getBoundingClientRect(); return r.top>=area.top && r.bottom<=area.bottom; })()`), 'typing indicator must be visible in the scroll viewport after signup cards');
      assert.ok(await chat(`(() => { const form=document.querySelector('#local-signup').getBoundingClientRect(), user=document.querySelector('#messages .role-user:last-child').getBoundingClientRect(), waiting=document.querySelector('#waiting').getBoundingClientRect(); return user.top>=form.bottom && waiting.top>=user.bottom; })()`), 'user message and typing indicator must appear together below the signup form');
      const typingShot=await command('Page.captureScreenshot',{format:'png'});
      fs.writeFileSync(path.join(output,`${width}-typing.png`),Buffer.from(typingShot.data,'base64'));
      await command('Fetch.continueRequest',{requestId:paused});
      await command('Fetch.disable');
      socket.removeEventListener('message',pauseChat);
      await wait(()=>chat(`document.querySelector('#waiting').hidden`));
      await wait(()=>chat(`!!document.querySelector('#messages .role-assistant')`));
      assert.ok(await chat(`(() => { const form=document.querySelector('#local-signup').getBoundingClientRect(), user=document.querySelector('#messages .role-user').getBoundingClientRect(), reply=document.querySelector('#messages .role-assistant').getBoundingClientRect(); return user.top>=form.bottom && reply.top>=user.bottom; })()`), 'assistant reply must follow the user in the same flow below the form');
      assert.equal(calls.filter(url=>url.endsWith('/confirm')).length,0);
      console.log(`PASS: ${width}px main host, thinking avatar, animated dots while API is pending, hidden after completion`);
      continue;
    }
    await chat(`document.querySelector('#local-signup [name=businessName]').value='retained draft'; document.querySelector('#desktop-services [data-service=human]').click()`);
    assert.equal(await chat(`document.querySelector('#assistant-content').hidden`),true);
    await chat(`document.querySelector('#desktop-services [data-service=assistant]').click()`);
    assert.equal(await chat(`document.querySelector('#local-signup [name=businessName]').value`),'retained draft');
    if (!reviewOnly) {
      await chat(`document.querySelector('#message').value='لانچو چه امکاناتی دارد؟'; document.querySelector('#form').requestSubmit()`);
      await wait(()=>chat(`document.querySelectorAll('#messages .role-assistant').length>0 && document.querySelector('#waiting').hidden`));
    }
    const history=await chat(`document.querySelector('#messages').textContent`);
    if (!reviewOnly) assert.ok(history.length>20);
    await evaluate('LaunchoWidget.close(); LaunchoWidget.open()');
    assert.equal(await chat(`document.querySelector('#messages').textContent`),history);
    for (const kind of ['shop', 'website']) {
      // Exercise the real preferences and review routes without authorizing creation.
      await chat(`(() => {
        const form = document.querySelector('#local-signup');
        form.elements.kind.value = '${kind}';
        form.elements.kind.dispatchEvent(new Event('change', {bubbles:true}));
      })()`);
      await wait(()=>chat(`!document.querySelector('#signup-save').disabled`));
      await chat(`(() => {
        const form = document.querySelector('#local-signup');
        form.elements.ownDomain.value = '';
        form.elements.ownDomain.dispatchEvent(new Event('input', {bubbles:true}));
        form.elements.businessName.value = 'آزمون ویجت';
        form.elements.label.value = 'widget-review';
        form.requestSubmit();
      })()`);
      await wait(()=>chat(`!document.querySelector('#session-review').hidden && !document.querySelector('#confirm').disabled`));
      assert.ok(await chat(`document.querySelector('#review-summary').textContent.includes('${kind === 'shop' ? 'فروشگاه' : 'سایت‌ساز'}')`));
      assert.equal(await chat(`document.querySelector('#local-signup').hidden`),true);
      await chat(`document.querySelector('#edit-signup').click()`);
      await wait(()=>chat(`!document.querySelector('#local-signup').hidden && !document.querySelector('#signup-save').disabled`));
      assert.equal(await chat(`document.querySelector('#local-signup').elements.businessName.value`),'آزمون ویجت');
      assert.equal(await chat(`document.querySelector('#confirm').disabled`),true);
      await chat(`(() => { const form=document.querySelector('#local-signup'); form.elements.businessName.value='نام ویرایش‌شده'; form.elements.ownDomain.value='owner.example.ir'; form.elements.ownDomain.dispatchEvent(new Event('input',{bubbles:true})); form.requestSubmit(); })()`);
      await wait(()=>chat(`!document.querySelector('#session-review').hidden && !document.querySelector('#confirm').disabled`));
      assert.ok(await chat(`document.querySelector('#review-summary').textContent.includes('نام ویرایش‌شده')`));
      assert.ok(await chat(`document.querySelector('#review-summary').textContent.includes('owner.example.ir')`));
      const reviewShot=await command('Page.captureScreenshot',{format:'png'});
      fs.writeFileSync(path.join(output,`${width}-${kind}-review.png`),Buffer.from(reviewShot.data,'base64'));
      await chat(`document.querySelector('#edit-signup').click()`);
      await wait(()=>chat(`!document.querySelector('#local-signup').hidden && !document.querySelector('#signup-save').disabled`));
      assert.equal(await chat(`document.querySelector('#local-signup').elements.ownDomain.value`),'owner.example.ir');
    }
    await chat(`document.querySelector('#confirm').click()`);
    assert.equal(calls.filter(url=>url.endsWith('/confirm')).length,0);
    if (reviewOnly) assert.equal(calls.filter(url=>url.endsWith('/api/chat')).length,0);
    if (process.env.WIDGET_TAB_RECOVERY === '1') {
      const sessionsBefore = calls.filter(url => url.endsWith('/api/sessions')).length;
      const reviewsBefore = calls.filter(url => url.endsWith('/review')).length;
      const preferencesBefore = calls.filter(url => url.endsWith('/preferences')).length;
      const readsBefore = calls.filter(url => /\/api\/sessions\/[^/]+$/.test(url)).length;
      const originalSessionUrl = calls.findLast(url => url.endsWith('/preferences')).replace(/\/preferences$/, '');
      await evaluate('window.beforeRecoveryReload=true');
      await command('Page.reload');await wait(()=>evaluate('!window.beforeRecoveryReload && !!window.LaunchoWidget'));
      await evaluate('LaunchoWidget.open()');
      await wait(()=>evaluate(`document.querySelector('#launcho-widget').shadowRoot.querySelector('iframe')?.style.visibility==='visible'`));
      const refreshedTree=await command('Page.getFrameTree');
      const refreshedChild=refreshedTree.frameTree.childFrames.find(item=>item.frame.url.includes('/widget/widget.html'));
      const refreshedWorld=await command('Page.createIsolatedWorld',{frameId:refreshedChild.frame.id,worldName:'recovered-widget-check'});
      const recovered=expression=>evaluate(expression,refreshedWorld.executionContextId);
      await wait(()=>recovered(`document.querySelector('[name=businessName]').value==='نام ویرایش‌شده' && !document.querySelector('#signup-save').disabled`));
      assert.equal(await recovered(`document.querySelector('[name=kind]').value`),'website');
      assert.equal(await recovered(`document.querySelector('[name=ownDomain]').value`),'owner.example.ir');
      assert.equal(await recovered(`document.querySelector('#confirm').disabled`),true);
      assert.equal(calls.filter(url=>url.endsWith('/api/sessions')).length,sessionsBefore);
      assert.equal(calls.filter(url=>url.endsWith('/review')).length,reviewsBefore);
      assert.equal(calls.filter(url=>url.endsWith('/preferences')).length,preferencesBefore);
      assert.equal(calls.filter(url=>/\/api\/sessions\/[^/]+$/.test(url)).length,readsBefore+1);
      assert.equal(calls.findLast(url=>/\/api\/sessions\/[^/]+$/.test(url)),originalSessionUrl,'recovery GET targets the original owner session');
      const recoveredShot=await command('Page.captureScreenshot',{format:'png'});
      fs.writeFileSync(path.join(output,`${width}-actual-recovery.png`),Buffer.from(recoveredShot.data,'base64'));
      console.log(`PASS: actual cross-origin tab recovery ${width}px, authoritative preferences, one GET and zero mutation replays`);
    }
    console.log(`PASS: running host ${host}, ${width}px, ${reviewOnly ? 'review-only/no chat API' : 'real chat'}, shop/website preferences, own domain, edits, Persian review, retained history, no confirmation`);
  }
  assert.deepEqual(errors,[]);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{socket?.close();chrome.kill();});
