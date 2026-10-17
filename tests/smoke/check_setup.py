"""Verify nano detection, segmentation, pose, composition, and display geometry."""

import argparse

import cv2
import numpy as np
import torch
from ultralytics.utils import ASSETS

from yolo_studio.vision import fit_frame, load_models, process_frame, resolve_device


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    device = resolve_device(args.device)
    frame = cv2.imread(str(ASSETS / "bus.jpg"))
    if frame is None:
        raise RuntimeError("Bundled test image is missing.")
    models = load_models("detect", "n")
    models.update(load_models("all", "n"))
    annotated, results = process_frame(models, frame, 0.35, 480, device)
    assert len(results["detect"].boxes) > 0, "No detections on sample image"
    assert results["segment"].masks is not None and len(results["segment"].masks) > 0, (
        "No segmentation masks"
    )
    assert results["pose"].keypoints is not None and len(results["pose"].keypoints) > 0, (
        "No human poses"
    )
    assert results["pose"].keypoints.data.shape[1] == 17, "Expected 17 human keypoints"
    assert annotated.shape == frame.shape, "Overlay changed capture dimensions"
    # A white 16:9 source in a square view must retain its entire image with black bars.
    white = np.full((90, 160, 3), 255, dtype=np.uint8)
    square = fit_frame(white, 200, 200)
    assert square.shape == (200, 200, 3)
    assert np.all(square[:43] == 0) and np.all(square[156:] == 0)
    assert np.all(square[44:156] == 255)
    portrait = fit_frame(np.full((160, 90, 3), 255, dtype=np.uint8), 320, 180)
    assert np.all(portrait[:, :109] == 0) and np.all(portrait[:, 210:] == 0)
    assert np.all(portrait[:, 109:210] == 255)
    tiny = fit_frame(white, 1, 1)
    assert tiny.shape == (1, 1, 3)
    # Drawing only masks/keypoints must still preserve frame shape.
    no_boxes, _ = process_frame(
        {k: v for k, v in models.items() if k != "detect"}, frame, 0.35, 480, device, boxes=False
    )
    assert no_boxes.shape == frame.shape
    print(
        f"PASS on {device}: detection, masks, 17-point skeletons, combined overlays, no-boxes, aspect ratio preservation."
    )
    print(f"PyTorch {torch.__version__}; CUDA available: {torch.cuda.is_available()}")


if __name__ == "__main__":
    main()
