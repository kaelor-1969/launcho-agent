"""Exercise the running local FastAPI services; never calls a model or live API."""
import concurrent.futures
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta, timezone
import sys
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
results = []


def record(name, inputs, actual, passed):
    results.append(dict(test=name, input=inputs, actual=actual, status='PASS' if passed else 'FAIL'))


def main():
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=30) as client:
        session = client.post('/api/sessions', json={}).json()
        assert session['adapterMode'] == 'local_mock'
        headers = {'X-Session-Token': session['sessionToken']}
        base = '/api/sessions/' + session['sessionId']
        prefs = dict(kind='shop', businessName='روزا', category='mock-bags-shoes',
                     template='mock-classic', planMonths=3, domain={'label': 'roza', 'tld': 'ir'})
        saved = client.patch(base+'/preferences', headers=headers,
                             json={'revision': session['revision'], 'preferences': prefs})
        saved.raise_for_status()
        review = client.post(base+'/review', headers=headers, json={'revision': saved.json()['revision']}).json()
        body = {k: review[k] for k in ('revision', 'reviewId', 'confirmationToken')}
        body['confirmed'] = True
        def confirm():
            return client.post(base+'/confirm', headers=headers, json=body)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda _: confirm(), range(2)))
        retry = confirm()
        ref = retry.json().get('ref')
        record('concurrent confirmation and replay', prefs,
               {'statuses': [r.status_code for r in responses], 'retry': retry.status_code,
                'same_ref': all(r.status_code in (200, 201, 409) and
                               (r.status_code == 409 or r.json().get('ref') == ref) for r in responses)},
               bool(ref) and all(r.status_code in (200, 201, 409) and
                               (r.status_code == 409 or r.json().get('ref') == ref) for r in responses))
        # Discard a completed HTTP response to simulate loss of acknowledgement after commit.
        confirm().close()
        replay = confirm()
        record('lost acknowledgement then retry', 'discard response, repeat exact confirmation',
               {'status': replay.status_code, 'same_ref': replay.json().get('ref') == ref},
               replay.status_code == 200 and replay.json().get('ref') == ref)
        website = client.post('/api/sessions', json={}).json()
        website_headers = {'X-Session-Token':website['sessionToken']}
        website_base = '/api/sessions/'+website['sessionId']
        website_prefs = {**prefs,'kind':'website','category':'mock-website-company',
                         'template':'mock-website-classic'}
        saved = client.patch(website_base+'/preferences',headers=website_headers,
                             json={'revision':website['revision'],'preferences':website_prefs})
        saved.raise_for_status()
        website_review = client.post(website_base+'/review',headers=website_headers,
                                     json={'revision':saved.json()['revision']}).json()
        website_body = {k:website_review[k] for k in ('revision','reviewId','confirmationToken')}
        website_body['confirmed']=True
        created = client.post(website_base+'/confirm',headers=website_headers,json=website_body)
        created.raise_for_status()
        opened = client.get(created.json()['confirmUrl'])
        status = client.get(website_base+'/draft-status',headers=website_headers)
        record('website real HTTP flow',website_prefs,
               {'confirm':created.status_code,'preview':opened.status_code,'state':status.json()},
               opened.status_code==200 and status.json()['status']=='draft')
        for text, expected in [('قیمت چقدره؟', False), ('تعرفه اشتراک چیست؟', False),
                               ('هزینه برام زیاده', True), ('خیلی گرونه', True),
                               ('بودجه‌ام نمی‌رسه', True), ('از پس هزینه برنمیام', True),
                               ('امکان پرداخت اقساطی هست؟', True), ('میشه قسطی پرداخت کنم؟', True),
                               ('گرون نیست، فقط تعرفه را می‌خواهم', False),
                               ('هزینه زیاد نیست، چه امکاناتی دارد؟', False)]:
            s = client.post('/api/sessions', json={}).json()
            h = {'X-Session-Token': s['sessionToken']}
            def chat(message):
                r = client.post('/api/chat', headers=h, json={'sessionId':s['sessionId'],
                                'requestId':str(uuid4()), 'message':message})
                r.raise_for_status()
                return r.json()['reply']
            first = chat(text)
            offered = 'پیشنهاد آزمایشی' in first
            record('financial language', text, first, offered == expected and
                   (not offered or 'برای خرید اعتبار ندارد' in first))
            if offered:
                for _ in range(6):
                    chat('امکانات فروشگاه چیست؟')
                later = chat(text)
                record('no repeat after six turns', text, later, 'پیشنهاد آزمایشی' not in later)
    with httpx.Client(base_url='http://127.0.0.1:8001', trust_env=False) as mock:
        key = 'review-' + str(uuid4())
        h = {'Authorization':'Bearer local-simulation', 'Idempotency-Key':key}
        first = mock.post('/signup-drafts', headers=h, json=prefs)
        repeat = mock.post('/signup-drafts', headers=h, json=prefs)
        conflict = mock.post('/signup-drafts', headers=h, json={**prefs,'planMonths':6})
        record('mock idempotency and conflict', 'same key; same and changed period',
               {'first':first.status_code,'repeat':repeat.status_code,'conflict':conflict.json()},
               first.json() == repeat.json() and conflict.status_code == 409 and
               conflict.json()['error']['code'] == 'idempotency_conflict')
        persistent_key = 'restart-' + str(uuid4())
        persistent = mock.post('/signup-drafts',headers={**h,'Idempotency-Key':persistent_key},json=prefs)
        (ROOT/'artifacts/review/restart-probe.json').write_text(json.dumps({
            'key':persistent_key,'prefs':prefs,'response':persistent.json()},ensure_ascii=False),encoding='utf8')
        ref = first.json()['data']['ref']
        # Change only this disposable test draft to exercise the real HTTP expiry paths.
        with sqlite3.connect(ROOT/'data/mock-drafts.sqlite3') as db:
            db.execute('UPDATE mock_drafts SET expires=? WHERE ref=?',
                       ((datetime.now(timezone.utc)-timedelta(seconds=1)).timestamp(), ref))
        expired = mock.get('/signup-drafts/'+ref, headers=h)
        preview = mock.get('/signup-drafts/'+ref+'/preview')
        repeat = mock.post('/signup-drafts',headers=h,json=prefs)
        record('expired draft', 'expire disposable draft in SQLite',
               {'state':expired.json()['data']['status'],'preview':preview.status_code,'retry':repeat.status_code},
               expired.json()['data']['status']=='expired' and preview.status_code==410 and repeat.status_code==410)
    path = ROOT/'artifacts/review/http-results.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
    for row in results:
        print(row['status'], row['test'], ascii(row['input']))
    return any(row['status']=='FAIL' for row in results)


if __name__ == '__main__':
    if '--replay-after-restart' in sys.argv:
        probe=json.loads((ROOT/'artifacts/review/restart-probe.json').read_text(encoding='utf8'))
        with httpx.Client(trust_env=False) as client:
            response=client.post('http://127.0.0.1:8001/signup-drafts',json=probe['prefs'],headers={
                'Authorization':'Bearer local-simulation','Idempotency-Key':probe['key']})
        passed=response.status_code==201 and response.json()==probe['response']
        (ROOT/'artifacts/review/restart-result.json').write_text(json.dumps({
            'test':'same request after mock restart','status':'PASS' if passed else 'FAIL',
            'http':response.status_code,'same_response':response.json()==probe['response']}),encoding='utf8')
        print('PASS' if passed else 'FAIL','same request after mock restart')
        raise SystemExit(not passed)
    raise SystemExit(main())
