import { createSessionApi, relativeUrl } from './api.js?v=3';
import { configureWorkflow, startWorkflow, workflowActive, selectWorkflowTemplate } from './workflow.js';

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
    structured = data.demo === true;
    demoMode = data.demo === true;
    if (demoMode) await configureWorkflow(data, notify);
    applyTheme(data.theme);
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
  if (event.key === 'Escape') { event.preventDefault(); notify('close'); }
});

function updateInput() {
  const length = Array.from(input.value.trim()).length;
  const blocked = pending || sessionStarting || confirmationPending || (!demoMode && !sessionReady);
  $('send').disabled = blocked || !configured || length === 0 || length > 5000;
  $('retry').disabled = pending || sessionStarting;
  $('review-button').disabled = blocked || !configured || Boolean(failed);
  $('confirm').disabled = pending || !review?.canConfirm;
  document.querySelectorAll('[data-question]').forEach((button) => { button.disabled = blocked || !configured || Boolean(failed); });
  input.style.height = 'auto';
  input.style.height = `${Math.min(120, input.scrollHeight)}px`;
}
async function initializeSession() {
  if (sessionReady || sessionStarting || demoMode) return;
  sessionStarting = true;
  updateInput();
  try {
    await sessionApi.start();
    sessionReady = true;
    showError('');
  } catch {
    showError('جلسه گفتگو ایجاد نشد. دوباره تلاش کن.', true);
  } finally {
    sessionStarting = false;
    updateInput();
  }
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
function appendMessage(role, message) {
  const row = document.createElement('div');
  row.className = `message-row role-${role}`;
  const avatar = document.createElement('span');
  avatar.className = 'avatar';
  avatar.setAttribute('aria-hidden', 'true');
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', role === 'user' ? '#person' : '#bot-avatar');
  icon.append(use);
  avatar.append(icon);
  const bubble = document.createElement('p');
  bubble.className = `bubble ${role}`;
  if (role === 'user') {
    bubble.textContent = message;
  } else {
    // Render only bold markers. Every other character stays plain text.
    let offset = 0;
    for (const match of message.matchAll(/\*\*([^*\r\n]+)\*\*/g)) {
      bubble.append(document.createTextNode(message.slice(offset, match.index)));
      const bold = document.createElement('strong');
      bold.textContent = match[1];
      bubble.append(bold);
      offset = match.index + match[0].length;
    }
    bubble.append(document.createTextNode(message.slice(offset)));
  }
  const speaker = document.createElement('span');
  speaker.className = 'sr-only';
  speaker.textContent = role === 'user' ? 'شما: ' : 'دستیار لانچو: ';
  bubble.prepend(speaker);
  row.append(avatar, bubble);
  $('messages').append(row);
}
async function submit(message, retry = false) {
  if (pending || sessionStarting || confirmationPending || (!demoMode && !sessionReady) || !configured || workflowActive()) return;
  message = message.trim();
  if (!message) return;
  if (Array.from(message).length > 5000) {
    showError('پیامت باید حداکثر ۵۰۰۰ کاراکتر باشد.');
    return;
  }
  // A failed turn must be resolved before sending another, preserving order.
  if (failed && !retry) { showError('ابتدا پیام قبلی را با «تلاش مجدد» ارسال کن.', true); return; }
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

function showDraft(draft) {
  // Accept only the official continuation URL from the structured server result.
  const url = new URL(draft.confirmUrl);
  if (url.origin !== 'https://launcho.ir' || url.pathname !== '/start' || url.hash ||
      url.username || url.password || !/^sd_[A-Za-z0-9_-]{4,128}$/.test(draft.ref) ||
      url.search !== `?signup=${draft.ref}` || draft.status !== 'draft') throw new Error('لینک پیش‌نویس معتبر نیست.');
  const link = document.createElement('a');
  link.textContent = 'ادامه در فرم رسمی لانچو';
  link.href = url.href;
  link.target = '_top';
  $('review-summary').replaceChildren(link);
  $('confirm').hidden = true;
  $('review-notice').textContent = 'شماره موبایل و اطلاعات پرداخت را فقط در فرم رسمی لانچو وارد کن.';
  $('session-review').hidden = false;
}

$('review-button').addEventListener('click', async () => {
  if (pending || confirmationPending || failed || !sessionReady) return;
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
      const rows = document.createElement('dl');
      const domain = summary.domain;
      for (const [label, value] of [
        ['نوع', summary.kind === 'website' ? 'وب‌سایت' : 'فروشگاه'],
        ['نام کسب‌وکار', summary.businessName], ['دسته‌بندی', summary.category],
        ['دوره اشتراک (ماه)', summary.planMonths], ['قالب', summary.template],
        ['دامنه', domain?.ownDomain || (domain ? `${domain.label}.${domain.tld}` : '')],
      ]) {
        const dt = document.createElement('dt'), dd = document.createElement('dd');
        dt.textContent = label;
        dd.textContent = String(value ?? '');
        rows.append(dt, dd);
      }
      $('review-summary').replaceChildren(rows);
      $('review-notice').textContent = review.canConfirm
        ? 'با تأیید شما پیش‌نویس ساخته می‌شود. موبایل و پرداخت فقط در فرم رسمی لانچو تکمیل می‌شوند.'
        : 'اتصال ساخت پیش‌نویس فعلاً آماده نیست؛ از فرم رسمی لانچو استفاده کن.';
      $('confirm').hidden = false;
      $('session-review').hidden = false;
    }
    scrollToBottom(true);
  } catch (error) { showError(error.message); }
  finally { pending = false; updateInput(); }
});

// This is the only production path that can authorize draft creation.
$('confirm').addEventListener('click', async () => {
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
      showError('تأیید انجام نشد. اطلاعات را بررسی و خلاصه را دوباره مرور کن.');
    } else showError('نتیجه تأیید دریافت نشد. برای بررسی همان درخواست، دوباره دکمه تأیید را بزن.');
  } finally { pending = false; updateInput(); }
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
updateInput();
if (configured) initializeSession();
notify('ready');
