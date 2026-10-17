"""Touch layout, mobile browser camera, and unsupported-fullscreen fallback."""
import argparse
from playwright.sync_api import sync_playwright
from yolo_studio.paths import ARTIFACTS_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.port}'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
        context = browser.new_context(is_mobile=True, has_touch=True, permissions=['camera'], viewport={'width': 390, 'height': 844})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base)
        page.wait_for_function("document.getElementById('gpuHint').textContent.length > 0")
        try:
            for width, height in [(320, 740), (390, 844), (768, 1024), (844, 390)]:
                page.set_viewport_size({'width': width, 'height': height})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), (width, height)
                assert page.locator('#apply').bounding_box()['height'] >= 44
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('[data-source="browser"]').tap()
            page.locator('#facingMode').select_option('user')
            for feature in ['Detect', 'Segment', 'Pose']:
                page.locator('#feature' + feature).uncheck()
            page.locator('#apply').tap()
            page.locator('#video').wait_for(state='visible', timeout=30000)
            assert page.evaluate('browserStream.getVideoTracks()[0].readyState') == 'live'
            # Exercise the fallback even on browsers that support native fullscreen.
            page.evaluate("Object.defineProperty(document, 'fullscreenEnabled', {value: false, configurable: true})")
            page.locator('#fullscreen').tap()
            assert page.locator('#viewer').evaluate("element => element.classList.contains('expanded')")
            assert page.locator('#video').evaluate("element => getComputedStyle(element).objectFit") == 'contain'
            page.locator('#fullscreen').tap()
            assert not page.locator('#viewer').evaluate("element => element.classList.contains('expanded')")
            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(ARTIFACTS_DIR / 'mobile-touch.png'), full_page=True)
            page.locator('#stop').tap()
            page.wait_for_function('browserStream === null')
            assert not errors, errors
            print('PASS: touch layouts at 320/390/768px and landscape, mobile capture, front/rear controls, fullscreen fallback, Stop.')
        finally:
            page.request.post(base + '/api/stop', data={})
            context.close()
            browser.close()


if __name__ == '__main__':
    main()
