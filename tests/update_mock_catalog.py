"""Import reviewed public examples as LOCAL choices, never registration IDs."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = json.loads((root/'artifacts/review/public-templates.json').read_text(encoding='utf8'))
path = root/'content/launcho-widget-catalog.json'
fixture = json.loads(path.read_text(encoding='utf8'))
shop = fixture['signupOptions']['shop']
recommendations = {
    'moda':['mock-fashion','mock-bags-shoes'], 'bazar':['mock-fashion','mock-bags-shoes'],
    'parand':['mock-fashion','mock-handicrafts','mock-carpets'],
    'techno':['mock-digital','mock-tools','mock-industrial'],
    'digikala':['mock-digital','mock-supermarket','mock-groceries'],
    'yas':['mock-beauty'], 'hamdam':['mock-pets'],
    'zarin':['mock-jewelry','mock-accessories'], 'golbarg':['mock-jewelry'],
    'kashane':['mock-home-appliances','mock-home-decor'],
    'yadak':['mock-automotive'], 'negah':['mock-accessories','mock-medical'],
}
templates = []
for row in rows:
    # A hidden or preview-less marketing entry is not silently made selectable.
    if row.get('hidden') or not row.get('demoHref'):
        continue
    templates.append(dict(id='mock-'+row['id'], label=row['title'], available=True,
                          previewUrl=row['demoHref'], title=row['title'], kind='shop',
                          approvalStatus='test_only', source=shop['source'],
                          reviewedAt=shop['reviewedAt'], compatibleCategoryIds=None,
                          recommendedFor=recommendations.get(row['id'], [])))
classic = next(t for t in templates if t['id']=='mock-classic')
classic['generalFallback'] = True
classic['recommendedFor'] = [c['id'] for c in shop['businessCategories']
                             if not any(c['id'] in values for values in recommendations.values())]
shop['templates'] = [classic] + [t for t in templates if t is not classic]
shop['notice'] = 'این فهرست نمایندهٔ گزینه‌های سایت واقعی نیست. انتخاب‌ها فقط برای mock محلی‌اند. نمونهٔ عمومی، تأیید گزینهٔ ثبت واقعی نیست. پیشنهاد صنف صرفاً راهنمای توسعه است؛ کلاسیک مسیر عمومی همهٔ اصناف است.'
path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2)+'\n',encoding='utf8')
evidence = [{k:row[k] for k in ('id','title','demoHref') if k in row} |
            {'hidden':bool(row.get('hidden')), 'registrationAvailability':'unverified'} for row in rows]
(root/'content/public-template-evidence.json').write_text(json.dumps({
    'source':'https://launcho.ir/#templates','reviewedAt':'2026-11-12','samples':evidence
},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Imported',len(templates),'public samples as local mock choices; 27 categories have specific or general recommendations.')
