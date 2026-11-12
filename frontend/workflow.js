import { createWorkflowApi, validateView, validTemplate } from './workflow-api.js?v=3';

const root = document.getElementById('workflow');
let adapter, view, busy = false, started = false, lastRequest, draftKey;
let initializing;
let demoFactory;
let notifyHost = () => {};
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
    initializing = import('./workflow-demo.js?v=3').then(({createDemoWorkflow}) => {
      demoFactory = createDemoWorkflow;
      adapter = createDemoWorkflow();
      const badge = element('p', 'حالت نمایشی', 'demo-badge');
      document.querySelector('.header').after(badge);
      const leave = document.getElementById('leave-workflow');
      leave.addEventListener('click', () => {
        if (busy) return;
        started = false;
        view = lastRequest = draftKey = null;
        adapter = demoFactory();
        root.replaceChildren();
        root.hidden = true;
        leave.hidden = true;
        document.querySelector('.starters').hidden = false;
        document.getElementById('form').hidden = false;
        document.getElementById('message').focus();
      });
    });
    await initializing;
  } else adapter = createWorkflowApi(options.workflowUrl);
}
export function workflowActive() { return started; }
export async function startWorkflow() {
  if (started) return;
  started = true;
  document.querySelector('.starters').hidden = true;
  document.getElementById('form').hidden = true;
  root.hidden = false;
  if (demoFactory) document.getElementById('leave-workflow').hidden = false;
  if (!adapter) {
    root.replaceChildren(element('p', 'شروع ساخت فروشگاه فعلاً در دسترس نیست. کمی بعد دوباره تلاش کن.', 'flow-card'));
    return;
  }
  await request('start');
}
async function request(action, data = {}, retryPayload) {
  if (busy) return;
  if (action === 'createDraft' && view?.kind !== 'review') return;
  busy = true;
  const controls = Array.from(root.querySelectorAll('button,input,select'), n => [n,n.disabled]);
  controls.forEach(([n]) => n.disabled = true);
  const status = element('p', action === 'createDraft' ? 'در حال آماده‌سازی پیش‌نویس…' : 'در حال نوشتن…', 'flow-status');
  status.setAttribute('role','status'); root.append(status);
  if (action === 'createDraft') draftKey ||= crypto.randomUUID();
  const payload = retryPayload || { action, data, sessionId: view?.sessionId ?? null, revision: view?.revision ?? null,
    ...(action === 'createDraft' ? {idempotencyKey: draftKey} : {}) };
  lastRequest = payload;
  try {
    const next = validateView(await adapter.request(payload), {demo: Boolean(demoFactory)});
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
  const card = element('div', undefined, 'flow-card');
  const heading = element('h2', view.title); heading.tabIndex = -1; card.append(heading);
  if (view.description) card.append(element('p', view.description));
  if (view.kind === 'draft') {
    const link = element('a', 'مشاهده نمونهٔ پیش‌نویس (نمایشی)');
    link.href = view.draftUrl; link.target = '_blank'; link.rel = 'noopener noreferrer';
    card.append(link);
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
      if (demoFactory) {
        const placeholder = element('option', 'انتخاب کن');
        placeholder.value = '';
        placeholder.disabled = true;
        field.append(placeholder);
      }
      for (const option of view.options) { const o = element('option', option.label); o.value = option.id; field.append(o); }
    } else {
      field = element('input'); field.type = 'text'; field.maxLength = 200;
    }
    field.id='flow-value'; field.value=view.value || (demoFactory ? '' : field.value); card.append(field);
  }
  for (const action of view.actions) {
    const button = element('button', action.label, ['createDraft','next'].includes(action.id) ? 'primary' : '');
    button.type='button'; button.dataset.action=action.id;
    button.disabled = action.disabled === true;
    button.onclick = () => {
      if (busy) return;
      if (action.id === 'browseTemplates') { notifyHost('browse-templates'); return; }
      let value = field?.value.trim();
      if (field && action.id === 'next') {
        if (!value) { field.setCustomValidity('این مورد را وارد کن.'); field.reportValidity(); return; }
        field.setCustomValidity('');
      }
      request(action.id, field ? {field:view.field, value} : {});
    };
    card.append(button);
  }
  if (field) field.addEventListener('input', () => field.setCustomValidity(''));
  root.replaceChildren(card);
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
