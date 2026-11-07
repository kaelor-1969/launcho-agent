// Proposed structured adapter. No guessed endpoint, pricing or production fallback.
export function safeUrl(value) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
const text = (v, max = 5000) => typeof v === 'string' && v.length > 0 && v.length <= max;
export function validTemplate(t) {
  return t && text(t.id, 200) && text(t.name, 200) && safeUrl(t.image);
}
export function validateView(v) {
  if (!v || !text(v.sessionId, 200) || !Number.isSafeInteger(v.revision) || v.revision < 0 || !text(v.title) ||
      !['field', 'template', 'review', 'draft', 'payment', 'result'].includes(v.kind) ||
      !Array.isArray(v.actions) || v.actions.length > 20 ||
      !v.actions.every(a => a && text(a.id, 200) && text(a.label, 200)) ||
      (v.rows !== undefined && (!Array.isArray(v.rows) || !v.rows.every(r => r && text(r.label, 200) && typeof r.value === 'string'))) ||
      (v.template !== undefined && !validTemplate(v.template))) throw new Error('پاسخ معتبر نیست. دوباره تلاش کن.');
  if (v.kind === 'field' && (!['businessName', 'category', 'domain', 'mobile', 'subscription', 'setupPayment'].includes(v.field) ||
      (v.options !== undefined && (!Array.isArray(v.options) || !v.options.every(o => o && text(o.id,200) && text(o.label,200)))))) throw new Error('پاسخ معتبر نیست.');
  if (v.quote !== undefined && (!v.quote || v.quote.currency !== 'TOMAN' || !text(v.quote.id,200) || !Number.isSafeInteger(v.quote.today) || v.quote.today < 0 || !Number.isFinite(Date.parse(v.quote.expiresAt)))) throw new Error('مبلغ معتبر دریافت نشد.');
  if (v.kind === 'payment' && !v.quote) throw new Error('مبلغ معتبر دریافت نشد.');
  if (v.actions.some(a => a.id === 'createDraft') && (v.kind !== 'review' || !v.quote)) throw new Error('اطلاعات مرور کامل نیست.');
  if (v.paymentStatus !== undefined && !['success', 'failed', 'cancelled', 'unknown'].includes(v.paymentStatus)) throw new Error('وضعیت معتبر نیست.');
  if (v.paymentStatus === 'success' && v.verified !== true) throw new Error('پرداخت هنوز تأیید نشده است.');
  if (v.checkoutUrl !== undefined && (!safeUrl(v.checkoutUrl) || !v.checkoutUrl.startsWith('https://') || !text(v.transactionId,200))) throw new Error('لینک پرداخت معتبر نیست.');
  if (v.kind === 'draft' && (!text(v.draftId,200) || v.confirmed !== true)) throw new Error('ساخت پیش‌نویس تأیید نشده است.');
  if (v.domainStatus !== undefined && !['unchecked','checking','available','unavailable','error'].includes(v.domainStatus)) throw new Error('وضعیت دامنه معتبر نیست.');
  if (v.kind === 'result' && v.paymentStatus === 'unknown' && v.actions.some(a => a.id === 'pay')) throw new Error('ابتدا وضعیت تراکنش باید بررسی شود.');
  return v;
}
export function createWorkflowApi(url) {
  if (!safeUrl(url)) return null;
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
