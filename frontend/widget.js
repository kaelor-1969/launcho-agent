import { sendMessage } from './api.js';
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
let apiUrl = new URL('../api/chat', location.href).href;
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
      const url = new URL(data.apiUrl);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return;
      apiUrl = url.href;
    } catch { return; }
    configured = true;
    structured = data.demo === true || typeof data.workflowUrl === 'string';
    demoMode = data.demo === true;
    await configureWorkflow(data, notify);
    applyTheme(data.theme);
    notify('configured');
    updateInput();
    if (data.open) focusCurrent();
  } else if (data.type === 'open' && configured) {
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
  $('send').disabled = pending || !configured || length === 0 || length > 5000;
  $('retry').disabled = pending;
  document.querySelectorAll('[data-question]').forEach((button) => { button.disabled = pending || !configured || Boolean(failed); });
  input.style.height = 'auto';
  input.style.height = `${Math.min(120, input.scrollHeight)}px`;
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
  bubble.textContent = message;
  const speaker = document.createElement('span');
  speaker.className = 'sr-only';
  speaker.textContent = role === 'user' ? 'شما: ' : 'دستیار لانچو: ';
  bubble.prepend(speaker);
  row.append(avatar, bubble);
  $('messages').append(row);
}
async function submit(message, retry = false) {
  if (pending || !configured || workflowActive()) return;
  message = message.trim();
  if (!message) return;
  if (Array.from(message).length > 5000) {
    showError('پیامت باید حداکثر ۵۰۰۰ کاراکتر باشد.');
    return;
  }
  // A failed turn must be resolved before sending another, preserving order.
  if (failed && !retry) { showError('ابتدا پیام قبلی را با «تلاش مجدد» ارسال کن.', true); return; }
  pending = true;
  failed = null;
  showError('');
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
    const reply = demoMode ? 'برای بررسی مراحل در این نمونه، «ساخت فروشگاه» را انتخاب کن.' : await sendMessage(apiUrl, message);
    appendMessage('assistant', reply);
  } catch (error) {
    failed = message;
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
  if (!failed && !pending) showError(Array.from(input.value.trim()).length > 5000 ? 'پیامت باید حداکثر ۵۰۰۰ کاراکتر باشد.' : '');
});
input.addEventListener('compositionstart', () => { composing = true; });
input.addEventListener('compositionend', () => { composing = false; });
input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !composing && event.keyCode !== 229) {
    event.preventDefault(); submit(input.value);
  }
});
$('retry').addEventListener('click', () => { if (failed) submit(failed, true); });
document.querySelectorAll('[data-question]').forEach((button) => {
  button.addEventListener('click', () => {
    if (button.classList.contains('primary-starter') && structured) startWorkflow();
    else {
      if (button.classList.contains('primary-starter')) document.querySelector('.starters').hidden = true;
      submit(button.dataset.question);
    }
  });
});
// Follow content resizing only while the reader is near the end of the chat.
new ResizeObserver(() => scrollToBottom()).observe($('messages'));
$('welcome').addEventListener('transitionend', () => scrollToBottom());
updateInput();
notify('ready');
