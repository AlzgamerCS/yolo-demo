"""Resolve IP Webcam and generic network stream addresses."""

import threading
import time
from collections import deque
from urllib.parse import urlsplit, urlunsplit

import cv2

DEFAULT_PHONE = "http://10.12.48.195:8080"


def network_url(value, phone=False):
    parsed = urlsplit(value)
    supported = ("http", "https") if phone else ("http", "https", "rtsp", "rtsps")
    if parsed.scheme.lower() not in supported:
        if phone:
            raise ValueError("Phone address must start with http:// or https://.")
        return None
    if not parsed.hostname:
        raise ValueError("Stream URL must include a hostname or IP address.")
    if phone and parsed.scheme.lower() == "http" and parsed.port is None:
        parsed = parsed._replace(netloc=parsed.netloc + ":8080")
    if phone and parsed.path in ("", "/"):
        parsed = parsed._replace(path="/video")
    return urlunsplit(parsed)


def open_network_stream(url, timeout_ms=5000):
    # FFmpeg open/read timeouts prevent an offline phone from hanging startup.
    return cv2.VideoCapture(
        url,
        cv2.CAP_FFMPEG,
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            timeout_ms,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            timeout_ms,
        ],
    )


class BrowserCapture:
    """Latest uploaded JPEG from the browser that owns this session."""

    def __init__(self, config):
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.stop_event = threading.Event()
        self.frame = None
        self.sequence = 0
        self.timestamp = 0
        self.fps = 0
        self.error = None
        self.capture_times = deque()

    def push(self, frame):
        now = time.perf_counter()
        with self.lock:
            self.capture_times.append(now)
            while self.capture_times and now - self.capture_times[0] > 1:
                self.capture_times.popleft()
            self.fps = len(self.capture_times)
            self.frame, self.timestamp = frame, now
            self.sequence += 1
        self.ready.set()

    def snapshot(self):
        with self.lock:
            error = self.error
            if self.timestamp and time.perf_counter() - self.timestamp > 15:
                error = "Browser camera stopped sending frames. Click Start / apply to reconnect."
            return self.frame, self.sequence, self.timestamp, self.fps, error

    def close(self):
        self.stop_event.set()
        self.ready.set()


class LatestCapture:
    """Continuously consume input; retain only the most recent decoded frame."""

    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.stop_event = threading.Event()
        self.frame = None
        self.sequence = 0
        self.timestamp = 0
        self.fps = 0
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        cap = None
        try:
            if self.config.source == "laptop":
                import sys

                cap = cv2.VideoCapture(
                    self.config.camera, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
                )
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            else:
                url = network_url(self.config.url.strip(), phone=self.config.source == "phone")
                cap = open_network_stream(url)
            if not cap.isOpened():
                raise RuntimeError(
                    "Could not open video. Check camera access or the phone server, address and Wi-Fi connection."
                )
            previous = None
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                now = time.perf_counter()
                if not ok:
                    raise RuntimeError(
                        "Video disconnected or timed out. Check the source, then click Start / apply."
                    )
                with self.lock:
                    if previous is not None:
                        measured = min(240, 1 / max(now - previous, 0.0001))
                        self.fps = measured if not self.fps else 0.9 * self.fps + 0.1 * measured
                    self.frame, self.timestamp = frame, now
                    self.sequence += 1
                previous = now
                self.ready.set()
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
            self.ready.set()
        finally:
            if cap is not None:
                cap.release()

    def snapshot(self):
        with self.lock:
            return self.frame, self.sequence, self.timestamp, self.fps, self.error

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=6)
        if self.thread.is_alive():
            raise RuntimeError("Capture is still closing. Wait a few seconds and try again.")
