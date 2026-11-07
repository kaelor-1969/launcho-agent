// The browser never receives gateway credentials or conversation history.
export async function sendMessage(apiUrl, message, timeout = 45000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
      signal: controller.signal,
      credentials: 'omit',
    });
    if (!response.ok) throw new Error('http');
    let data;
    try { data = await response.json(); } catch { throw new Error('invalid'); }
    if (!data || typeof data.reply !== 'string' || !data.reply.trim()) throw new Error('invalid');
    return data.reply;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('دریافت پاسخ طول کشید. می‌توانی دوباره تلاش کنی.');
    if (error.message === 'invalid') throw new Error('پاسخ معتبری دریافت نشد. دوباره تلاش کن.');
    if (error.message === 'http') throw new Error('ارسال پیام انجام نشد. دوباره تلاش کن.');
    throw new Error('ارتباط برقرار نشد. اتصال اینترنتت را بررسی کن.');
  } finally {
    clearTimeout(timer);
  }
}
