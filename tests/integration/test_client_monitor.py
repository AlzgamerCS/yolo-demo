"""Two synthetic browser cameras/microphones, grid monitoring, and live muting."""

import argparse

from playwright.sync_api import expect, sync_playwright

from yolo_studio.paths import ARTIFACTS_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
        )
        contexts, pages, errors = [], [], []
        operator = browser.new_context()
        monitor = operator.new_page()
        monitor.on("pageerror", lambda error: errors.append(str(error)))
        try:
            for _ in range(2):
                context = browser.new_context(permissions=["camera", "microphone"])
                contexts.append(context)
                page = context.new_page()
                pages.append(page)
                page.add_init_script("""window.capturedMicrophones = [];
                  const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                  navigator.mediaDevices.getUserMedia = async (constraints) => {
                    const stream = await original(constraints);
                    window.capturedMicrophones.push(...stream.getAudioTracks());
                    return stream;
                  };""")
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                page.wait_for_function("document.getElementById('gpuHint').textContent.length > 0")
                expect(page.locator("#shareOperator")).to_be_checked()
                expect(page.locator("#shareAudio")).to_be_checked()
                page.locator('[data-source="browser"]').click()
                for name in ["Detect", "Segment", "Pose"]:
                    page.locator("#feature" + name).uncheck()
                page.locator("#apply").click()
                page.locator("#video").wait_for(state="visible", timeout=30000)
                page.wait_for_function(
                    "document.getElementById('clientAudioStatus').textContent.includes('Microphone shared')",
                    timeout=15000,
                )
            monitor.goto(base + "/monitor")
            expect(monitor.locator(".client-card")).to_have_count(2, timeout=15000)
            monitor.wait_for_function(
                "Array.from(document.querySelectorAll('.client-card img')).every(image => image.naturalWidth > 1)"
            )
            monitor.locator("#feed").wait_for(state="visible")
            ids = monitor.locator("#client option").evaluate_all(
                "options => options.map(option => option.value)"
            )
            monitor.locator("#clientListen").click()
            monitor.wait_for_function(
                "document.getElementById('clientAudioState').textContent.includes('Playing')",
                timeout=15000,
            )
            assert monitor.evaluate("player.nextTime > 0")
            monitor.locator("#client").select_option(ids[1])
            expect(monitor.locator("#clientListen")).to_have_text("Listen to client")
            monitor.locator("#clientListen").click()
            monitor.wait_for_function(
                "document.getElementById('clientAudioState').textContent.includes('Playing')",
                timeout=15000,
            )
            monitor.locator("#clientListen").click()
            assert monitor.evaluate("audioSocket === null")
            # Client muting releases only its microphone; inference/video generation stays intact.
            before = pages[0].request.get(base + "/api/status").json()
            pages[0].locator("#shareAudio").uncheck()
            pages[0].wait_for_function(
                "capturedMicrophones.every(track => track.readyState === 'ended')"
            )
            state = pages[0].request.get(base + "/api/status").json()
            assert (
                not state["config"]["share_audio"] and state["generation"] == before["generation"]
            )
            assert pages[0].evaluate("browserStream.getVideoTracks()[0].readyState") == "live"
            expect(monitor.locator(".client-card")).to_have_count(2)
            # Unmute, then disable all operator sharing immediately, without Apply.
            pages[0].locator("#shareAudio").check()
            pages[0].wait_for_function(
                "document.getElementById('clientAudioStatus').textContent.includes('Microphone shared')"
            )
            pages[0].locator("#shareOperator").uncheck()
            expect(monitor.locator(".client-card")).to_have_count(1, timeout=10000)
            pages[0].wait_for_function(
                "capturedMicrophones.every(track => track.readyState === 'ended')"
            )
            assert pages[1].evaluate("browserStream.getVideoTracks()[0].readyState") == "live"
            # Re-enable the first client to verify both tiles return.
            pages[0].locator("#shareOperator").check()
            expect(monitor.locator(".client-card")).to_have_count(2, timeout=10000)
            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            monitor.screenshot(
                path=str(ARTIFACTS_DIR / "monitor-multiple-clients.png"), full_page=True
            )
            monitor.set_viewport_size({"width": 390, "height": 844})
            assert monitor.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            for page in pages:
                page.locator("#stop").click()
                page.wait_for_function(
                    "capturedMicrophones.every(track => track.readyState === 'ended')"
                )
            expect(monitor.locator(".client-card")).to_have_count(0, timeout=10000)
            # Denying microphone permission must leave camera capture/inference usable.
            denied_context = browser.new_context(permissions=["camera"])
            contexts.append(denied_context)
            denied = denied_context.new_page()
            pages.append(denied)
            denied.on("pageerror", lambda error: errors.append(str(error)))
            denied.add_init_script("""const realMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
              navigator.mediaDevices.getUserMedia = (constraints) => constraints.audio
                ? Promise.reject(new DOMException('Microphone permission denied', 'NotAllowedError'))
                : realMedia(constraints);""")
            denied.goto(base)
            denied.wait_for_function("document.getElementById('gpuHint').textContent.length > 0")
            denied.locator('[data-source="browser"]').click()
            for name in ["Detect", "Segment", "Pose"]:
                denied.locator("#feature" + name).uncheck()
            denied.locator("#apply").click()
            denied.locator("#video").wait_for(state="visible", timeout=15000)
            denied.wait_for_function(
                "document.getElementById('clientAudioStatus').textContent.includes('Microphone unavailable')"
            )
            assert denied.evaluate("browserStream.getVideoTracks()[0].readyState") == "live"
            denied.locator("#stop").click()
            assert not errors, errors
            print(
                "PASS: default video/mic sharing, two live video tiles, client audio playback, focus switching, immediate mic/video revocation, isolated Stop."
            )
        finally:
            for page in pages:
                page.request.post(base + "/api/stop", data={})
            for context in contexts:
                context.close()
            operator.close()
            browser.close()


if __name__ == "__main__":
    main()
