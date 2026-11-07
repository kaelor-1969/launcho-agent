import { createWorkflowApi, validateView, validTemplate } from './workflow-api.js';

const root = document.getElementById('workflow');
let adapter, view, busy = false, started = false, lastRequest, draftKey;
let initializing;
let quoteTimer;
let notifyHost = () => {};
const money = n => new Intl.NumberFormat('fa-IR').format(n);
const domains = {unchecked:'بررسی‌نشده', checking:'در حال بررسی', available:'آزاد؛ هنوز ثبت یا رزرو نشده', unavailable:'غیرقابل انتخاب', error:'خطای بررسی'};
const element = (tag, content, cls) => {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (cls) node.className = cls;
  return node;
};
export async function configureWorkflow(options, notify) {
  notifyHost = notify;
  if (initializing) return initializing;
  if (adapter || started) return;
  if (options.demo === true) {
    initializing = import('./workflow-demo.js').then(({createDemoWorkflow}) => {
      adapter = createDemoWorkflow();
      const badge = element('p', 'حالت نمایشی — ساخت و پرداخت واقعی انجام نمی‌شود.', 'demo-badge');
      document.querySelector('.header').after(badge);
    });
    await initializing;
  } else adapter = createWorkflowApi(options.workflowUrl);
}
export function workflowActive() { return started; }
export async function startWorkflow() {
  started = true;
  document.querySelector('.starters').hidden = true;
  document.getElementById('form').hidden = true;
  root.hidden = false;
  if (!adapter) {
    root.replaceChildren(element('p', 'شروع ساخت فروشگاه فعلاً در دسترس نیست. کمی بعد دوباره تلاش کن.', 'flow-card'));
    return;
  }
  await request('start');
}
async function request(action, data = {}, retryPayload) {
  if (busy) return;
  if (action === 'createDraft' && view?.kind !== 'review') return;
  if (action === 'createDraft' && Date.parse(view.quote.expiresAt) <= Date.now()) {
    showFailure('اعتبار مبلغ تمام شده است. مبلغ تازه دریافت کن.', () => request('refreshQuote'));
    return;
  }
  if (action === 'pay' && (view?.kind !== 'payment' || Date.parse(view.quote.expiresAt) <= Date.now())) {
    showFailure('اعتبار مبلغ تمام شده است. مبلغ تازه دریافت کن.', () => request('refreshQuote'));
    return;
  }
  busy = true;
  const controls = Array.from(root.querySelectorAll('button,input,select'), n => [n,n.disabled]);
  controls.forEach(([n]) => n.disabled = true);
  const status = element('p', action === 'createDraft' ? 'در حال ساخت پیش‌نویس…' : action === 'checkDomain' ? 'در حال بررسی' : 'در حال نوشتن…', 'flow-status');
  status.setAttribute('role','status'); root.append(status);
  if (action === 'createDraft') draftKey ||= crypto.randomUUID();
  const payload = retryPayload || { action, data, sessionId: view?.sessionId ?? null, revision: view?.revision ?? null,
    ...(action === 'createDraft' ? {idempotencyKey: draftKey} : {}) };
  lastRequest = payload;
  try {
    const next = validateView(await adapter.request(payload));
    if (view && (next.sessionId !== view.sessionId || next.revision < view.revision)) throw new Error('پاسخ مربوط به این مرحله نیست.');
    if (next.kind === 'review' && action !== 'createDraft') draftKey = null;
    view = next;
    render();
  } catch (error) {
    status.remove();
    // A manual retry reuses the same idempotency key. Never replay automatically.
    controls.forEach(([n,disabled]) => n.disabled = disabled);
    showFailure(action === 'createDraft' ? 'پیش‌نویس ساخته نشد. دوباره تلاش کن.' : error.message,
      () => request(lastRequest.action, lastRequest.data, lastRequest));
  } finally { busy = false; }
}
function showFailure(message, retry) {
  root.querySelector('.flow-error')?.remove();
  const box = element('div', undefined, 'flow-error'); box.setAttribute('role','alert');
  box.append(element('p', message));
  const button = element('button', 'تلاش مجدد'); button.type = 'button'; button.onclick = retry;
  box.append(button); root.append(box);
}
function render() {
  clearTimeout(quoteTimer);
  const card = element('div', undefined, 'flow-card');
  const heading = element('h2', view.title); heading.tabIndex = -1; card.append(heading);
  if (view.description) card.append(element('p', view.description));
  if (view.checkoutUrl) {
    const link = element('a', 'ادامه در درگاه پرداخت');
    link.href = view.checkoutUrl; link.target='_blank'; link.rel='noopener noreferrer'; card.append(link);
  }
  if (view.domainStatus) {
    const status = element('p', domains[view.domainStatus]); status.setAttribute('role','status'); card.append(status);
  }
  if (view.template) {
    const image = document.createElement('img'); image.src = view.template.image; image.alt = view.template.name; image.referrerPolicy = 'no-referrer';
    card.append(image, element('p', view.template.name));
  }
  if (view.rows) {
    const rows = element('dl');
    for (const row of view.rows) { const value = element('dd', row.value); value.dir='auto'; rows.append(element('dt',row.label),value); }
    card.append(rows);
  }
  let field;
  if (view.kind === 'field') {
    const label = element('label', view.label || view.title); label.htmlFor = 'flow-value'; card.append(label);
    if (view.options) {
      field = element('select');
      for (const option of view.options) { const o = element('option', option.label); o.value = option.id; field.append(o); }
    } else {
      field = element('input'); field.type = 'text'; field.maxLength = view.field === 'mobile' ? 16 : 200;
      if (['mobile','domain'].includes(view.field)) field.dir='ltr';
      if (view.field === 'mobile') { field.type='tel'; field.inputMode='tel'; field.autocomplete='tel'; }
      if (view.field === 'domain') { field.inputMode='url'; field.autocomplete='off'; field.spellcheck=false; }
    }
    field.id='flow-value'; field.value=view.value || field.value || ''; card.append(field);
  }
  for (const action of view.actions) {
    const label = action.id === 'pay' && view.quote ? `پرداخت ${money(view.quote.today)} تومان` : action.label;
    const button = element('button', label, ['createDraft','next','pay'].includes(action.id) ? 'primary' : '');
    button.type='button'; button.dataset.action=action.id;
    button.disabled = action.disabled === true || (action.id === 'pay' && Date.parse(view.quote.expiresAt) <= Date.now());
    button.onclick = () => {
      if (busy) return;
      if (action.id === 'browseTemplates') { notifyHost('browse-templates'); return; }
      let value = field?.value.trim();
      if (field && ['next','checkDomain'].includes(action.id)) {
        if (view.field === 'mobile') {
          value = value.replace(/[۰-۹]/g, n => String(n.charCodeAt(0)-1776)).replace(/[٠-٩]/g, n => String(n.charCodeAt(0)-1632)).replace(/[\s-]/g,'');
          if (!/^09\d{9}$/.test(value)) { field.setCustomValidity('شماره موبایل ۱۱ رقمی با ۰۹ وارد کن.'); field.reportValidity(); return; }
        }
        if (!value) { field.setCustomValidity('این مورد را وارد کن.'); field.reportValidity(); return; }
        field.setCustomValidity('');
      }
      request(action.id, field ? {field:view.field, value} : {});
    };
    card.append(button);
  }
  if (field) field.addEventListener('input', () => {
    field.setCustomValidity('');
    if (view.field === 'domain') {
      const changed = field.value.trim() !== view.value;
      const next = card.querySelector('[data-action=next]');
      if (next) next.disabled = changed;
      const status = card.querySelector('[role=status]');
      if (status) status.textContent = changed ? domains.unchecked : domains[view.domainStatus];
    }
  });
  root.replaceChildren(card);
  if (view.kind === 'payment') {
    const remaining = Date.parse(view.quote.expiresAt) - Date.now();
    if (remaining > 0) quoteTimer = setTimeout(() => {
      const pay = card.querySelector('[data-action=pay]');
      if (pay) pay.disabled = true;
      const expired = element('p','اعتبار مبلغ تمام شده است. مبلغ تازه دریافت کن.');
      expired.setAttribute('role','status'); card.append(expired);
    }, Math.min(remaining,2147483647));
  }
  // Scroll only the message body. scrollIntoView would also scroll the host's
  // overflow-hidden animated frame and can move the header outside the viewport.
  const scrollArea = document.getElementById('scroll-area');
  scrollArea.scrollTop += heading.getBoundingClientRect().top - scrollArea.getBoundingClientRect().top - 16;
  heading.focus({preventScroll:true});
}
export function selectWorkflowTemplate(template) {
  if (!started || busy || view?.kind !== 'template' || !validTemplate(template)) return;
  request('selectTemplate', {template});
}
