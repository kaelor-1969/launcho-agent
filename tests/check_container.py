"""Exercise the built image, persistent volumes and restart over real HTTP."""
import argparse
import subprocess
import time
from uuid import uuid4

import httpx


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True, text=True).stdout.strip()


def wait_ready(client):
    for _ in range(60):
        try:
            if client.get('/health/ready').status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(1)
    raise RuntimeError('Container readiness timed out.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='launcho-agent:ci')
    args = parser.parse_args()
    prefix = 'launcho-test-' + uuid4().hex[:10]
    mock, agent = prefix + '-mock', prefix + '-agent'
    volumes = [prefix + '-sessions', prefix + '-drafts']
    try:
        for volume in volumes:
            docker('volume', 'create', volume)
        # Sharing a network namespace preserves the adapter's loopback-only mock policy.
        docker('run', '-d', '--name', mock, '--no-healthcheck', '-p', '127.0.0.1::8000',
               '-v', volumes[1] + ':/app/data', '-e', 'LAUNCHO_MOCK_DRAFT_DB=/app/data/drafts.sqlite3',
               args.image, 'uvicorn', 'app.mock_launcho:app', '--host', '0.0.0.0', '--port', '8001', '--no-access-log')
        docker('run', '-d', '--name', agent, '--network', 'container:' + mock,
               '-v', volumes[0] + ':/app/data', '-e', 'LAUNCHO_MOCK_URL=http://127.0.0.1:8001',
               '-e', 'AI_API_KEY=', '-e', 'AI_MODEL_NAME=', '-e', 'AI_BASE_URL=https://example.invalid/v1',
               args.image)
        port = docker('port', mock, '8000/tcp').rsplit(':', 1)[1]
        url = 'http://127.0.0.1:' + port
        with httpx.Client(base_url=url, timeout=15, trust_env=False) as client:
            wait_ready(client)
            subprocess.run(['python', 'tests/check_backend_http.py', '--url', url], check=True)
            owner = client.post('/api/sessions').json()
            base = '/api/sessions/' + owner['sessionId']
            headers = {'X-Session-Token': owner['sessionToken']}
            saved = client.patch(base + '/preferences', headers=headers,
                                 json={'revision': 0, 'preferences': {
                                     'businessName': 'Persistence test', 'category': 'mock-bags-shoes',
                                     'template': 'mock-classic', 'planMonths': 3,
                                     'domain': {'label': 'persistence', 'tld': 'ir'}}})
            saved.raise_for_status()
            review_response = client.post(base + '/review', headers=headers,
                                          json={'revision': saved.json()['revision']})
            review_response.raise_for_status()
            review = review_response.json()
            confirmation = {key: review[key] for key in ('revision', 'reviewId', 'confirmationToken')}
            confirmation['confirmed'] = True
            created = client.post(base + '/confirm', headers=headers, json=confirmation)
            created.raise_for_status()
            docker('stop', agent)
            docker('restart', mock)
            docker('start', agent)
            wait_ready(client)
            recovered = client.get(base, headers=headers)
            recovered.raise_for_status()
            assert recovered.json()['preferences'] == saved.json()['preferences']
            replay = client.post(base + '/confirm', headers=headers, json=confirmation)
            replay.raise_for_status()
            assert replay.json()['ref'] == created.json()['ref']
            assert replay.json()['replayed'] is True
            assert client.get(base + '/draft-status', headers=headers).json()['status'] == 'draft'
            assert docker('exec', agent, 'id', '-u') != '0'
            print('PASS: both containers restarted, session and draft persisted, same confirmation replayed, non-root user and readiness')
    finally:
        for container in (agent, mock):
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        for volume in volumes:
            subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


if __name__ == '__main__':
    main()
