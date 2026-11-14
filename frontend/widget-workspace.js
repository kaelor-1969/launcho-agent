// Production presentation only: transport, credentials, retries and approval
// remain owned by widget.js/api.js. Never import preview fixtures here.
export function setupConnectedWorkspace(notify) {
  if (document.body.dataset.interface !== 'workspace') return;
  const $ = id => document.getElementById(id);
  const services = [
    { id:'assistant', name:'دستیار لانچو', kind:'هوش مصنوعی', short:'از ایده تا فروشگاه', description:'راهنمای شروع و ساخت فروشگاه' },
    { id:'callcenter', name:'ایجنت کال‌سنتر', kind:'به‌زودی', short:'درخواست تماس تلفنی', description:'سرویس تماس تلفنی فعلاً در دسترس نیست. درخواستی ثبت نمی‌شود.' },
    { id:'human', name:'پشتیبانی انسانی', kind:'فعلاً در دسترس نیست', short:'همراهی یک کارشناس', description:'چت پشتیبانی انسانی فعلاً در دسترس نیست. پیامی برای پشتیبانی ارسال نمی‌شود.' },
  ];
  // Each service owns its view and scroll state. Only the assistant has a
  // connected transport; unavailable services never share its session/history.
  const states = new Map(services.map(service => [service.id, { scroll:0 }]));
  let active = services[0];
  function select(service) {
    states.get(active.id).scroll = $('scroll-area').scrollTop;
    active = service;
    const assistant = active.id === 'assistant';
    document.body.dataset.service = active.id;
    $('assistant-content').hidden = !assistant;
    $('unavailable-service').hidden = assistant;
    $('unavailable-description').textContent = active.description;
    $('chat-title').textContent = active.name;
    $('service-kind').textContent = active.kind;
    $('service-description').textContent = assistant ? active.description : 'فعلاً در دسترس نیست';
    $('service-avatar').hidden = !assistant;
    document.querySelectorAll('[data-service]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.service === active.id)));
    if (assistant) $('scroll-area').scrollTop = states.get(active.id).scroll;
  }
  for (const container of [$('desktop-services'), $('mobile-services')]) {
    for (const service of services) {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'service-card'; button.dataset.service = service.id;
      const avatar = document.createElement('span');
      avatar.className = `avatar ${service.id}${service.id === 'assistant' ? ' launcher-avatar' : ''}`;
      avatar.setAttribute('aria-hidden', 'true');
      if (service.id === 'assistant') {
        const image = document.createElement('img');
        image.src = './assets/phoenix-launcher-front.png'; image.alt = ''; image.width = image.height = 44;
        avatar.append(image);
      } else {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', service.id === 'callcenter'
          ? 'M4 14v-3a8 8 0 0 1 16 0v3M4 12h3v7H4a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2ZM20 12h-3v7h3a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2ZM18 19c0 3-3 3-6 3'
          : 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 22v-2a8 8 0 0 1 16 0v2');
        svg.append(path); avatar.append(svg);
      }
      const copy = document.createElement('span'); copy.className = 'card-copy';
      for (const [className, text] of [['card-name',service.name], ['card-description',service.short], ['card-kind',service.kind]]) {
        const span = document.createElement('span'); span.className = className; span.textContent = text; copy.append(span);
      }
      button.append(avatar, copy);
      button.addEventListener('click', () => { select(service); if ($('service-sheet').open) $('service-sheet').close(); });
      container.append(button);
    }
  }
  $('minimize-workspace').addEventListener('click', () => notify('close'));
  $('expand-workspace').addEventListener('click', () => notify('resize'));
  $('change-service').addEventListener('click', () => {
    $('service-sheet').showModal(); $('change-service').setAttribute('aria-expanded','true');
    $('mobile-services').querySelector('[aria-pressed=true]').focus();
  });
  $('close-sheet').addEventListener('click', () => $('service-sheet').close());
  $('service-sheet').addEventListener('close', () => {
    $('change-service').setAttribute('aria-expanded','false'); $('change-service').focus({preventScroll:true});
  });
  window.addEventListener('resize', () => { if (innerWidth > 850 && $('service-sheet').open) $('service-sheet').close(); });
  select(active);
}
