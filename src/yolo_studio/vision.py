"""Shared model selection, inference, overlays, and display geometry."""

from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from .paths import MODELS_DIR

SIZES = {"nano": "n", "small": "s", "medium": "m", "large": "l", "extra-large": "x"}
SUFFIXES = {"detect": "", "segment": "-seg", "pose": "-pose"}


def resolve_device(value):
    if value == "auto":
        return "0" if torch.cuda.is_available() else "cpu"
    if value == "cpu":
        return value
    index = "0" if value in ("gpu", "cuda") else value.removeprefix("cuda:")
    if not index.isdigit():
        raise ValueError("Device must be auto, cpu, gpu, cuda:N, or a GPU index such as 0.")
    if not torch.cuda.is_available() or int(index) >= torch.cuda.device_count():
        raise ValueError(
            f"CUDA GPU {index} is unavailable. Run setup.ps1 -Compute gpu, or use --device cpu."
        )
    return index


def load_models(mode, size, custom_model=None, features=None):
    tasks = ("segment", "pose") if mode == "all" else (mode,)
    if features is not None:
        tasks = (
            ["segment"] if "segment" in features else ["detect"] if "detect" in features else []
        ) + (["pose"] if "pose" in features else [])
    models = {}
    for task in tasks:
        weights = (
            Path(custom_model).expanduser().resolve()
            if custom_model
            else MODELS_DIR / f"yolo26{SIZES.get(size, size)}{SUFFIXES[task]}.pt"
        )
        if custom_model and not weights.is_file():
            raise ValueError(f"Custom model file does not exist: {weights}")
        weights.parent.mkdir(parents=True, exist_ok=True)
        print(f"Loading {task}: {weights.name}", flush=True)
        model = YOLO(str(weights))
        if model.task != task:
            raise ValueError(f"{weights.name} is a {model.task} model; use --mode {model.task}.")
        models[task] = model
    return models


def process_frame(
    models,
    frame,
    confidence,
    imgsz,
    device,
    boxes=True,
    retina_masks=True,
    quantize=None,
    detection=True,
):
    annotated = frame.copy()
    results = {}
    for task, model in models.items():
        result = model.predict(
            frame,
            conf=confidence,
            imgsz=imgsz,
            device=device,
            verbose=False,
            retina_masks=task == "segment" and retina_masks,
            quantize=quantize,
        )[0]
        draw_boxes = (
            boxes
            and detection
            and not (task == "pose" and ("segment" in models or "detect" in models))
        )
        annotated = result.plot(
            img=annotated,
            boxes=draw_boxes,
            labels=draw_boxes,
            masks=task == "segment",
            kpt_line=True,
        )
        results[task] = result
    return annotated, results


def fit_frame(frame, width, height):
    """Fit the entire image in the display area without stretching or cropping."""
    width, height = max(1, width), max(1, height)
    source_height, source_width = frame.shape[:2]
    scale = min(width / source_width, height / source_height)
    target_width = max(1, min(width, round(source_width * scale)))
    target_height = max(1, min(height, round(source_height * scale)))
    resized = cv2.resize(
        frame,
        (target_width, target_height),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )
    canvas = np.zeros((height, width, 3), dtype=frame.dtype)
    left, top = (width - target_width) // 2, (height - target_height) // 2
    canvas[top : top + target_height, left : left + target_width] = resized
    return canvas
