"""Measure displayed browser FPS with a synthetic camera; no real footage."""

import argparse
import json

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--mode", default="all", choices=["raw", "detect", "segment", "pose", "all"]
    )
    parser.add_argument(
        "--http", action="store_true", help="Disable WebSocket to compare HTTP fallback"
    )
    parser.add_argument("--seconds", type=int, default=8)
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
        )
        context = browser.new_context(permissions=["camera"])
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if args.http:
            page.add_init_script(
                "window.WebSocket=class {static OPEN=1;constructor(){this.readyState=3;}close(){}}"
            )
        page.goto(args.url)
        page.wait_for_function("document.getElementById('gpuHint').textContent.length > 0")
        page.locator('[data-source="browser"]').click()
        features = {
            "raw": [],
            "detect": ["detect"],
            "segment": ["detect", "segment"],
            "pose": ["pose"],
            "all": ["detect", "segment", "pose"],
        }[args.mode]
        for feature, element in {
            "detect": "featureDetect",
            "segment": "featureSegment",
            "pose": "featurePose",
        }.items():
            page.locator("#" + element).set_checked(feature in features)
        page.locator("#maxFps").fill("20")
        page.locator("#apply").click()
        page.wait_for_function(
            "document.getElementById('statusBadge').textContent.includes('Live')", timeout=45000
        )
        page.locator("#video").wait_for(state="visible", timeout=15000)
        page.wait_for_timeout(2000)
        page.evaluate(
            'window.benchmarkStart=performance.now();window.benchmarkFrames=0;window.benchmarkHandler=()=>window.benchmarkFrames++;document.getElementById("video").addEventListener("load",window.benchmarkHandler)'
        )
        page.wait_for_timeout(args.seconds * 1000)
        result = page.evaluate(
            """async () => ({display_fps: +(window.benchmarkFrames / ((performance.now()-window.benchmarkStart)/1000)).toFixed(1), transport: liveSocket?.readyState===WebSocket.OPEN?'websocket':'http', metrics: (await fetch('/api/status').then(r=>r.json())).metrics})"""
        )
        assert result["display_fps"] > 0, result
        assert not errors, errors
        page.locator("#stop").click()
        browser.close()
        print(
            json.dumps({"url": args.url, "mode": args.mode, **result}, ensure_ascii=True),
            flush=True,
        )


if __name__ == "__main__":
    main()
