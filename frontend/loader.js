(() => {
  'use strict';
  if (window.LaunchoWidget) return;
  const script = document.currentScript;
  if (!script || !script.src) return;
  const widgetUrl = new URL('/widget/widget.html', script.src);
  const widgetOrigin = widgetUrl.origin;
  const channel = crypto.randomUUID ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint32Array(4))).join('-');
  const options = {
    theme: ['light', 'dark', 'auto'].includes(script.dataset.theme) ? script.dataset.theme : 'auto',
    position: script.dataset.position === 'left' ? 'left' : 'right',
    apiUrl: '/api/chat',
    demo: script.dataset.demo === 'true',
    workflowUrl: null,
    offset: 24,
    mobileOffset: 16,
    width: 380,
    height: 450,
  };
  const dimensions = { width: [280, 960], height: [320, 960] };
  function setDimensions(values) {
    for (const [key, [min, max]] of Object.entries(dimensions)) {
      if (Number.isFinite(values[key])) options[key] = Math.min(max, Math.max(min, values[key]));
    }
  }
  setDimensions({ width: Number(script.dataset.width || NaN), height: Number(script.dataset.height || NaN) });
  function validApi(value) {
    try {
      const url = new URL(value, location.href);
      return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
    } catch { return null; }
  }
  function relativeApi(value) {
    try {
      const url = new URL(value, widgetOrigin);
      return url.origin === widgetOrigin && !url.username && !url.password &&
        !url.pathname.startsWith('//') ? url.pathname + url.search : null;
    } catch { return null; }
  }
  if (script.dataset.apiUrl) options.apiUrl = relativeApi(script.dataset.apiUrl) || options.apiUrl;
  if (script.dataset.workflowUrl) options.workflowUrl = relativeApi(script.dataset.workflowUrl);
  for (const key of ['offset', 'mobileOffset']) if (script.dataset[key] && Number.isFinite(Number(script.dataset[key]))) options[key] = Math.max(0, Math.min(240, Number(script.dataset[key])));
  let host, shadow, button, resizeButton, panel, frame, feedback, ready = false, opened = script.dataset.autoOpen !== 'false';
  let expanded = false;
  let askButton, templateHint, templateHintTimer;
  const systemTheme = matchMedia('(prefers-color-scheme: dark)');
  let loadTimer;
  function post(type, payload = {}) {
    if (!frame || !ready) return;
    const data = { scope: 'launcho', channel, type, ...payload };
    if (type === 'configure') Object.assign(data, options, { open: opened });
    frame.contentWindow.postMessage(data, widgetOrigin);
  }
  function viewport() {
    if (!host) return;
    const view = window.visualViewport;
    host.style.setProperty('--viewport-height', `${view ? view.height : innerHeight}px`);
    host.style.setProperty('--viewport-lift', `${view ? Math.max(0, innerHeight - view.height - view.offsetTop) : 0}px`);
  }
  function setOpen(value) {
    opened = value;
    if (!host) return;
    panel.hidden = !opened;
    askButton.hidden = opened;
    if (opened) {
      clearTimeout(templateHintTimer);
      templateHint.hidden = true;
    }
    resizeButton.hidden = !opened;
    button.setAttribute('aria-expanded', String(opened));
    button.setAttribute('aria-label', 'دستیار لانچو');
    button.dataset.open = String(opened);
    if (opened && !frame) {
      frame = document.createElement('iframe');
      frame.title = 'گفتگو با دستیار لانچو';
      frame.referrerPolicy = 'no-referrer';
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-popups allow-top-navigation-by-user-activation');
      frame.setAttribute('allow', '');
      widgetUrl.hash = new URLSearchParams({ parentOrigin: location.origin, channel }).toString();
      frame.src = widgetUrl.href;
      panel.append(frame);
      loadTimer = setTimeout(() => {
        if (!feedback.hidden) feedback.textContent = 'گفتگو بارگذاری نشد. اتصال اینترنت را بررسی و صفحه را تازه کن.';
      }, 15000);
    }
    post(opened ? 'open' : 'close');
    if (!opened) button.focus({ preventScroll: true });
  }
  function configure(next) {
    if (!next || typeof next !== 'object') return;
    if (['light', 'dark', 'auto'].includes(next.theme)) options.theme = next.theme;
    if (['left', 'right'].includes(next.position)) options.position = next.position;
    if (typeof next.apiUrl === 'string') options.apiUrl = relativeApi(next.apiUrl) || options.apiUrl;
    // Demo mode is fixed at installation, never enabled by a later message.
    if (typeof next.workflowUrl === 'string') options.workflowUrl = relativeApi(next.workflowUrl);
    for (const key of ['offset', 'mobileOffset']) if (Number.isFinite(next[key])) options[key] = Math.max(0, Math.min(240, next[key]));
    setDimensions(next);
    if (host) {
      host.dataset.position = options.position;
      host.style.setProperty('--desktop-offset', `${options.offset}px`);
      host.style.setProperty('--mobile-offset', `${options.mobileOffset}px`);
      host.style.setProperty('--panel-width', `${options.width}px`);
      host.style.setProperty('--panel-height', `${options.height}px`);
      host.dataset.theme = options.theme === 'auto' ? (systemTheme.matches ? 'dark' : 'light') : options.theme;
    }
    post('configure');
  }
  window.LaunchoWidget = Object.freeze({
    open: () => setOpen(true), close: () => setOpen(false),
    setTheme: (theme) => configure({ theme }), configure,
    selectTemplate: (template) => {
      if (!validTemplate(template)) return false;
      post('template-selected', { template: {id:template.id, name:template.name, image:validApi(template.image)} });
      setOpen(true);
      return true;
    },
  });
  function validTemplate(t) {
    return t && typeof t.id === 'string' && t.id.length > 0 && t.id.length <= 200 && typeof t.name === 'string' && t.name.length > 0 && t.name.length <= 200 && typeof t.image === 'string' && Boolean(validApi(t.image));
  }
  window.addEventListener('message', (event) => {
    const data = event.data;
    if (!frame || event.source !== frame.contentWindow || event.origin !== widgetOrigin || !data || data.scope !== 'launcho' || data.channel !== channel) return;
    if (data.type === 'ready') { ready = true; post('configure'); }
    else if (data.type === 'configured' && ready) {
      clearTimeout(loadTimer);
      feedback.hidden = true;
      frame.style.visibility = 'visible';
    } else if (data.type === 'close' && ready) setOpen(false);
    else if (data.type === 'templates-link-opened' && ready && opened) {
      setOpen(false);
      templateHint.hidden = false;
      clearTimeout(templateHintTimer);
      templateHintTimer = setTimeout(() => { templateHint.hidden = true; }, 6500);
    } else if (data.type === 'browse-templates' && ready) {
      window.dispatchEvent(new CustomEvent('launcho:templates:open', { detail: { select: window.LaunchoWidget.selectTemplate } }));
    }
  });
  function mount() {
    host = document.createElement('div');
    host.id = 'launcho-widget';
    host.dataset.position = options.position;
    // Host CSS cannot turn the invisible wrapper into a page-sized click target.
    host.style.setProperty('all', 'initial', 'important');
    host.style.setProperty('position', 'fixed', 'important');
    host.style.setProperty('width', '0', 'important');
    host.style.setProperty('height', '0', 'important');
    host.style.setProperty('z-index', '2147483000', 'important');
    shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = `
      <style>
        :host{--blue:#143ef2;--mid-blue:#0d8ae5;--turquoise:#00d8d1;--white:#fff;--surface:#f7f8ff;--ink:#152a56;--line:#cbdaf1;--button-line:#ffffff40;--button-shadow:0 5px 12px #008ca83b;--offset:var(--desktop-offset,24px);--gap:16px;--size:58px;--radius:32px;--frame-gradient:conic-gradient(var(--blue),var(--mid-blue),var(--turquoise),var(--mid-blue),var(--blue));--frame-duration:6s;--frame-width:3px;--shadow:0 14px 34px #22509838;--viewport-height:100dvh;--viewport-lift:0px}
        :host([data-theme=dark]){--surface:#091525;--ink:#eef6f3;--line:#12394c;--shadow:0 12px 48px #0004}
        *{box-sizing:border-box} [hidden]{display:none!important}
        .launcher{all:initial;box-sizing:border-box;position:fixed;bottom:calc(var(--offset) + env(safe-area-inset-bottom) + var(--viewport-lift));right:calc(var(--offset) + env(safe-area-inset-right));width:var(--size);height:var(--size);border-radius:50%;border:1px solid var(--button-line);background:linear-gradient(135deg,#174BFF 0%,#087DDF 55%,#009EAE 100%);color:var(--white);box-shadow:var(--button-shadow);display:grid;place-items:center;cursor:pointer;transition:transform 180ms;pointer-events:auto}
        button:hover{transform:translateY(-2px)}button:focus-visible{outline:3px solid var(--blue);outline-offset:4px}
        svg{width:26px;height:26px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}button .close{display:none}button[data-open=true]{box-shadow:var(--button-shadow),inset 0 0 0 2px var(--button-line)}
        .panel{position:fixed;right:calc(var(--offset) + env(safe-area-inset-right));bottom:calc(var(--offset) + var(--size) + var(--gap) + env(safe-area-inset-bottom) + var(--viewport-lift));width:380px;max-width:calc(100vw - 24px - env(safe-area-inset-left) - env(safe-area-inset-right));height:450px;max-height:calc(var(--viewport-height) - var(--offset) - var(--offset) - var(--size) - var(--gap) - env(safe-area-inset-bottom) - env(safe-area-inset-top));padding:var(--frame-width);border:0;border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow);background:var(--surface);pointer-events:auto}
        /* The iframe covers the center of the rotating gradient, leaving only the rim visible. */
        .panel::before{content:'';position:absolute;inset:-100%;background:var(--frame-gradient);animation:launcho-border-spin var(--frame-duration) linear infinite;pointer-events:none}
        @keyframes launcho-border-spin{to{transform:rotate(360deg)}}
        iframe{z-index:1;border-radius:calc(var(--radius) - var(--frame-width));border:0;width:100%;height:100%;display:block;visibility:hidden;position:relative;background:transparent}
        .feedback{position:absolute;z-index:1;inset:var(--frame-width);border-radius:calc(var(--radius) - var(--frame-width));background:var(--surface);display:grid;place-items:center;margin:0;padding:24px;text-align:center;font:14px/2 Tahoma,sans-serif;color:var(--ink);direction:rtl}
        .panel{width:var(--panel-width,380px);height:var(--panel-height,450px);max-width:calc(100vw - var(--offset) - 12px - env(safe-area-inset-left) - env(safe-area-inset-right))}
        .panel[data-expanded=true]{width:max(var(--panel-width),680px);height:max(var(--panel-height),720px)}
        .resize{position:fixed;bottom:calc(var(--offset) + 9px + env(safe-area-inset-bottom) + var(--viewport-lift));right:calc(var(--offset) + var(--size) + 8px + env(safe-area-inset-right));display:grid;place-items:center;width:40px;height:40px;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--ink);cursor:pointer}
        :host([data-position=left]) .resize{right:auto;left:calc(var(--offset) + var(--size) + 8px + env(safe-area-inset-left))}
        .resize svg{width:17px;height:17px}
        .ask{position:fixed;bottom:calc(var(--offset) + 7px + env(safe-area-inset-bottom) + var(--viewport-lift));right:calc(var(--offset) + var(--size) + 8px + env(safe-area-inset-right));min-height:44px;max-width:calc(100vw - var(--size) - var(--offset) - 24px);padding:8px 14px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:14px/1.5 Tahoma,sans-serif;direction:rtl;cursor:pointer;box-shadow:var(--shadow)}
        :host([data-position=left]) .ask{right:auto;left:calc(var(--offset) + var(--size) + 8px + env(safe-area-inset-left))}
        .template-hint{position:fixed;bottom:calc(var(--offset) + var(--size) + 8px + env(safe-area-inset-bottom) + var(--viewport-lift));right:calc(var(--offset) + env(safe-area-inset-right));max-width:calc(100vw - 48px);margin:0;padding:9px 14px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:13px/1.5 Tahoma,sans-serif;text-align:center;direction:rtl;pointer-events:none;box-shadow:var(--shadow)}
        :host([data-position=left]) .template-hint{right:auto;left:calc(var(--offset) + env(safe-area-inset-left))}
        :host([data-position=left]) .launcher,:host([data-position=left]) .panel{right:auto;left:calc(var(--offset) + env(safe-area-inset-left))}
        @media(max-width:480px){:host{--offset:var(--mobile-offset,16px);--gap:12px}.panel{right:calc(12px + env(safe-area-inset-right));width:calc(100vw - 24px - env(safe-area-inset-left) - env(safe-area-inset-right))}:host([data-position=left]) .panel{left:calc(12px + env(safe-area-inset-left))}}
        @media(prefers-reduced-motion:reduce){button{transition:none}.panel::before{animation:none}}
        @media(max-width:480px){.resize{display:none}.panel[data-expanded=true]{width:calc(100vw - 24px - env(safe-area-inset-left) - env(safe-area-inset-right));height:var(--panel-height,450px)}}
      </style>
      <div class="panel" id="launcho-panel" hidden><p class="feedback" role="status">در حال آماده‌سازی گفتگو…</p></div>
      <button type="button" aria-label="دستیار لانچو" aria-expanded="false" aria-controls="launcho-panel" data-open="false"><svg class="bubble" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" stroke="none" d="M5 3h14a4 4 0 0 1 4 4v7a4 4 0 0 1-4 4H9l-5 4v-4a4 4 0 0 1-4-4V7a5 5 0 0 1 5-4Z"/><g fill="#00cbd8" stroke="none"><circle cx="6" cy="10.5" r="1.3"/><circle cx="11.5" cy="10.5" r="1.3"/><circle cx="17" cy="10.5" r="1.3"/></g></svg><svg class="close" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6"/></svg></button>`;
    panel = shadow.querySelector('.panel');
    feedback = shadow.querySelector('.feedback');
    button = shadow.querySelector('button');
    button.className = 'launcher';
    askButton = document.createElement('button');
    askButton.type = 'button';
    askButton.className = 'ask';
    askButton.textContent = 'از هوش مصنوعی بپرس';
    askButton.setAttribute('aria-controls', 'launcho-panel');
    askButton.addEventListener('click', () => setOpen(true));
    shadow.append(askButton);
    templateHint = document.createElement('p');
    templateHint.className = 'template-hint';
    templateHint.setAttribute('role', 'status');
    templateHint.textContent = 'قالب رو انتخاب کردی؟ کمک خواستی روی دکمه بزن.';
    templateHint.hidden = true;
    shadow.append(templateHint);
    resizeButton = document.createElement('button');
    resizeButton.type = 'button';
    resizeButton.hidden = true;
    resizeButton.className = 'resize';
    resizeButton.setAttribute('aria-label', 'تغییر اندازهٔ گفتگو');
    resizeButton.setAttribute('aria-pressed', 'false');
    resizeButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4H4v5m11-5h5v5M4 15v5h5m11-5v5h-5"/></svg>';
    resizeButton.addEventListener('click', () => {
      expanded = !expanded;
      panel.dataset.expanded = String(expanded);
      resizeButton.setAttribute('aria-pressed', String(expanded));
    });
    shadow.append(resizeButton);
    button.addEventListener('click', () => setOpen(!opened));
    shadow.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && opened) { event.preventDefault(); setOpen(false); }
    });
    document.body.append(host);
    viewport();
    configure(options);
    if (opened) setOpen(true);
  }
  window.addEventListener('resize', viewport, { passive: true });
  systemTheme.addEventListener('change', () => { if (options.theme === 'auto') configure({ theme: 'auto' }); });
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', viewport, { passive: true });
    window.visualViewport.addEventListener('scroll', viewport, { passive: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
})();
