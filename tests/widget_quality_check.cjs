// Fail-fast controlled regression suite. Public previews require separate opt-in.
const {spawnSync} = require('node:child_process');
const path = require('node:path');
for (const args of [
  ['--experimental-vm-modules', 'tests/widget_session_test.cjs'],
  ['tests/widget_signup_browser.cjs'],
  ['tests/widget_sessions_browser.cjs'],
]) {
  const env = {...process.env};
  if (env.WIDGET_ARTIFACT_DIR) env.WIDGET_ARTIFACT_DIR = path.join(env.WIDGET_ARTIFACT_DIR, args[0].includes('signup') ? 'signup' : 'sessions');
  const result = spawnSync(process.execPath, args, {stdio:'inherit', windowsHide:true, env});
  if (result.error) { console.error(result.error.message); process.exit(1); }
  if (result.status !== 0) process.exit(result.status || 1);
}
console.log('PASS: all controlled widget quality checks; no production signup or model calls');
