// Explicit, in-memory demo fixtures only. Never imported by the live installation.
// Transitions here simulate a SERVER contract, not a second production agent.
export function createDemoWorkflow() {
  const state = {};
  let step = 'businessName', editing = false, revision = 0;
  const sessionId = crypto.randomUUID();
  const fields = ['businessName','category','subscription','template'];
  const labels = {businessName:'نام کسب‌وکار',category:'دسته‌بندی',subscription:'دوره اشتراک',template:'قالب'};
  const plans = [{id:'3',label:'سه‌ماهه'},{id:'6',label:'شش‌ماهه'},{id:'12',label:'سالانه'}];
  const action = (id,label) => ({id,label});
  const envelope = v => ({sessionId, revision:++revision, ...v});
  function review() {
    step = 'review';
    return envelope({kind:'review', title:'مرور اطلاعات',
      rows:[...['businessName','category'].map(f=>({label:labels[f],value:state[f]})),
        {label:labels.subscription,value:plans.find(p=>p.id===state.subscription).label},
        {label:'قالب',value:state.template.name}],
      actions:[action('createDraft','تأیید و ساخت پیش‌نویس نمایشی'),action('edit','ویرایش اطلاعات')]});
  }
  function field() {
    if (step==='template') return envelope({kind:'template',title:'قالب فروشگاهت را انتخاب کن',
      ...(state.template ? {template:state.template} : {}),
      actions:[action('browseTemplates',state.template ? 'تغییر قالب' : 'مشاهده و انتخاب قالب')]});
    return envelope({kind:'field', field:step, label:labels[step], value:state[step] || '',
      title:step==='businessName' ? 'حتماً، قدم‌به‌قدم پیش می‌ریم. اسم کسب‌وکارت چیه؟' : `${labels[step]} را مشخص کن`,
      ...(step==='category' ? {options:[{id:'پوشاک',label:'پوشاک'},{id:'زیبایی',label:'زیبایی'},{id:'سایر',label:'سایر'}]} : {}),
      ...(step==='subscription' ? {options:plans} : {}),
      actions:[action('next','ادامه')]});
  }
  function advance() {
    if (editing) { editing=false; return review(); }
    const index=fields.indexOf(step);
    if (index===fields.length-1) return review();
    step=fields[index+1]; return field();
  }
  return {async request({action:a,data={}}) {
    await new Promise(resolve=>setTimeout(resolve,250));
    if (a==='start' && step==='businessName') return field();
    if (a==='selectTemplate' && step==='template') {state.template=data.template; return advance();}
    if (a==='next' && fields.includes(step) && step!=='template') {
      if (data.field && data.field!==step) throw new Error('این فیلد در مرحلهٔ فعلی پذیرفته نیست.');
      if (step==='subscription' && !plans.some(p=>p.id===data.value)) throw new Error('دوره اشتراک معتبر نیست.');
      state[step]=data.value; return advance();
    }
    if (a==='edit' && step==='review') return envelope({kind:'review',title:'کدام اطلاعات را ویرایش می‌کنی؟',actions:fields.map(f=>action(`edit:${f}`,labels[f]))});
    if (a.startsWith('edit:') && step==='review' && fields.includes(a.slice(5))) {step=a.slice(5); editing=true; return field();}
    if (a==='createDraft' && step==='review') {
      step='draft';
      return envelope({kind:'draft',title:'پیش‌نویس نمایشی آماده شد.',draftId:'demo-only',confirmed:true,
        draftUrl:new URL('./draft-preview.html', import.meta.url).href,
        description:'این لینک یک نمونهٔ ثابت برای بررسی رابط است؛ فروشگاه واقعی ساخته نشده و اطلاعات واردشده در نمونه نمایش داده نمی‌شود.',actions:[]});
    }
    throw new Error('این اقدام در نمونه در دسترس نیست.');
  }};
}
