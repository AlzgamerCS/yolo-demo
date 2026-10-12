"""Integration checks against a running dashboard; no real camera required."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from yolo_studio.paths import ARTIFACTS_DIR
import threading
import time

import cv2
import requests
from ultralytics.utils import ASSETS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.port}'
    http = requests.Session()
    image = cv2.imread(str(ASSETS / 'bus.jpg'))
    ok, data = cv2.imencode('.jpg', image)
    assert ok
    jpeg = data.tobytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *values):
            pass

        def do_GET(self):
            if self.path != '/video':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(jpeg)).encode() + b'\r\n\r\n' + jpeg + b'\r\n')
                    self.wfile.flush()
                    time.sleep(1 / 25)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    stream = f'http://127.0.0.1:{fixture.server_port}'

    def status():
        return http.get(base + '/api/status', timeout=5).json()

    def wait_running(timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = status()
            assert state['phase'] != 'error', state['message']
            if state['phase'] == 'running':
                return state
            time.sleep(0.2)
        raise AssertionError('Preview failed to become live')

    try:
        options = http.get(base + '/api/options', timeout=5).json()
        config = status()['config']
        config.update(features=None, source='phone', url=stream, mode='all', size='n', device='cpu', max_fps=5)
        response = http.post(base + '/api/config', json=config, timeout=5)
        assert response.status_code == 200, response.text
        state = wait_running()
        assert state['metrics']['counts']['segment'] > 0 and state['metrics']['counts']['pose'] > 0
        first_id = state['frame_id']
        time.sleep(1)
        state = status()
        assert state['frame_id'] > first_id
        assert state['metrics']['skipped_frames'] > 0, 'Old captured frames were not skipped'
        assert 0 < state['metrics']['processing_fps'] < 8, state['metrics']
        frame = http.get(base + '/api/frame', timeout=5)
        assert frame.status_code == 200 and frame.content.startswith(b'\xff\xd8')
        assert http.get(base + '/api/frame', params={'after': 10**12}, timeout=5).status_code == 204
        old_generation_frame = state['frame_id']
        config.update(mode='raw')
        assert http.post(base + '/api/config', json=config, timeout=5).status_code == 200
        state = wait_running()
        assert state['frame_id'] > old_generation_frame and state['metrics']['inference_ms'] == 0
        rejected = dict(config, device='999')
        assert http.post(base + '/api/config', json=rejected, timeout=5).status_code == 400
        assert status()['config']['mode'] == 'raw', 'Invalid update interrupted active preview'
        assert http.post(base + '/api/config', json=dict(config, source='url', url='not-a-stream'), timeout=5).status_code == 422
        assert http.post(base + '/api/stop', json={}, headers={'Origin': 'https://unrelated.invalid'}, timeout=5).status_code == 403
        if options['gpu_available']:
            config.update(mode='all', device='0')
            assert http.post(base + '/api/config', json=config, timeout=5).status_code == 200
            state = wait_running()
            assert state['metrics']['device'] == '0' and state['metrics']['counts']['pose'] > 0
            print('PASS: combined CPU/GPU inference, phone stream, latest-frame dropping, raw mode, validation, cross-origin rejection.', flush=True)
        else:
            print('PASS: CPU inference, phone stream, latest-frame dropping, raw mode, validation. GPU unavailable.', flush=True)
        if args.browser:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1100})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.context.add_cookies([{'name': 'yolo_session', 'value': http.cookies.get('yolo_session'), 'url': base}])
                page.goto(base)
                page.locator('#video').wait_for(state='visible', timeout=30000)
                page.locator('#fullscreen').click()
                page.wait_for_function('document.fullscreenElement !== null')
                page.keyboard.press('Escape')
                page.wait_for_function('document.fullscreenElement === null')
                page.locator('[data-source="url"]').click()
                page.locator('#url').fill(stream + '/video')
                page.locator('#featureDetect').uncheck()
                page.locator('#featureSegment').uncheck()
                page.locator('#featurePose').check()
                page.locator('[data-size="s"]').click()
                with page.expect_response(lambda response: response.url.endswith('/api/config') and response.request.method == 'POST'):
                    page.locator('#apply').click()
                page.wait_for_function("document.getElementById('statusBadge').textContent.includes('Live') && document.getElementById('modeLabel').textContent === 'HUMAN POSE'", timeout=90000)
                page.locator('#video').wait_for(state='visible', timeout=30000)
                state = status()
                assert state['config']['size'] == 's' and state['config']['mode'] == 'pose' and state['config']['source'] == 'url'
                assert page.locator('#video').evaluate("element => getComputedStyle(element).objectFit") == 'contain'
                ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(ARTIFACTS_DIR / 'dashboard-desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.screenshot(path=str(ARTIFACTS_DIR / 'dashboard-mobile.png'), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile layout overflows'
                page.locator('#stop').click()
                page.wait_for_function("document.getElementById('statusBadge').textContent.includes('Idle')", timeout=20000)
                assert not errors, errors
                browser.close()
                print('PASS: browser source/mode/model controls, fullscreen, aspect ratio, mobile layout, stop, no JS errors.', flush=True)
    finally:
        http.post(base + '/api/stop', json={}, timeout=5)
        deadline = time.monotonic() + 15
        while status()['phase'] == 'stopping' and time.monotonic() < deadline:
            time.sleep(0.1)
        assert status()['phase'] == 'idle', 'Camera was not released after stopping'
        fixture.shutdown()
        fixture.server_close()


if __name__ == '__main__':
    main()
