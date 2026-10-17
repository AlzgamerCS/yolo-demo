"""Check browser camera uploads, session isolation, and forwarded HTTPS controls."""

import argparse
import time

import cv2
import numpy as np
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    clients = [requests.Session(), requests.Session()]
    configs = []
    generations = []
    colors = [(30, 60, 210), (210, 60, 30)]
    for client in clients:
        config = client.get(base + "/api/status", timeout=10).json()["config"]
        config.update(features=None, source="browser", mode="raw", device="cpu", max_fps=20)
        configs.append(config)
        result = client.post(base + "/api/config", json=config, timeout=10)
        assert result.status_code == 200, result.text
        generations.append(result.json()["generation"])
    try:
        assert clients[0].cookies.get("yolo_session") != clients[1].cookies.get("yolo_session")
        for index, client in enumerate(clients):
            image = np.full((180, 320, 3), colors[index], dtype=np.uint8)
            ok, jpeg = cv2.imencode(".jpg", image)
            assert ok
            for _ in range(60):
                result = client.post(
                    base + "/api/browser-frame",
                    params={"generation": generations[index]},
                    data=jpeg.tobytes(),
                    headers={"Content-Type": "image/jpeg"},
                    timeout=10,
                )
                assert result.status_code in (204, 409), result.text
                state = client.get(base + "/api/status", timeout=10).json()
                assert state["phase"] != "error", state["message"]
                if state["phase"] == "running":
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("Browser upload never became live")
            received = client.get(base + "/api/frame", timeout=10)
            decoded = cv2.imdecode(np.frombuffer(received.content, np.uint8), cv2.IMREAD_COLOR)
            assert decoded.shape == image.shape
            assert np.max(np.abs(decoded.mean(axis=(0, 1)) - np.array(colors[index]))) < 5
            assert (
                client.post(
                    base + "/api/browser-frame",
                    params={"generation": generations[index] - 1},
                    data=jpeg.tobytes(),
                    headers={"Content-Type": "image/jpeg"},
                    timeout=10,
                ).status_code
                == 409
            )
        clients[0].post(base + "/api/stop", json={}, timeout=10)
        assert clients[1].get(base + "/api/frame", timeout=10).status_code == 200, (
            "One viewer stopped another viewer"
        )
        assert (
            clients[1]
            .post(
                base + "/api/browser-frame",
                params={"generation": generations[1]},
                data=b"not-jpeg",
                headers={"Content-Type": "image/jpeg"},
                timeout=10,
            )
            .status_code
            == 400
        )
        if base.startswith("http://127.0.0.1"):
            proxy = requests.Session()
            headers = {
                "Host": "demo.trycloudflare.com",
                "X-Forwarded-Proto": "https",
                "Origin": "https://demo.trycloudflare.com",
            }
            response = proxy.post(
                base + "/api/config", json=configs[0], headers=headers, timeout=10
            )
            assert response.status_code == 200, (
                "Forwarded HTTPS origin was rejected: " + response.text
            )
            proxy.post(base + "/api/stop", json={}, headers=headers, timeout=10)
        print(
            "PASS: uploaded JPEG decoding, separate viewer frames, independent Stop, stale generation rejection, forwarded HTTPS.",
            flush=True,
        )
        if args.browser:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
                )
                context = browser.new_context(permissions=["camera"])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                page.wait_for_function("document.getElementById('gpuHint').textContent.length > 0")
                page.locator('[data-source="browser"]').click()
                page.locator("#shareOperator").check()
                page.locator("#featureDetect").uncheck()
                page.locator("#featureSegment").uncheck()
                page.locator("#featurePose").uncheck()
                page.locator("#apply").click()
                page.wait_for_function(
                    "document.getElementById('statusBadge').textContent.includes('Live') && document.getElementById('sourceLabel').textContent === 'MY BROWSER CAMERA'",
                    timeout=30000,
                )
                page.locator("#video").wait_for(state="visible", timeout=15000)
                assert page.evaluate("browserStream.getVideoTracks()[0].readyState") == "live"
                assert page.locator("#browserCamera option").count() > 0
                assert (
                    page.request.get(base + "/api/status").json()["config"]["share_with_operator"]
                    is True
                )
                page.locator("#featureDetect").check()
                page.locator("#apply").click()
                page.wait_for_function(
                    "document.getElementById('statusBadge').textContent.includes('Live') && document.getElementById('modeLabel').textContent === 'OBJECT DETECTION'",
                    timeout=45000,
                )
                page.locator("#stop").click()
                page.wait_for_function("browserStream === null")
                page.wait_for_function(
                    "document.getElementById('statusBadge').textContent.includes('Idle')",
                    timeout=15000,
                )
                assert not errors, errors
                browser.close()
                print(
                    "PASS: getUserMedia camera permission/capture, uploaded preview, model switch, track release on Stop.",
                    flush=True,
                )
    finally:
        for client in clients:
            client.post(base + "/api/stop", json={}, timeout=10)


if __name__ == "__main__":
    main()
