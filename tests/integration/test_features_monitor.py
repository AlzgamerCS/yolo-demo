"""Feature combinations and opt-in local operator viewing with sample footage."""
import argparse
import time
import cv2
import requests
from ultralytics.utils import ASSETS
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.port}'
    client, operator = requests.Session(), requests.Session()
    config = client.get(base + '/api/status', timeout=5).json()['config']
    image = cv2.imread(str(ASSETS / 'bus.jpg'))
    ok, jpeg = cv2.imencode('.jpg', image)
    assert ok
    config.update(source='browser', device='cpu', share_with_operator=True)

    def apply(features):
        config['features'] = features
        response = client.post(base + '/api/config', json=config, timeout=5)
        assert response.status_code == 200, response.text
        generation = response.json()['generation']
        for _ in range(100):
            upload = client.post(base + '/api/browser-frame', params={'generation': generation}, data=jpeg.tobytes(), headers={'Content-Type': 'image/jpeg'}, timeout=5)
            assert upload.status_code in (204, 409)
            status = client.get(base + '/api/status', timeout=5).json()
            assert status['phase'] != 'error', status['message']
            if status['phase'] == 'running':
                return status
            time.sleep(.05)
        raise AssertionError('Feature combination did not start')

    try:
        for features, counts in [(['detect', 'pose'], {'detect', 'pose'}), (['segment'], {'segment'}), (['segment', 'pose'], {'segment', 'pose'}), (['detect', 'segment', 'pose'], {'segment', 'pose'})]:
            state = apply(features)
            assert set(state['metrics']['counts']) == counts
            assert all(count > 0 for count in state['metrics']['counts'].values())
        if client.get(base + '/api/options', timeout=5).json()['gpu_available']:
            config['device'] = '0'
            state = apply(['detect', 'segment', 'pose'])
            assert state['metrics']['device'] == '0'
        sessions = operator.get(base + '/api/operator/sessions', timeout=5).json()['sessions']
        assert len(sessions) == 1, sessions
        watch_id = sessions[0]['id']
        raw = operator.get(base + f'/api/operator/frame/{watch_id}', timeout=5)
        assert raw.status_code == 200 and raw.content == jpeg.tobytes(), 'Raw monitor did not show original client JPEG'
        processed = operator.get(base + f'/api/operator/frame/{watch_id}?kind=processed', timeout=5)
        assert processed.status_code == 200 and processed.content != raw.content
        for path in ('/monitor', '/api/operator/sessions', f'/api/operator/frame/{watch_id}'):
            assert operator.get(base + path, headers={'Host': 'remote.trycloudflare.com'}, timeout=5).status_code == 403
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/monitor')
            page.locator('#feed').wait_for(state='visible', timeout=10000)
            page.locator('#kind').select_option('processed')
            page.locator('#feed').wait_for(state='visible', timeout=10000)
            assert page.locator('#feed').evaluate("element => getComputedStyle(element).objectFit") == 'contain'
            assert not errors, errors
            browser.close()
        config['share_with_operator'] = False
        response = client.post(base + '/api/config', json=config, timeout=5)
        assert response.status_code == 200
        assert operator.get(base + f'/api/operator/frame/{watch_id}', timeout=5).status_code == 403
        assert operator.get(base + '/api/operator/sessions', timeout=5).json()['sessions'] == []
        print('PASS: feature combinations, CPU/GPU quantize, original/annotated monitor, consent revocation, localhost restriction, operator browser UI.')
    finally:
        client.post(base + '/api/stop', json={}, timeout=5)


if __name__ == '__main__':
    main()
