// Explicit, in-memory demo fixtures only. Never imported by the live installation.
// Transitions here simulate a SERVER contract, not a second production agent.
export function createDemoWorkflow() {
  let state = {}, step = 'businessName', editing = false, revision = 0, draft = false;
  const sessionId = crypto.randomUUID();
  const fields = ['businessName','category','domain','template','mobile','subscription','setupPayment'];
  const labels = {businessName:'نام کسب‌وکار',category:'دسته‌بندی',domain:'دامنه',template:'قالب',mobile:'موبایل',subscription:'اشتراک',setupPayment:'روش پرداخت راه‌اندازی'};
  const plans = [
    {id:'3',label:'سه‌ماهه — بدون ماه رایگان',subscription:2400000,installment:6150000,upfront:17400000},
    {id:'6',label:'شش‌ماهه — یک ماه رایگان',subscription:4000000,installment:7750000,upfront:19000000},
    {id:'12',label:'سالانه — دو ماه رایگان',subscription:8000000,installment:11750000,upfront:23000000},
  ];
  const number = n => new Intl.NumberFormat('fa-IR').format(n) + ' تومان';
  const action = (id,label) => ({id,label});
  const envelope = v => ({sessionId, revision:++revision, ...v});
  function quote() {
    const plan = plans.find(p => p.id === state.subscription);
    const installments = state.setupPayment === 'installments';
    return {id:`demo-${state.subscription}-${state.setupPayment}`, currency:'TOMAN', today:installments ? plan.installment : plan.upfront, expiresAt:new Date(Date.now()+900000).toISOString()};
  }
  function costRows() {
    const plan = plans.find(p=>p.id===state.subscription);
    return [
      {label:'اشتراک',value:plan.label}, {label:'هزینه اشتراک',value:number(plan.subscription)},
      {label:'کل راه‌اندازی',value:number(15000000)},
      {label:'سهم راه‌اندازی امروز',value:number(state.setupPayment === 'installments' ? 3750000 : 15000000)},
      {label:'پرداخت امروز',value:number(quote().today)},
      {label:'اقساط باقی‌مانده',value:state.setupPayment === 'installments' ? '۳ قسط ۳٬۷۵۰٬۰۰۰ تومانی؛ بدون کارمزد. سررسید از سیستم دریافت می‌شود.' : 'ندارد'},
      {label:'دامنه اختصاصی',value:'در این نمونه هزینه جدا ندارد'},
    ];
  }
  function review() {
    return envelope({kind:'review', title:'مرور اطلاعات', quote:quote(),
      rows:[...['businessName','category','domain','mobile'].map(f=>({label:labels[f],value:state[f]})),
        {label:'وضعیت دامنه',value:'آزاد؛ ثبت یا رزرو نشده (نمایشی)'},{label:'قالب',value:state.template.name}, ...costRows()],
      actions:[action('createDraft','تأیید و ساخت پیش‌نویس'),action('edit','ویرایش اطلاعات')]});
  }
  function field() {
    if (step==='template') return envelope({kind:'template',title:'قالب فروشگاهت را انتخاب کن',...(state.template ? {template:state.template} : {}), actions:[action('browseTemplates',state.template ? 'تغییر قالب' : 'مشاهده و انتخاب قالب')]});
    return envelope({kind:'field', field:step, label:labels[step], value:state[step] || '',
      title:step==='businessName' ? 'حتماً، قدم‌به‌قدم پیش می‌ریم. اسم کسب‌وکارت چیه؟' : `${labels[step]} را مشخص کن`,
      ...(step==='category' ? {options:[{id:'پوشاک',label:'پوشاک'},{id:'زیبایی',label:'زیبایی'},{id:'سایر',label:'سایر'}]} : {}),
      ...(step==='subscription' ? {options:plans.map(({id,label})=>({id,label}))} : {}),
      ...(step==='setupPayment' ? {options:[{id:'installments',label:'۴ قسط بدون کارمزد'},{id:'upfront',label:'یکجا'}]} : {}),
      ...(step==='domain' ? {domainStatus:state.domainStatus || 'unchecked',description:'آزاد بودن به معنی ثبت یا رزرو نیست. در demo، taken.ir غیرقابل انتخاب و error.ir خطا است.'} : {}),
      ...(step==='mobile' && state.template ? {template:state.template} : {}),
      actions:step==='domain' ? [action('checkDomain','بررسی دامنه'),...(state.domainStatus==='available' ? [action('next','ادامه')] : [])] : [action('next','ادامه'),...(step==='mobile' ? [action('changeTemplate','تغییر قالب')] : [])]});
  }
  function advance() {
    if (editing) { editing=false; return review(); }
    const index=fields.indexOf(step);
    if (index===fields.length-1) return review();
    step=fields[index+1]; return field();
  }
  function payment() {
    return envelope({kind:'payment',title:'خلاصه هزینه',quote:quote(),rows:costRows(),
      description:'حالت نمایشی؛ پرداخت واقعی غیرفعال است.',
      actions:[{...action('pay','پرداخت'),disabled:true},action('editPayment','تغییر اشتراک یا روش پرداخت'),
        action('fixtureUnknown','نمایش نتیجه نامشخص'),action('fixtureFailed','نمایش نتیجه ناموفق'),action('fixtureSuccess','نمایش پاسخ تأییدشده آزمایشی')]});
  }
  function result(status) {
    return envelope({kind:'result',title:status==='success' ? 'پاسخ آزمایشی: پرداخت تأیید شد' : status==='unknown' ? 'وضعیت پرداخت نامشخص است' : 'پرداخت ناموفق یا لغوشده',
      paymentStatus:status,verified:status==='success',description:'این نتیجه صرفاً fixture نمایشی است و تراکنشی انجام نشده است.',
      actions:status==='unknown' ? [action('checkPayment','بررسی وضعیت تراکنش')] : status==='failed' || status==='cancelled' ? [action('continuePayment','تلاش مجدد')] : []});
  }
  return {async request({action:a,data={}}) {
    await new Promise(resolve=>setTimeout(resolve,250));
    if (a==='start') return field();
    if (a==='checkDomain') {
      state.domain=data.value.toLowerCase();
      state.domainStatus=!/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/.test(state.domain) || state.domain==='error.ir' ? 'error' : state.domain==='taken.ir' ? 'unavailable' : 'available';
      return field();
    }
    if (a==='selectTemplate') {state.template=data.template; return advance();}
    if (a==='changeTemplate') {step='template'; return field();}
    if (a==='next') {
      if (step==='domain' && (state.domainStatus!=='available' || data.value!==state.domain)) throw new Error('دامنه تازه را دوباره بررسی کن.');
      state[step]=data.value; return advance();
    }
    if (a==='edit') return envelope({kind:'review',title:'کدام اطلاعات را ویرایش می‌کنی؟',actions:fields.map(f=>action(`edit:${f}`,labels[f]))});
    if (a.startsWith('edit:')) {step=a.slice(5); editing=true; return field();}
    if (a==='createDraft') {draft=true; return envelope({kind:'draft',title:'پیش‌نویس فروشگاهت آماده شد.',draftId:'demo-only',confirmed:true,description:'پاسخ ساخت شبیه‌سازی شده است؛ فروشگاه واقعی ساخته نشده است.',actions:[action('continuePayment','ادامه به پرداخت')]});}
    if (a==='continuePayment' && draft || a==='refreshQuote') return payment();
    if (a==='editPayment') {step='subscription'; editing=false; return field();}
    if (a==='fixtureUnknown') return result('unknown');
    if (a==='fixtureFailed') return result('failed');
    if (a==='fixtureSuccess' || a==='checkPayment') return result('success');
    throw new Error('این اقدام در نمونه در دسترس نیست.');
  }};
}
