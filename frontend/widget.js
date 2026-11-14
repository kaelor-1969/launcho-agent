import { createSessionApi, relativeUrl } from './api.js?v=6';
import { setupConnectedWorkspace } from './widget-workspace.js';
import { configureWorkflow, startWorkflow, workflowActive, selectWorkflowTemplate } from './workflow.js?v=3';

const $ = (id) => document.getElementById(id);
const input = $('message');
const scrollArea = $('scroll-area');
const params = new URLSearchParams(location.hash.slice(1));
const channel = params.get('channel');
let parentOrigin = null;
try {
  const url = new URL(params.get('parentOrigin'));
  if (['http:', 'https:'].includes(url.protocol) && url.origin === params.get('parentOrigin')) parentOrigin = url.origin;
} catch { /* Standalone preview does not send messages to a parent. */ }
let apiUrl = '/api/chat';
const sessionApi = createSessionApi();
let sessionReady = false;
let sessionStarting = false;
let review = null;
let confirmationPending = false;
let configured = window.parent === window;
let pending = false;
let failed = null;
let composing = false;
let followBottom = true;
let structured = false;
let demoMode = false;
let signupAvailable = false;
let signupLoading = false;
let signupSaving = false;
let editSignup;
let prepareSignupReview;
const persianNumber = value => new Intl.NumberFormat('fa-IR', {useGrouping: false}).format(value);
const systemTheme = matchMedia('(prefers-color-scheme: dark)');
let theme = 'light';

function notify(type) {
  if (parentOrigin && channel && window.parent !== window) {
    window.parent.postMessage({ scope: 'launcho', channel, type }, parentOrigin);
  }
}
function applyTheme(value) {
  if (!['light', 'dark', 'auto'].includes(value)) return;
  theme = value;
  document.documentElement.dataset.theme = value === 'auto' ? (systemTheme.matches ? 'dark' : 'light') : value;
}
systemTheme.addEventListener('change', () => applyTheme(theme));
function focusCurrent() {
  if (document.body.dataset.service && document.body.dataset.service !== 'assistant') return;
  if (workflowActive()) document.querySelector('#workflow h2')?.focus({preventScroll:true});
  else input.focus({preventScroll:true});
}
window.addEventListener('message', async (event) => {
  const data = event.data;
  if (event.source !== window.parent || event.origin !== parentOrigin || !data || data.scope !== 'launcho' || data.channel !== channel) return;
  if (data.type === 'configure') {
    if (!['light', 'dark', 'auto'].includes(data.theme) || typeof data.apiUrl !== 'string' || typeof data.open !== 'boolean') return;
    try {
      const url = relativeUrl(data.apiUrl);
      if (!url) return;
      apiUrl = url;
    } catch { return; }
    configured = true;
    demoMode = document.body.dataset.interface !== 'workspace' && data.demo === true;
    structured = demoMode;
    if (demoMode) await configureWorkflow(data, notify);
    applyTheme(data.theme);
    if ($('expand-workspace') && typeof data.expanded === 'boolean') $('expand-workspace').setAttribute('aria-pressed', String(data.expanded));
    notify('configured');
    if (data.open && !demoMode) initializeSession();
    updateInput();
    if (data.open) focusCurrent();
  } else if (data.type === 'open' && configured) {
    if (!demoMode) initializeSession();
    focusCurrent();
  } else if (data.type === 'close' && configured) {
    input.blur();
  } else if (data.type === 'template-selected' && configured) {
    selectWorkflowTemplate(data.template);
  }
});
$('close').addEventListener('click', () => notify('close'));
document.addEventListener('keydown', (event) => {
  if ($('service-sheet')?.open) return;
  if (event.key === 'Escape') { event.preventDefault(); notify('close'); }
});

function hasVisibleText(message) {
  return /[\p{L}\p{N}\p{P}\p{S}]/u.test(message);
}

function updateInput() {
  const length = Array.from(input.value.trim()).length;
  const blocked = pending || signupSaving || sessionStarting || confirmationPending || (!demoMode && !sessionReady);
  $('send').disabled = blocked || !configured || !hasVisibleText(input.value) || length > 5000;
  $('retry').disabled = pending || sessionStarting;
  $('review-button').disabled = blocked || !configured || Boolean(failed);
  // An unknown result locks edits, but permits an explicit retry of this review.
  $('confirm').disabled = pending || signupSaving || !review?.canConfirm;
  $('edit-signup').disabled = blocked;
  if (signupAvailable) {
    $('local-signup').querySelectorAll('input,select,button').forEach(control => {
      control.disabled = blocked || Boolean(failed) || signupLoading || (control.id === 'signup-save' && !localOptions);
    });
  }
  document.querySelectorAll('[data-question]').forEach((button) => { button.disabled = blocked || !configured || Boolean(failed); });
  input.style.height = 'auto';
  input.style.height = `${Math.min(120, input.scrollHeight)}px`;
}
async function initializeSession() {
  if (sessionReady || sessionStarting || demoMode) return;
  sessionStarting = true;
  updateInput();
  try {
    const session = await sessionApi.start();
    if (session.mode === 'local_mock') await initializeLocalSignup();
    sessionReady = true;
    showError('');
  } catch {
    showError('جلسه گفتگو ایجاد نشد. دوباره تلاش کن.', true);
  } finally {
    sessionStarting = false;
    updateInput();
  }
}
let localOptions;
async function initializeLocalSignup() {
  signupAvailable = true;
  const form = $('local-signup');
  let optionsRequest = 0;
  let optionsKind;
  let retainedChoices = {};
  const fill = (name, values) => {
    const select = form.elements[name];
    const previous = select.value;
    select.replaceChildren(...values.map(([value, label]) => new Option(label, value)));
    if (values.some(([value]) => value === previous)) select.value = previous;
  };

  const updatePreview = () => {
    const link = $('local-template-preview');
    const template = localOptions?.templates.find(item => item.id === form.elements.template.value);
    link.hidden = true;
    link.removeAttribute('href');
    if (!template?.previewUrl) return;
    try {
      const url = new URL(template.previewUrl);
      if (url.protocol === 'https:' && url.origin === 'https://demo.launcho.ir' && !url.username && !url.password) {
        link.href = url.href;
        link.hidden = false;
      }
    } catch { /* The template remains selectable without a preview. */ }
  };
  const updateTemplates = () => {
    if (!localOptions || optionsKind !== form.elements.kind.value) return;
    const category = form.elements.category.value;
    fill('template', localOptions.templates.filter(item => item.available === true).map(item => [
      item.id, item.label + (item.recommendedFor?.includes(category) ? ' (پیشنهادی)' : ''),
    ]));
    updatePreview();
  };
  const loadOptions = async () => {
    const kind = form.elements.kind.value;
    const request = ++optionsRequest;
    if (optionsKind) retainedChoices = Object.fromEntries(['category', 'template', 'planMonths', 'tld'].map(name => [name, form.elements[name].value]));
    optionsKind = null;
    localOptions = null;
    signupLoading = true;
    $('signup-retry').hidden = true;
    $('local-signup-status').textContent = 'در حال دریافت گزینه‌ها…';
    for (const name of ['category', 'template', 'planMonths', 'tld']) fill(name, []);
    updatePreview();
    updateInput();
    try {
      const options = await sessionApi.localOptions(kind);
      if (request !== optionsRequest || form.elements.kind.value !== kind) return false;
      localOptions = options;
      optionsKind = kind;
      fill('category', options.businessCategories.map(item => [item.id, item.label]));
      fill('planMonths', options.periods.map(value => [String(value), `${persianNumber(value)} ماهه`]));
      fill('tld', options.suffixes.map(value => [value, value]));
      for (const name of ['category', 'planMonths', 'tld']) {
        if (Array.from(form.elements[name].options).some(option => option.value === retainedChoices[name])) form.elements[name].value = retainedChoices[name];
      }
      updateTemplates();
      if (options.templates.some(item => item.available === true && item.id === retainedChoices.template)) form.elements.template.value = retainedChoices.template;
      updatePreview();
      $('local-signup-status').textContent = '';
      return true;
    } catch (error) {
      if (request === optionsRequest) {
        $('local-signup-status').textContent = error.message;
        $('signup-retry').hidden = false;
      }
      return false;
    } finally {
      if (request === optionsRequest) { signupLoading = false; updateInput(); }
    }
  };
  const invalidate = () => {
    review = null;
    $('session-review').hidden = true;
    $('review-button').hidden = true;
    updateInput();
  };
  form.addEventListener('input', invalidate);
  form.addEventListener('change', invalidate);
  form.elements.category.onchange = updateTemplates;
  form.elements.template.onchange = updatePreview;
  form.elements.kind.onchange = loadOptions;
  $('signup-retry').onclick = loadOptions;
  prepareSignupReview = async summary => {
    form.elements.kind.value = summary.kind === 'website' ? 'website' : 'shop';
    if (optionsKind !== form.elements.kind.value && !await loadOptions()) throw new Error('گزینه‌های مرور دریافت نشد. دوباره تلاش کن.');
  };
  form.hidden = false;
  editSignup = async summary => {
    invalidate();
    showError('');
    $('signup-title').textContent = 'ویرایش انتخاب‌ها';
    $('signup-save').textContent = 'ذخیره و مرور دوباره';
    form.hidden = false;
    form.elements.businessName.value = summary.businessName || '';
    form.elements.kind.value = summary.kind === 'website' ? 'website' : 'shop';
    if (optionsKind !== form.elements.kind.value) await loadOptions();
    if (optionsKind === form.elements.kind.value) {
      form.elements.category.value = summary.category || '';
      updateTemplates();
      form.elements.template.value = summary.template || '';
      form.elements.planMonths.value = String(summary.planMonths ?? '');
      form.elements.tld.value = summary.domain?.tld || '';
      form.elements.label.value = summary.domain?.label || '';
      updatePreview();
    }
    revealCard('signup-title');
  };
  form.onsubmit = async event => {
    event.preventDefault();
    if (pending || signupSaving || signupLoading || confirmationPending || !sessionReady || failed ||
        optionsKind !== form.elements.kind.value || !form.reportValidity()) return;
    form.elements.businessName.value = form.elements.businessName.value.trim();
    if (!hasVisibleText(form.elements.businessName.value)) {
      $('local-signup-status').textContent = 'نام کسب‌وکار را وارد کن.';
      form.elements.businessName.focus();
      return;
    }
    const status = $('local-signup-status');
    status.textContent = '';
    // Capture values before locking controls: disabled controls are absent from FormData.
    const fields = Object.fromEntries(new FormData(form));
    invalidate();
    signupSaving = true;
    updateInput();
    try {
      await sessionApi.savePreferences({
        kind: fields.kind, businessName: fields.businessName, category: fields.category,
        template: fields.template, planMonths: Number(fields.planMonths),
        domain: {label: fields.label, tld: fields.tld},
      });
      signupSaving = false;
      await requestReview();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      signupSaving = false;
      updateInput();
    }
  };
  await loadOptions();
}

function revealCard(headingId) {
  const heading = $(headingId);
  // Scroll inside the widget without shifting its host frame or composer.
  scrollArea.scrollTop += heading.getBoundingClientRect().top - scrollArea.getBoundingClientRect().top - 16;
  heading.focus({preventScroll: true});
}

function showError(message, retry = false) {
  $('error-text').textContent = message;
  $('error').hidden = !message;
  $('retry').hidden = !retry;
}
function scrollToBottom(force = false) {
  if (force || followBottom) scrollArea.scrollTop = scrollArea.scrollHeight;
}
scrollArea.addEventListener('scroll', () => {
  followBottom = scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight < 80;
}, { passive: true });
const officialChatUrls = new Set([
  'https://launcho.ir', 'https://launcho.ir/', 'https://launcho.ir/start',
  'https://launcho.ir/pricing', 'https://launcho.ir/contact', 'https://launcho.ir/features',
  'https://launcho.ir/#templates', 'https://launcho.ir/store-setup', 'https://launcho.ir/installments',
]);

function appendReplyText(parent, text) {
  let offset = 0;
  for (const match of text.matchAll(/https?:\/\/[^\s<>"'\]\)*`]+/gi)) {
    const address = match[0].replace(/[.,،؛]+$/, '');
    if (!officialChatUrls.has(address)) continue;
    parent.append(document.createTextNode(text.slice(offset, match.index)));
    const link = document.createElement('a');
    link.href = address;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = address;
    if (address === 'https://launcho.ir/#templates') {
      link.textContent = 'مشاهدهٔ قالب‌های لانچو';
      link.addEventListener('click', () => notify('templates-link-opened'));
    }
    parent.append(link);
    offset = match.index + address.length;
  }
  parent.append(document.createTextNode(text.slice(offset)));
}

function appendMessage(role, message) {
  const row = document.createElement('div');
  const workspace = document.body.dataset.interface === 'workspace';
  row.className = `message-row role-${role}${workspace ? ` ${role}` : ''}`;
  const avatar = document.createElement('span');
  avatar.className = 'avatar';
  if (workspace) avatar.classList.add(role === 'user' ? 'user-avatar' : 'assistant');
  avatar.setAttribute('aria-hidden', 'true');
  let icon;
  if (role === 'user') {
    icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '#person');
    icon.append(use);
  } else {
    icon = document.createElement('img');
    icon.src = new URL('./assets/phoenix-avatar-left.png', import.meta.url).href;
    icon.alt = '';
    icon.className = 'assistant-avatar';
    icon.width = 42;
    icon.height = 42;
  }
  avatar.append(icon);
  const bubble = document.createElement('p');
  bubble.className = `bubble ${role}`;
  if (role === 'user') {
    bubble.textContent = message;
  } else {
    // Build text, bold spans, and approved links without parsing HTML.
    let offset = 0;
    for (const match of message.matchAll(/\*\*([^*\r\n]+)\*\*/g)) {
      appendReplyText(bubble, message.slice(offset, match.index));
      const bold = document.createElement('strong');
      appendReplyText(bold, match[1]);
      bubble.append(bold);
      offset = match.index + match[0].length;
    }
    appendReplyText(bubble, message.slice(offset));
  }
  const speaker = document.createElement('span');
  speaker.className = 'sr-only';
  speaker.textContent = role === 'user' ? 'شما: ' : 'دستیار لانچو: ';
  bubble.prepend(speaker);
  if (workspace) {
    const content = document.createElement('div');
    content.className = 'message-content';
    content.append(bubble);
    row.append(avatar, content);
  } else row.append(avatar, bubble);
  $('messages').append(row);
}
async function submit(message, retry = false) {
  if (pending || signupSaving || sessionStarting || confirmationPending || (!demoMode && !sessionReady) || !configured || workflowActive()) return;
  message = message.trim();
  if (!hasVisibleText(message)) return;
  if (Array.from(message).length > 5000) {
    showError('پیامت باید حداکثر ۵۰۰۰ کاراکتر باشد.');
    return;
  }
  // A failed turn must be resolved before sending another, preserving order.
  if (failed && !retry) { showError('ابتدا پیام قبلی را با «تلاش مجدد» ارسال کن.', true); return; }
  if (demoMode && /(?:مراحل\s+)?ثبت[\s‌]*نام\s+(?:(?:رو|را)\s+)?(?:(?:برام|برای من)\s+)?(?:انجام بده|شروع کن)/u.test(message)) {
    input.value = '';
    startWorkflow();
    return;
  }
  const requestId = retry ? failed.requestId : globalThis.crypto?.randomUUID?.();
  pending = true;
  failed = null;
  showError('');
  review = null;
  $('session-review').hidden = true;
  $('review-button').hidden = true;
  if (!retry) {
    $('welcome').classList.add('compact');
    $('welcome-description').hidden = true;
    appendMessage('user', message);
    input.value = '';
    followBottom = true;
  }
  $('waiting').hidden = false;
  updateInput();
  scrollToBottom();
  try {
    // Give the explicit demo a visible pending state, without calling an API.
    if (demoMode) await new Promise(resolve => setTimeout(resolve, 700));
    const result = demoMode ? {reply: 'برای بررسی مراحل در این نمونه، «ساخت فروشگاه» را انتخاب کن.'} : await sessionApi.sendMessage(apiUrl, message, requestId);
    appendMessage('assistant', result.reply);
    $('review-button').hidden = result.nextAction !== 'review';
  } catch (error) {
    failed = {message, requestId};
    showError(error.message, true);
  } finally {
    pending = false;
    $('waiting').hidden = true;
    updateInput();
    scrollToBottom();
  }
}
$('form').addEventListener('submit', (event) => { event.preventDefault(); if (!composing) submit(input.value); });
input.addEventListener('input', () => {
  updateInput();
  if (!failed && !pending && !confirmationPending && (demoMode || sessionReady)) {
    showError(Array.from(input.value.trim()).length > 5000 ? 'پیامت باید حداکثر ۵۰۰۰ کاراکتر باشد.' : '');
  }
});
input.addEventListener('compositionstart', () => { composing = true; });
input.addEventListener('compositionend', () => { composing = false; });
input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !composing && event.keyCode !== 229) {
    event.preventDefault(); submit(input.value);
  }
});
$('retry').addEventListener('click', () => {
  if (!sessionReady && !demoMode) initializeSession();
  else if (failed) submit(failed.message, true);
});

const draftStatusText = new Map([
  ['draft', 'پیش‌نویس آماده است. فرم را باز کنید.'],
  ['opened', 'شمارهٔ موبایل را در فرم رسمی تأیید کنید.'],
  ['mobile_verified', 'ثبت‌نام را در فرم رسمی کامل کنید.'],
  ['invoiced', 'فاکتور در لانچو آمادهٔ بررسی است.'],
  ['paid', 'پرداخت ثبت شده و فروشگاه در انتظار فعال‌سازی است.'],
  ['active', 'فروشگاه فعال است. برای شروع، اولین محصول را از پنل اضافه کنید.'],
  ['expired', 'پیش‌نویس منقضی شده است. برای ادامه پیش‌نویس تازه بسازید.'],
]);

function showDraft(draft) {
  // Accept only the official continuation URL from the structured server result.
  const local = draft.adapterMode === 'local_mock' || (localOptions && draft.confirmUrl?.startsWith('/api/local-drafts/'));
  const url = new URL(draft.confirmUrl, location.origin);
  const allowed = local
    ? url.origin === location.origin && url.pathname === `/api/local-drafts/${draft.ref}/preview` && !url.search
    : url.origin === 'https://launcho.ir' && url.pathname === '/start' && url.search === `?signup=${draft.ref}`;
  if (!allowed || url.hash || url.username || url.password ||
      !/^sd_[A-Za-z0-9_-]{4,128}$/.test(draft.ref) || draft.status !== 'draft') throw new Error('لینک پیش‌نویس معتبر نیست.');
  const link = document.createElement('a');
  link.textContent = local ? 'باز کردن پیش‌نویس آزمایشی' : 'ادامه در فرم رسمی لانچو';
  link.href = url.href;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  const statusButton = document.createElement('button');
  statusButton.type = 'button';
  statusButton.textContent = 'بررسی وضعیت ثبت‌نام';
  statusButton.addEventListener('click', async () => {
    statusButton.disabled = true;
    try {
      const result = await sessionApi.draftStatus();
      $('review-notice').textContent = draftStatusText.get(result.status) || 'وضعیت ثبت‌نام دریافت نشد.';
    } catch {
      $('review-notice').textContent = 'پیگیری وضعیت فعلاً در دسترس نیست. کمی بعد دوباره بررسی کنید.';
    } finally {
      statusButton.disabled = false;
    }
  });
  $('review-summary').replaceChildren(link, statusButton);
  $('local-signup').hidden = true;
  $('edit-signup').hidden = true;
  $('edit-notice').hidden = true;
  $('confirm').hidden = true;
  $('review-notice').textContent = local ? 'این پیش‌نویس فقط برای توسعهٔ محلی است.' : 'شماره موبایل و اطلاعات پرداخت را فقط در فرم رسمی لانچو وارد کن.';
  $('session-review').hidden = false;
}

async function requestReview() {
  if (pending || signupSaving || signupLoading || confirmationPending || failed || !sessionReady) return;
  // A new server review invalidates the previous confirmation, even if its
  // response is lost. Never leave the previous review available for approval.
  review = null;
  $('session-review').hidden = true;
  pending = true;
  showError('');
  updateInput();
  try {
    review = await sessionApi.review();
    if (review.draft) showDraft(review.draft);
    else {
      const summary = review.summary;
      if (prepareSignupReview) await prepareSignupReview(summary);
      const rows = document.createElement('dl');
      const domain = summary.domain;
      for (const [label, value] of [
        ['نوع سرویس', summary.kind === 'website' ? 'سایت‌ساز' : 'فروشگاه'],
        ['نام کسب‌وکار', summary.businessName], ['دسته‌بندی', localOptions?.businessCategories.find(item => item.id === summary.category)?.label ?? summary.category],
        ['قالب', localOptions?.templates.find(item => item.id === summary.template)?.label ?? summary.template],
        ['دورهٔ اشتراک', summary.planMonths == null ? '' : `${persianNumber(summary.planMonths)} ماهه`],
        ['دامنه', domain?.ownDomain || (domain ? `${domain.label}.${domain.tld}` : '')],
      ]) {
        const dt = document.createElement('dt'), dd = document.createElement('dd');
        dt.textContent = label;
        dd.textContent = String(value ?? '');
        if (label === 'دامنه') dd.dir = 'ltr';
        rows.append(dt, dd);
      }
      $('review-summary').replaceChildren(rows);
      $('local-signup').hidden = true;
      $('edit-signup').hidden = !signupAvailable;
      $('edit-notice').hidden = !signupAvailable;
      $('review-notice').textContent = review.canConfirm
        ? (signupAvailable ? 'ساخت پیش‌نویس آزمایشی فقط با تأیید شما انجام می‌شود؛ فروشگاه واقعی ایجاد نمی‌شود.' : 'با تأیید شما پیش‌نویس ساخته می‌شود. موبایل و پرداخت فقط در فرم رسمی لانچو تکمیل می‌شوند.')
        : 'اتصال ساخت پیش‌نویس فعلاً آماده نیست؛ از فرم رسمی لانچو استفاده کن.';
      $('confirm').hidden = false;
      $('session-review').hidden = false;
    }
    $('review-button').hidden = true;
    revealCard('review-title');
  } catch (error) { review = null; $('session-review').hidden = true; $('review-button').hidden = false; showError(error.message); }
  finally { pending = false; updateInput(); }
}
$('review-button').addEventListener('click', requestReview);
$('edit-signup').addEventListener('click', () => {
  if (pending || signupSaving || confirmationPending || failed || !review?.summary || !editSignup) return;
  editSignup(review.summary);
});

// This is the only production path that can authorize draft creation.
$('confirm').addEventListener('click', async (event) => {
  if (!event.isTrusted) return;
  if (pending || failed || !review?.canConfirm) return;
  pending = true;
  confirmationPending = true;
  showError('');
  updateInput();
  try {
    showDraft(await sessionApi.confirm(review));
    confirmationPending = false;
    review = null;
    $('review-button').hidden = true;
  } catch (error) {
    // Preserve this exact review after a timeout. Only another click retries it.
    if (['stale_confirmation', 'review_expired', 'draft_expired', 'review_rejected', 'draft_rejected', 'draft_adapter_unavailable'].includes(error.code)) {
      confirmationPending = false;
      review = null;
      $('session-review').hidden = true;
      $('review-button').hidden = false;
      showError('تأیید انجام نشد. اطلاعات را بررسی و خلاصه را دوباره مرور کن.');
    } else showError('نتیجه تأیید دریافت نشد. برای بررسی همان درخواست، دوباره دکمه تأیید را بزن.');
  } finally {
    pending = false;
    updateInput();
    if (confirmationPending && review && document.activeElement === document.body) $('confirm').focus({preventScroll: true});
  }
});
document.querySelectorAll('[data-question]').forEach((button) => {
  button.addEventListener('click', () => {
    if (button.classList.contains('primary-starter') && structured) startWorkflow();
    else submit(button.dataset.question);
  });
});
// Follow content resizing only while the reader is near the end of the chat.
new ResizeObserver(() => scrollToBottom()).observe($('messages'));
$('welcome').addEventListener('transitionend', () => scrollToBottom());
setupConnectedWorkspace(notify);
updateInput();
if (configured) initializeSession();
notify('ready');
