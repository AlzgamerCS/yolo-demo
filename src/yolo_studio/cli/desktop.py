"""YOLO webcam: object boxes, instance masks, and human skeletons."""

import argparse
import sys
import time
from pathlib import Path

import cv2
import torch

from ..capture import DEFAULT_PHONE, network_url, open_network_stream
from ..desktop_config import DEFAULT_CONFIG, parse_desktop_args
from ..vision import SIZES, fit_frame, load_models, process_frame, resolve_device


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config",
        metavar="PATH",
        help=f"Desktop TOML settings file; automatically loads {DEFAULT_CONFIG} when present",
    )
    config_group.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore settings files and use built-in defaults plus CLI flags",
    )
    parser.add_argument(
        "--mode",
        choices=["detect", "segment", "pose", "all"],
        default="all",
        help="all overlays object masks/boxes and human skeletons",
    )
    parser.add_argument(
        "--size",
        "--model-size",
        choices=list(SIZES) + list(SIZES.values()),
        default="n",
        help="Model size: n/s/m/l/x, from smallest to largest",
    )
    parser.add_argument(
        "--model", help="Custom local .pt weights; requires a single matching --mode"
    )
    parser.add_argument("--camera", type=int, default=0, help="Webcam index")
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--webcam",
        action="store_true",
        help="Use the webcam even if the config specifies phone/source",
    )
    source_group.add_argument(
        "--source", help="Local image/video or HTTP/HTTPS/RTSP stream instead of webcam"
    )
    source_group.add_argument(
        "--phone",
        nargs="?",
        const=DEFAULT_PHONE,
        metavar="URL",
        help="Android IP Webcam base URL; adds /video to a base address. Without URL uses "
        + DEFAULT_PHONE,
    )
    parser.add_argument("--width", type=int, default=1280, help="Requested camera width")
    parser.add_argument("--height", type=int, default=720, help="Requested camera height")
    parser.add_argument(
        "--confidence", type=float, default=0.35, help="Object/person confidence threshold"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=480,
        help="Inference input size; separate from camera/display resolution",
    )
    parser.add_argument(
        "--device", default="auto", help="auto, cpu, gpu, cuda:N, or N (single CUDA GPU index)"
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Start fullscreen; F toggles, Escape leaves fullscreen",
    )
    parser.add_argument(
        "--windowed",
        dest="fullscreen",
        action="store_false",
        default=argparse.SUPPRESS,
        help="Override fullscreen from the config",
    )
    parser.add_argument("--window-width", type=int, default=1280, help="Initial window width")
    parser.add_argument("--window-height", type=int, default=720, help="Initial window height")
    parser.add_argument(
        "--no-boxes",
        action="store_true",
        help="Hide bounding boxes/labels; keep masks and skeletons",
    )
    parser.add_argument(
        "--boxes",
        dest="no_boxes",
        action="store_false",
        default=argparse.SUPPRESS,
        help="Show boxes even if disabled in the config",
    )
    parser.add_argument(
        "--check", action="store_true", help="Process one frame without opening a preview"
    )
    parser.add_argument(
        "--list-devices", action="store_true", help="Report PyTorch CPU/CUDA availability and exit"
    )
    return parser


def main():
    parser = build_parser()
    args = parse_desktop_args(parser)
    if args.list_devices:
        print(
            f"PyTorch {torch.__version__}; CPU: available; CUDA build: {torch.version.cuda}; CUDA available: {torch.cuda.is_available()}"
        )
        for index in range(torch.cuda.device_count()):
            print(f"GPU {index}: {torch.cuda.get_device_name(index)}")
        return
    device = resolve_device(args.device)
    models = load_models(args.mode, args.size, args.model)
    stream_url = (
        network_url(args.phone, phone=True)
        if args.phone
        else (network_url(args.source) if args.source else None)
    )
    local_source = bool(args.source and not stream_url)
    if stream_url:
        cap = open_network_stream(stream_url)
    elif args.source:
        source = Path(args.source).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"Source file does not exist: {source}")
        cap = cv2.VideoCapture(str(source))
    else:
        cap = cv2.VideoCapture(
            args.camera, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        )
    window = "YOLO Webcam | F: fullscreen | Q: quit"
    fullscreen = args.fullscreen
    try:
        if not cap.isOpened():
            if stream_url:
                raise RuntimeError(
                    "Cannot connect to the network video stream. Start the phone camera server, check the address/port and same-Wi-Fi access, and open its /video URL in a browser. If authentication is enabled, use a stream URL with credentials."
                )
            raise RuntimeError(
                "Cannot open source. Close other camera apps, check camera permissions, or try --camera 1."
            )
        if not args.source and not args.phone:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        if not args.check:
            cv2.namedWindow(window, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
            cv2.resizeWindow(window, args.window_width, args.window_height)
            if fullscreen:
                cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        print(
            f"Mode {args.mode}; size {args.size}; device {device}. F: fullscreen; Q: quit.",
            flush=True,
        )
        reported_capture = False
        preview_shown = False
        while True:
            start = time.perf_counter()
            ok, frame = cap.read()
            if not ok:
                if local_source and reported_capture:
                    break
                if stream_url:
                    raise RuntimeError(
                        "Network stream stopped or timed out. Keep the phone camera server running and check Wi-Fi, then restart the demo."
                    )
                raise RuntimeError(
                    "No frame received. Check camera shutter and permissions, or the source file."
                )
            if not reported_capture:
                print(f"Capture: {frame.shape[1]}x{frame.shape[0]}.", flush=True)
                reported_capture = True
            annotated, results = process_frame(
                models, frame, args.confidence, args.imgsz, device, not args.no_boxes
            )
            if args.check:
                for task, result in results.items():
                    print(
                        f"{task}: {len(result.boxes)} objects; masks: {0 if result.masks is None else len(result.masks)}; poses: {0 if result.keypoints is None else len(result.keypoints)}",
                        flush=True,
                    )
                print("Frame check passed.", flush=True)
                return
            fps = 1 / max(time.perf_counter() - start, 1e-6)
            cv2.putText(
                annotated,
                f"{args.mode} | {device} | {fps:.1f} FPS | F: fullscreen | Q: quit",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )
            if preview_shown and cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
            _, _, display_width, display_height = cv2.getWindowImageRect(window)
            cv2.imshow(
                window,
                fit_frame(
                    annotated,
                    display_width or args.window_width,
                    display_height or args.window_height,
                ),
            )
            preview_shown = True
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")) or (key == 27 and not fullscreen):
                break
            if key in (ord("f"), ord("F")) or (key == 27 and fullscreen):
                fullscreen = not fullscreen
                cv2.setWindowProperty(
                    window,
                    cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL,
                )
                if not fullscreen:
                    cv2.resizeWindow(window, args.window_width, args.window_height)
    finally:
        cap.release()
        cv2.destroyAllWindows()


def run():
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
