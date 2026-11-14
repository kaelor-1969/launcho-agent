// Read-only public preview audit. HTTP availability does not prove registration availability.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'content/launcho-mock.json'), 'utf8'));
const evidence = JSON.parse(fs.readFileSync(path.join(root, 'content/public-template-evidence.json'), 'utf8'));
const rows = fixture.signupOptions.shop.templates;
const visible = evidence.samples.filter(row => !row.hidden);
assert.equal(rows.length, 23, 'shop fixture must contain the expected 23 public samples');
assert.equal(new Set(rows.map(row => row.id)).size, rows.length);
assert.deepEqual(rows.map(row => row.previewUrl).sort(), visible.filter(row => row.demoHref).map(row => row.demoHref).sort());
const results = [];
let next = 0;
async function worker() {
  while (next < rows.length) {
    const row = rows[next++];
    const url = new URL(row.previewUrl);
    assert.equal(url.origin, 'https://demo.launcho.ir');
    try {
      const response = await fetch(url, {signal: AbortSignal.timeout(20000), redirect: 'follow'});
      const html = await response.text();
      results.push({id: row.id, label: row.label, url: url.href, http: response.status,
        finalUrl: response.url, title: html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? null,
        result: response.ok ? 'reachable' : 'http-error', registration: 'unverified'});
    } catch (error) {
      results.push({id: row.id, label: row.label, url: url.href, result: 'unverified',
        error: error.cause?.code || error.name, registration: 'unverified'});
    }
  }
}
(async () => {
  await Promise.all(Array.from({length: 4}, worker));
  results.sort((a, b) => a.id.localeCompare(b.id));
  const report = {checkedAt: new Date().toISOString(), shopCount: rows.length,
    publicVisibleCount: visible.length, publicHiddenCount: evidence.samples.length - visible.length,
    missingPublicPreviews: visible.filter(row => !row.demoHref).map(row => ({id: row.id, title: row.title})),
    websiteTemplates: fixture.signupOptions.website.templates.map(row => ({id: row.id, hasPreview: !!row.previewUrl})),
    note: 'HTTP only; template rendering and official signup availability are unverified.', results};
  const output = path.join(root, 'docs/widget-person3/catalog-audit.json');
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({shop: rows.length, visible: visible.length, hidden: report.publicHiddenCount,
    reachable: results.filter(row => row.result === 'reachable').length,
    httpErrors: results.filter(row => row.result === 'http-error').length,
    unverified: results.filter(row => row.result === 'unverified').length, output}));
})().catch(error => { console.error(error); process.exitCode = 1; });
