"""Check public preview links; HTTP availability is not registration availability."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import httpx

root = Path(__file__).resolve().parents[1]
samples = json.loads((root/'content/public-template-evidence.json').read_text(encoding='utf8'))['samples']

def check(row):
    result = {'label':row['title'], 'url':row.get('demoHref'), 'registration':'unverified'}
    if row['hidden'] or not row.get('demoHref'):
        return {**result,'status':'NOT_RUN','reason':'hidden or no public preview link'}
    try:
        response = httpx.get(row['demoHref'],follow_redirects=True,timeout=25)
        title = re.search(r'<title[^>]*>(.*?)</title>',response.text,re.S)
        return {**result,'status':'PASS' if response.status_code==200 else 'FAIL',
                'http':response.status_code,'pageTitle':title.group(1) if title else None}
    except httpx.HTTPError as error:
        return {**result,'status':'NOT_RUN','reason':type(error).__name__}

with ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(check,samples))
(root/'artifacts/review/preview-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print({state:sum(r['status']==state for r in results) for state in ('PASS','FAIL','NOT_RUN')})
