"""Inference workers, latest-frame output, and browser session lifecycle."""

import threading
import time
import uuid

import cv2
import torch
from fastapi import HTTPException

from .capture import BrowserCapture, LatestCapture
from .client_audio import ClientAudioBuffer
from .config import Config
from .vision import load_models, process_frame, resolve_device

MODEL_LOAD_LOCK = threading.Lock()


class Engine:
    def __init__(self):
        self.condition = threading.Condition()
        self.generation = 0
        self.active = False
        self.closed = False
        self.config = Config()
        self.phase = "idle"
        self.message = "Choose a source and start the preview."
        self.reader = None
        self.jpeg = None
        self.frame_id = 0
        self.frame_time = 0
        self.metrics = {}
        self.raw_jpeg = None
        self.raw_frame_id = 0
        self.client_audio = ClientAudioBuffer()
        self.public_id = uuid.uuid4().hex
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def apply(self, config):
        # Reject unsupported device requests before interrupting a working stream.
        resolve_device(config.device)
        with self.condition:
            if self.reader:
                self.reader.stop_event.set()
                self.reader.ready.set()
            self.config = config
            self.active = True
            self.generation += 1
            self.client_audio.clear()
            self.phase, self.message = "starting", "Connecting to source…"
            self.jpeg = None
            self.raw_jpeg = None
            self.metrics = {}
            self.condition.notify_all()

    def stop(self):
        with self.condition:
            if self.reader:
                self.reader.stop_event.set()
                self.reader.ready.set()
            self.active = False
            self.client_audio.clear()
            self.generation += 1
            self.phase, self.message = "stopping", "Releasing the camera…"
            self.jpeg = None
            self.raw_jpeg = None
            self.metrics = {}
            self.condition.notify_all()

    def update(self, generation, **values):
        with self.condition:
            if generation != self.generation:
                return False
            for name, value in values.items():
                setattr(self, name, value)
            self.condition.notify_all()
            return True

    def current(self, generation):
        with self.condition:
            return not self.closed and self.active and generation == self.generation

    def run(self):
        handled = -1
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.generation != handled)
                if self.closed:
                    break
                generation, active, config = self.generation, self.active, self.config.model_copy()
                handled = generation
            if not active:
                self.update(generation, phase="idle", message="Preview stopped. Camera released.")
                continue
            reader = BrowserCapture(config) if config.source == "browser" else LatestCapture(config)
            models = None
            try:
                self.reader = reader
                if config.source != "browser":
                    reader.thread.start()
                reader.ready.wait(timeout=10)
                frame, _, _, _, error = reader.snapshot()
                if error or frame is None:
                    raise RuntimeError(
                        error
                        or "No frames arrived. Allow camera access in your browser, or check the source connection."
                    )
                if not self.current(generation):
                    continue
                device = resolve_device(config.device)
                if config.mode != "raw":
                    self.update(
                        generation,
                        phase="loading",
                        message="Loading models. New model sizes download on first use…",
                    )
                    with MODEL_LOAD_LOCK:
                        if not self.current(generation):
                            continue
                        models = load_models(config.mode, config.size, features=config.features)
                if not self.current(generation):
                    continue
                previous_sequence = 0
                previous_end = None
                inference_fps = 0
                while self.current(generation):
                    started = time.perf_counter()
                    frame, sequence, captured, _, error = reader.snapshot()
                    if error:
                        raise RuntimeError(error)
                    if frame is None or sequence == previous_sequence:
                        reader.stop_event.wait(0.01)
                        continue
                    skipped = max(0, sequence - previous_sequence - 1) if previous_sequence else 0
                    previous_sequence = sequence
                    counts = {}
                    infer_start = time.perf_counter()
                    if models is None:
                        annotated = frame
                        inference_ms = 0
                    else:
                        annotated, results = process_frame(
                            models,
                            frame,
                            config.confidence,
                            config.imgsz,
                            device,
                            config.boxes,
                            retina_masks=False,
                            quantize=16 if device != "cpu" else 32,
                            detection="detect" in config.features,
                        )
                        inference_ms = (time.perf_counter() - infer_start) * 1000
                        counts = {task: len(result.boxes) for task, result in results.items()}
                    height, width = annotated.shape[:2]
                    if width > config.preview_width:
                        annotated = cv2.resize(
                            annotated,
                            (
                                config.preview_width,
                                max(1, round(height * config.preview_width / width)),
                            ),
                            interpolation=cv2.INTER_AREA,
                        )
                    ok, encoded = cv2.imencode(
                        ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, config.quality]
                    )
                    if not ok:
                        raise RuntimeError("Could not encode the preview frame.")
                    finished = time.perf_counter()
                    if previous_end is not None:
                        measured = 1 / max(finished - previous_end, 0.0001)
                        inference_fps = (
                            measured if not inference_fps else 0.8 * inference_fps + 0.2 * measured
                        )
                    previous_end = finished
                    metrics = {
                        "processing_fps": round(inference_fps, 1),
                        "inference_ms": round(inference_ms),
                        "frame_age_ms": round((finished - captured) * 1000),
                        "resolution": f"{width} × {height}",
                        "device": device,
                        "counts": counts,
                        "skipped_frames": skipped,
                        "jpeg_kb": round(len(encoded) / 1024, 1),
                    }
                    with self.condition:
                        next_id = self.frame_id + 1
                    if not self.update(
                        generation,
                        jpeg=encoded.tobytes(),
                        frame_id=next_id,
                        frame_time=finished,
                        metrics=metrics,
                        phase="running",
                        message="Live · newest frames only",
                    ):
                        break
                    reader.stop_event.wait(max(0, 1 / config.max_fps - (finished - started)))
            except Exception as exc:
                self.update(generation, phase="error", message=str(exc), jpeg=None, raw_jpeg=None)
            finally:
                try:
                    reader.close()
                except Exception as exc:
                    self.update(generation, phase="error", message=str(exc))
                self.reader = None
                models = None
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    def status(self):
        with self.condition:
            metrics = dict(self.metrics)
            if self.frame_time and self.jpeg:
                metrics["preview_age_ms"] = round((time.perf_counter() - self.frame_time) * 1000)
            if self.reader:
                _, _, _, fps, _ = self.reader.snapshot()
                metrics["capture_fps"] = round(fps, 1)
            return {
                "phase": self.phase,
                "message": self.message,
                "config": self.config.model_dump(),
                "metrics": metrics,
                "frame_id": self.frame_id,
                "generation": self.generation,
            }

    def upload(self, frame, generation, raw_jpeg=None):
        with self.condition:
            if not self.active or self.config.source != "browser" or generation != self.generation:
                return False
            reader = self.reader
            if not isinstance(reader, BrowserCapture) or reader.stop_event.is_set():
                return False
            reader.push(frame)
            self.raw_jpeg = (
                bytes(raw_jpeg) if self.config.share_with_operator and raw_jpeg else None
            )
            self.raw_frame_id += 1
            return True

    def shutdown(self):
        with self.condition:
            self.closed = True
            self.client_audio.clear()
            if self.reader:
                self.reader.stop_event.set()
                self.reader.ready.set()
            self.generation += 1
            self.condition.notify_all()
        self.thread.join(timeout=15)


class Sessions:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = {}

    def get(self, identifier):
        with self.lock:
            if identifier not in self.items:
                identifier = uuid.uuid4().hex
                if len(self.items) >= 32:
                    raise HTTPException(
                        status_code=503, detail="Too many active browser sessions. Try again later."
                    )
                self.items[identifier] = (Engine(), time.monotonic())
            engine, _ = self.items[identifier]
            self.items[identifier] = (engine, time.monotonic())
            return identifier, engine

    def prune(self, all_sessions=False):
        with self.lock:
            expired = [
                key
                for key, (_, touched) in self.items.items()
                if all_sessions or time.monotonic() - touched > 90
            ]
            engines = [self.items.pop(key)[0] for key in expired]
        for engine in engines:
            engine.shutdown()
