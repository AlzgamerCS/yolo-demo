"""Synthetic PCM playback and listener controls; never opens a real microphone."""

import argparse
import json
import struct
import time

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            is_mobile=True, has_touch=True, viewport={"width": 390, "height": 844}
        )
        page = context.new_page()
        state = page.request.get(base + "/api/status").json()
        state.update(phase="running", generation=1)
        state["config"]["source"] = "laptop"
        page.route("**/api/status", lambda route: route.fulfill(json=state))
        page.route(
            "**/api/audio/devices",
            lambda route: route.fulfill(
                json={
                    "available": True,
                    "devices": [{"value": "1", "label": "Synthetic input"}],
                    "error": "",
                }
            ),
        )
        # Count actual Web Audio scheduling, rather than checking only button text.
        page.add_init_script("""window.scheduledAudio = 0;
          const original = AudioContext.prototype.createBufferSource;
          AudioContext.prototype.createBufferSource = function() {
            const node = original.call(this), start = node.start.bind(node);
            node.start = (...args) => { window.scheduledAudio++; return start(...args); };
            return node;
          };""")
        closed = []
        connections = []

        def audio(socket):
            connections.append(socket)
            socket.on_close(lambda *args: closed.append(True))
            socket.send(json.dumps({"sample_rate": 16000, "channels": 1, "format": "s16le"}))
            socket.send(struct.pack("<320h", *([1000, -1000] * 160)))

        page.route_web_socket("**/api/audio", audio)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base)
            page.wait_for_function("!document.getElementById('listenAudio').disabled")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#listenAudio").tap()
            page.wait_for_function("window.scheduledAudio > 0")
            assert page.locator("#audioLevel").evaluate("element => element.value") > 0
            assert "Input signal received" in page.locator("#audioStatus").inner_text()
            assert page.locator("#listenAudio").get_attribute("aria-pressed") == "true"
            # Connected silence must be reported as silence, not successful listening.
            until = time.monotonic() + 2.3
            while time.monotonic() < until:
                connections[-1].send(bytes(640))
                page.wait_for_timeout(50)
            assert "Microphone is silent" in page.locator("#audioStatus").inner_text()
            assert page.locator("#audioLevel").evaluate("element => element.value") == 0
            page.locator("#listenAudio").tap()
            assert page.locator("#listenAudio").get_attribute("aria-pressed") == "false"
            page.locator("#listenAudio").tap()
            page.wait_for_function("window.scheduledAudio > 1")
            page.locator('[data-source="browser"]').tap()
            assert page.locator("#audioPanel").is_hidden()
            assert page.locator("#listenAudio").get_attribute("aria-pressed") == "false"
            page.wait_for_timeout(100)
            assert len(closed) >= 2, "Mute/source change did not close the audio socket"
            page.locator('[data-source="laptop"]').tap()
            page.locator("#testSpeaker").tap()
            assert "test tone" in page.locator("#audioStatus").inner_text()
            assert not errors, errors
            print(
                "PASS: PCM playback, signal meter, silent-input warning, speaker test, Mute, source-change cleanup; synthetic audio only."
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
