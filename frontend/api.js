// Session credentials stay in memory for the lifetime of the widget.
export function relativeUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const url = new URL(value, location.href);
    return url.origin === location.origin && !url.username && !url.password && !url.pathname.startsWith('//')
      ? url.pathname + url.search : null;
  } catch { return null; }
}

async function post(url, body, token, timeout = 45000, method = body === undefined ? 'GET' : 'POST') {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, {
      method, credentials: 'omit', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...(token ? {'X-Session-Token': token} : {}) },
      body: JSON.stringify(body), signal: controller.signal,
    });
    if (!response.ok) {
      let detail;
      try { detail = (await response.json())?.detail; } catch { /* No upstream text is displayed. */ }
      const error = new Error('http');
      error.status = response.status;
      error.code = typeof detail?.code === 'string' ? detail.code : null;
      throw error;
    }
    let data;
    try { data = await response.json(); } catch { throw new Error('invalid'); }
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('invalid');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('دریافت پاسخ طول کشید. می‌توانی دوباره تلاش کنی.');
    if (error.message === 'invalid') throw new Error('پاسخ معتبری دریافت نشد. دوباره تلاش کن.');
    if (error.message === 'http') {
      if (['session_expired', 'session_not_found'].includes(error.code)) {
        error.message = 'جلسهٔ گفتگو در دسترس نیست یا منقضی شده است.';
      } else if (['review_expired', 'stale_confirmation'].includes(error.code)) {
        error.message = 'خلاصهٔ قبلی معتبر نیست. اطلاعات را دوباره مرور کن.';
      } else if (error.code === 'draft_expired') {
        error.message = 'پیش‌نویس منقضی شده است. پیش از اقدام تازه، اطلاعات را دوباره مرور کن.';
      } else if (error.code === 'invalid_preferences' || error.status === 422) {
        error.message = 'اطلاعات واردشده معتبر نیست. انتخاب‌ها را بررسی و اصلاح کن.';
      } else if (error.code === 'conversation_busy') {
        error.message = 'پاسخ پیام قبلی هنوز در حال آماده‌شدن است. چند لحظه بعد دوباره تلاش کن.';
      } else if (error.code === 'model_rate_limited' || error.status === 429) {
        error.message = 'سرویس پاسخ‌گویی به محدودیت مصرف رسیده. کمی بعد دوباره تلاش کن.';
      } else if (error.code === 'model_unavailable' || [502, 503, 504].includes(error.status)) {
        error.message = 'سرویس پاسخ‌گویی موقتاً در دسترس نیست. کمی بعد دوباره تلاش کن.';
      } else {
        error.message = 'ارسال درخواست انجام نشد. دوباره تلاش کن.';
      }
      throw error;
    }
    throw new Error('ارتباط برقرار نشد. اتصال اینترنتت را بررسی کن.');
  } finally { clearTimeout(timer); }
}

const validRevision = value => Number.isSafeInteger(value) && value >= 0;
const invalid = () => new Error('پاسخ معتبری دریافت نشد. دوباره تلاش کن.');

const sessionEnded = error => ['session_not_found', 'session_expired'].includes(error.code);

export function createSessionApi() {
  let session, initializing, needsReconciliation = false;
  async function start() {
    if (session) return session;
    if (!initializing) {
      initializing = post('/api/sessions', {}).then(data => {
        if (typeof data.sessionId !== 'string' || !data.sessionId ||
            typeof data.sessionToken !== 'string' || !data.sessionToken || !validRevision(data.revision)) throw invalid();
        session = { id: data.sessionId, token: data.sessionToken, revision: data.revision, mode: data.adapterMode };
      }).finally(() => { initializing = null; });
    }
    await initializing;
    return session;
  }
  function endpoint(action) { return `/api/sessions/${encodeURIComponent(session.id)}/${action}`; }
  return {
    start,
    async sendMessage(apiUrl, message, requestId) {
      await start();
      const url = relativeUrl(apiUrl);
      if (!url) throw invalid();
      const send = () => post(url, {message, sessionId: session.id, requestId}, session.token);
      let data;
      try {
        data = await send();
      } catch (error) {
        if (!sessionEnded(error)) throw error;
        session = null;
        needsReconciliation = true;
        await start();
        data = await send();
      }
      if (typeof data.reply !== 'string' || !data.reply.trim() || data.sessionId !== session.id ||
          !validRevision(data.revision) || data.revision < session.revision) throw invalid();
      session.revision = data.revision;
      const result = {...data, sessionRestarted: needsReconciliation};
      needsReconciliation = false;
      return result;
    },
    async localOptions(kind) {
      const data = await post('/api/local-signup-options?kind=' + encodeURIComponent(kind));
      const choices = items => Array.isArray(items) && items.length > 0 && items.every(item =>
        item && typeof item.id === 'string' && item.id && typeof item.label === 'string' && item.label);
      if (!choices(data.businessCategories) || !choices(data.templates) ||
          !data.templates.some(item => item.available === true) ||
          !Array.isArray(data.periods) || !data.periods.length ||
          !data.periods.every(value => Number.isSafeInteger(value) && value > 0 && value <= 120) ||
          !Array.isArray(data.suffixes) || !data.suffixes.length ||
          !data.suffixes.every(value => typeof value === 'string' && /^[a-z0-9]+(?:\.[a-z0-9]+)*$/.test(value))) throw invalid();
      return data;
    },
    async savePreferences(preferences) {
      await start();
      const data = await post(endpoint('preferences'), {revision: session.revision, preferences},
                              session.token, 45000, 'PATCH');
      if (data.sessionId !== session.id || !validRevision(data.revision) || data.revision < session.revision) throw invalid();
      session.revision = data.revision;
      return data;
    },
    async review() {
      await start();
      const data = await post(endpoint('review'), {revision: session.revision}, session.token);
      if (data.sessionId !== session.id || data.revision !== session.revision || typeof data.canConfirm !== 'boolean') throw invalid();
      if (!data.draft && (!data.summary || typeof data.summary !== 'object' || Array.isArray(data.summary) ||
          typeof data.reviewId !== 'string' || typeof data.confirmationToken !== 'string')) throw invalid();
      return data;
    },
    async draftStatus() {
      await start();
      return post(endpoint('draft-status'), undefined, session.token);
    },
    // Called only from the visible confirm button, never from chat/model output.
    async confirm(review) {
      return post(endpoint('confirm'), {
        revision: review.revision, reviewId: review.reviewId,
        confirmationToken: review.confirmationToken, confirmed: true,
      }, session.token);
    },
  };
}
