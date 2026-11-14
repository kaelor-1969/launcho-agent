// Starts isolated local services and a separate-origin host; never calls chat/confirm.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
const output = path.resolve(process.env.WIDGET_ARTIFACT_DIR || 'artifacts/widget-person1/local-integration');
const scratch = fs.mkdtempSync(path.join(os.tmpdir(),'launcho-person1-local-'));
const python = process.env.WIDGET_PYTHON || path.resolve('.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const children=[];
let host;
async function freePort() {const probe=http.createServer();probe.listen(0,'127.0.0.1');await once(probe,'listening');const port=probe.address().port;await new Promise(resolve=>probe.close(resolve));return port;}
function launch(module,port,env) {
  const child=spawn(python,['-m','uvicorn',module,'--host','127.0.0.1','--port',String(port)],{env,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let log='';child.stdout.on('data',chunk=>{log=(log+chunk).slice(-6000);});child.stderr.on('data',chunk=>{log=(log+chunk).slice(-6000);});
  child.on('error',error=>{log=error.message;});children.push(child);return {child,log:()=>log};
}
async function ready(url,service) {
  for(let i=0;i<100;i++) {try {if((await fetch(url)).ok) return;}catch{}if(service.child.exitCode!==null) break;await sleep(100);}
  throw new Error('Local test service failed: '+service.log());
}
(async()=>{
  fs.mkdirSync(output,{recursive:true});assert.ok(fs.existsSync(python),'Set WIDGET_PYTHON to an environment with project dependencies');
  const mockPort=await freePort(),apiPort=await freePort(),hostPort=await freePort();
  const env={...process.env,PYTHONUTF8:'1',AI_API_KEY:' ',AI_MODEL_NAME:' ',AI_BASE_URL:'https://example.invalid/v1',
    LAUNCHO_API_URL:' ',LAUNCHO_API_KEY:' ',LAUNCHO_ENABLE_DRAFTS:'0',LAUNCHO_ENV:'development',
    LAUNCHO_FRAME_ANCESTORS:`http://127.0.0.1:${hostPort}`,LAUNCHO_CORS_ORIGINS:'',
    LAUNCHO_MOCK_URL:`http://127.0.0.1:${mockPort}`,LAUNCHO_MOCK_DB:path.join(scratch,'mock.sqlite3'),
    LAUNCHO_SESSION_DB:path.join(scratch,'sessions.sqlite3'),LAUNCHO_MOCK_DRAFT_CATALOG:'widget'};
  const mock=launch('app.mock_launcho:app',mockPort,env);await ready(`http://127.0.0.1:${mockPort}/`,mock);
  const api=launch('app.main:app',apiPort,env);await ready(`http://127.0.0.1:${apiPort}/health/live`,api);
  host=http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
    res.end(`<!doctype html><html lang="fa" dir="rtl"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local integration only</title><script defer src="http://127.0.0.1:${apiPort}/widget/loader.js" data-auto-open="false" data-session-recovery="tab"></script></html>`);});
  host.listen(hostPort,'127.0.0.1');await once(host,'listening');
  const test=spawn(process.execPath,['tests/widget_live_workspace_browser.cjs'],{windowsHide:true,env:{...process.env,
    WIDGET_HOST_URL:`http://127.0.0.1:${host.address().port}`,WIDGET_REVIEW_ONLY:'1',WIDGET_TAB_RECOVERY:'1',WIDGET_ARTIFACT_DIR:output},stdio:['ignore','pipe','pipe']});
  children.push(test);let result='';for(const stream of [test.stdout,test.stderr]) stream.on('data',chunk=>{result+=chunk;process.stdout.write(chunk);});
  const [code]=await once(test,'exit');assert.equal(code,0,'local browser integration failed');
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({localServices:true,separateHostOrigin:true,
    testCatalogOnly:true,realProduction:false,chatRequests:0,confirmRequests:0,tabRecovery:true,result},null,2)+'\n');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  host?.closeAllConnections();host?.close();
  for(const child of children) {if(child.exitCode===null) {child.kill();await Promise.race([once(child,'exit'),sleep(3000)]);}}
  // Temporary databases retained for OS-managed cleanup; no computed recursive deletion.
});
