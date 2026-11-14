// Public read-only previews; separate from the controlled widget/API tests.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const assert = require('node:assert/strict');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const root = path.resolve(__dirname, '..');
const rows = require('../content/launcho-widget-catalog.json').signupOptions.shop.templates;
const output = path.join(root, 'artifacts/widget-person3/public-previews');
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'launcho-previews-'));
const chrome = spawn(process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  ['--headless=new', '--disable-gpu', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  {windowsHide: true, stdio: 'ignore'});
let socket;
(async () => {
  fs.mkdirSync(output, {recursive: true});
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]; break; } catch { await sleep(100); }
  }
  assert.ok(port, 'Chrome must start');
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await once(socket, 'open');
  let id = 0;
  const pending = new Map();
  socket.addEventListener('message', event => {
    const data = JSON.parse(event.data);
    if (data.id) pending.get(data.id)?.(data);
  });
  const command = (method, params = {}) => new Promise((resolve, reject) => {
    const key = ++id;
    const timer = setTimeout(() => { pending.delete(key); reject(new Error(method + ' timeout')); }, 25000);
    pending.set(key, data => { pending.delete(key); clearTimeout(timer); data.error ? reject(new Error(data.error.message)) : resolve(data.result); });
    socket.send(JSON.stringify({id: key, method, params}));
  });
  const evaluate = async expression => {
    const result = await command('Runtime.evaluate', {expression, returnByValue: true});
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  };
  await command('Page.enable');
  await command('Emulation.setDeviceMetricsOverride', {width: 1280, height: 900, deviceScaleFactor: 1, mobile: false});
  const results = [];
  for (const row of rows) {
    try {
      const navigation = await command('Page.navigate', {url: row.previewUrl});
      if (navigation.errorText) throw new Error(navigation.errorText);
      let state;
      for (let i = 0; i < 100; i++) {
        await sleep(150);
        state = await evaluate(`({url:location.href, ready:document.readyState, title:document.title, text:document.body?.innerText.length||0, expectedLabelVisible:document.body?.innerText.includes(${JSON.stringify(row.label)})||false, images:[...document.images].filter(image=>image.complete&&image.naturalWidth>0).length, template:new URL(location.href).searchParams.get('template')})`);
        if (state.url === row.previewUrl && state.ready !== 'loading' && state.text > 100 && state.images > 0 && state.expectedLabelVisible) break;
      }
      const rendered = state.url === row.previewUrl && state.template === new URL(row.previewUrl).searchParams.get('template') && state.text > 100 && state.images > 0 && state.expectedLabelVisible;
      const shot = await command('Page.captureScreenshot', {format: 'png'});
      fs.writeFileSync(path.join(output, row.id + '.png'), Buffer.from(shot.data, 'base64'));
      results.push({id: row.id, result: rendered ? 'rendered' : 'unverified', ...state});
      console.log(`${rendered ? 'PASS' : 'UNVERIFIED'}: public preview ${row.id}`);
    } catch (error) { results.push({id: row.id, result: 'unverified', error: error.message}); }
  }
  const report = {browser: (await command('Browser.getVersion')).product,
    checkedAt: new Date().toISOString(), catalogSource: 'content/launcho-widget-catalog.json (test only)',
    note: 'Read-only public pages, visible text and loaded image smoke checks; not signup availability or visual equivalence.', results};
  fs.writeFileSync(path.join(root, 'docs/widget-person3/public-preview-browser.json'), JSON.stringify(report, null, 2) + '\n');
  if (results.some(row => row.result !== 'rendered')) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => { socket?.close(); chrome.kill(); });
