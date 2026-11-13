"""Black-box local core checks; no direct database access or live writes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, trust_env=False, timeout=30) as client:
        assert client.get('/health/live').status_code == 200
        assert client.get('/health/ready').status_code == 200
        for kind, category, template in [('shop', 'mock-bags-shoes', 'mock-classic'),
                                          ('website', 'mock-website-company', 'mock-website-classic')]:
            session = client.post('/api/sessions').json()
            assert session['adapterMode'] == 'local_mock', 'This probe requires local_mock.'
            base = '/api/sessions/' + session['sessionId']
            headers = {'X-Session-Token': session['sessionToken']}
            assert client.get(base).status_code == 404
            prefs = {'kind': kind, 'businessName': 'روزا', 'category': category, 'template': template,
                     'planMonths': 3, 'domain': {'label': 'roza', 'tld': 'ir'}}
            saved = client.patch(base + '/preferences', headers=headers,
                                 json={'revision': 0, 'preferences': prefs})
            saved.raise_for_status()
            assert client.patch(base + '/preferences', headers=headers,
                                json={'revision': 0, 'preferences': prefs}).status_code == 409
            reviewed = client.post(base + '/review', headers=headers, json={'revision': saved.json()['revision']})
            reviewed.raise_for_status()
            review = reviewed.json()
            assert 'draft' not in client.get(base, headers=headers).json()
            body = {key: review[key] for key in ('revision', 'reviewId', 'confirmationToken')}
            body['confirmed'] = True
            def confirm():
                return client.post(base + '/confirm', headers=headers, json=body)
            with ThreadPoolExecutor(2) as pool:
                concurrent = list(pool.map(lambda _: confirm(), range(2)))
            replay = confirm()
            replay.raise_for_status()
            assert replay.json()['replayed'] is True
            assert all(r.status_code == 409 or r.json()['ref'] == replay.json()['ref'] for r in concurrent)
            assert client.get(replay.json()['confirmUrl']).status_code == 200
            assert client.get(base + '/draft-status', headers=headers).json()['status'] == 'draft'
            print(f'PASS: {kind}: ownership, revision, explicit confirmation, concurrent replay, preview, status')
    print('PASS: liveness and readiness')


if __name__ == '__main__':
    main()
