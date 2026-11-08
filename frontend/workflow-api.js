import { relativeUrl } from './api.js';
// Proposed structured adapter. No guessed endpoint, pricing or production fallback.
export function safeUrl(value) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
// This release permits only the bundled static demo, at its exact module-relative
// URL. Real draft destinations require a separately reviewed allowlist.
const demoDraftUrl = new URL('./draft-preview.html', import.meta.url).href;
export function safeDraftUrl(value) {
  return value === demoDraftUrl && safeUrl(value) ? demoDraftUrl : null;
}
const text = (v, max = 5000) => typeof v === 'string' && v.length > 0 && v.length <= max;
const fields = ['businessName', 'category', 'subscription'];
const actions = new Set(['next', 'browseTemplates', 'edit', 'createDraft',
  ...[...fields, 'template'].map(field => `edit:${field}`)]);
export function validTemplate(t) {
  return t && text(t.id, 200) && text(t.name, 200) && safeUrl(t.image);
}
export function validateView(v) {
  if (!v || !text(v.sessionId, 200) || !Number.isSafeInteger(v.revision) || v.revision < 0 || !text(v.title) ||
      !['field', 'template', 'review', 'draft'].includes(v.kind) ||
      !Array.isArray(v.actions) || v.actions.length > 20 ||
      !v.actions.every(a => a && actions.has(a.id) && text(a.label, 200)) ||
      (v.rows !== undefined && (!Array.isArray(v.rows) || !v.rows.every(r => r && text(r.label, 200) && typeof r.value === 'string'))) ||
      (v.template !== undefined && !validTemplate(v.template))) throw new Error('پاسخ معتبر نیست. دوباره تلاش کن.');
  if (['mobile', 'setupPayment', 'domain', 'domainStatus', 'quote', 'checkoutUrl', 'transactionId', 'paymentStatus', 'verified'].some(key => key in v)) throw new Error('این اطلاعات خارج از محدودهٔ دستیار است.');
  if (v.kind === 'field' && (!fields.includes(v.field) ||
      (v.options !== undefined && (!Array.isArray(v.options) || !v.options.every(o => o && text(o.id,200) && text(o.label,200)))))) throw new Error('پاسخ معتبر نیست.');
  if (v.actions.some(a => a.id === 'createDraft') && v.kind !== 'review') throw new Error('اطلاعات مرور کامل نیست.');
  if (v.kind === 'draft' && (!text(v.draftId,200) || v.confirmed !== true || !safeDraftUrl(v.draftUrl))) throw new Error('پیش‌نویس یا لینک آن معتبر نیست.');
  if (v.kind !== 'draft' && v.draftUrl !== undefined) throw new Error('لینک پیش‌نویس فقط پس از تأیید نمایش داده می‌شود.');
  return v;
}
export function createWorkflowApi(url) {
  if (typeof url !== 'string' || !relativeUrl(url)) return null;
  url = relativeUrl(url);
  return { async request(payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch(url, { method: 'POST', credentials: 'omit', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload), signal: controller.signal });
      if (!response.ok) throw new Error('درخواست انجام نشد. دوباره تلاش کن.');
      return validateView(await response.json());
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('پاسخ به‌موقع دریافت نشد. پیش از اقدام دوباره، وضعیت درخواست را بررسی کن.');
      if (error instanceof TypeError) throw new Error('اتصال برقرار نشد. دوباره تلاش کن.');
      if (error instanceof SyntaxError) throw new Error('پاسخ معتبر نیست. دوباره تلاش کن.');
      throw error;
    } finally { clearTimeout(timer); }
  }};
}
