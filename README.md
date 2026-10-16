# YOLO Studio

Local computer vision with a browser dashboard and a desktop webcam preview.
Supports object detection, instance segmentation, human pose, browser/server
cameras, Android IP Webcam, and network video streams. Inference runs on the
backend laptop's CPU or NVIDIA GPU.

## Quick start (Windows)

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the project root:

```powershell
# Fresh CPU installation:
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Compute cpu
# Or install CUDA support for a compatible NVIDIA GPU:
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Compute gpu

# Start the browser dashboard:
.\start-web.cmd
# In a second terminal, publish a temporary HTTPS link:
.\start-tunnel.cmd
```

Local dashboard: **http://127.0.0.1:8765**.
Local client monitor: **http://127.0.0.1:8765/monitor**.
The tunnel prints its public URL. Anyone with that URL can use the dashboard
unless you enable its optional email restriction.

For an existing environment, install the editable package without replacing
its installed PyTorch CPU/GPU build:

```powershell
uv pip install --python .venv-system\Scripts\python.exe -e .
```

Root commands are stable entry points; their implementations live in `scripts/`.
Use Ctrl+C for services started in a terminal. `stop-web.cmd` and
`stop-tunnel.cmd` stop their recorded background instances.

## Project layout

```text
src/yolo_studio/       Installable Python application
  web/                HTTP interface and bundled browser assets
    app.py            Application assembly and router registration
    lifecycle.py      Session startup and shutdown
    middleware.py     Session cookies and same-origin controls
    routes/           Pages, controls, streaming, local operator access
    templates/        Dashboard and monitor HTML
    static/           Browser JavaScript and CSS
  cli/                Web-server and desktop command implementations
  config.py           Validated per-session settings
  capture.py          Camera/network readers and browser frames
  vision.py           Model loading, inference, and annotation
  engine.py           Inference workers and browser sessions
  paths.py            Packaged assets and writable runtime locations
  app.py              Compatibility ASGI import
  server.py           Compatibility web command
  desktop.py          Compatibility desktop command
scripts/              Windows launch/setup/tunnel scripts
scripts/python/       PyTorch installer and performance benchmark
tests/                Smoke and integration checks
docs/                 Usage reference and architecture notes
runtime/              Generated weights, logs, PID files, screenshots (ignored)
```

`pyproject.toml` declares the installable package and command-line entry points.
`requirements.txt` provides runtime dependencies; `requirements-dev.txt` adds
browser-test tooling. `requirements-lock.txt` is a snapshot of the working
machine's installed dependencies, excluding the editable project itself.
PyTorch build selection remains explicit in the setup script; the snapshot is
not a substitute for choosing the correct CPU/CUDA installation.

## Development

The package uses a `src` layout. Install it editable once; edits then take effect
when the server restarts. No Node.js or frontend build step is needed.

```powershell
uv pip install --python .venv-system\Scripts\python.exe -e ".[dev]"
.\.venv-system\Scripts\python.exe -m playwright install chromium
.\.venv-system\Scripts\python.exe -m yolo_studio --port 8766
```

In another terminal, run checks against that test server:

```powershell
.\.venv-system\Scripts\python.exe tests\smoke\check_setup.py --device cpu
.\.venv-system\Scripts\python.exe tests\integration\test_web_dashboard.py --port 8766 --browser
.\.venv-system\Scripts\python.exe tests\integration\test_browser_camera.py --url http://127.0.0.1:8766 --browser
.\.venv-system\Scripts\python.exe tests\integration\test_features_monitor.py --port 8766
```

Checks use synthetic/bundled sample images and isolated sessions. Browser QA
screenshots are written to `runtime/artifacts/`. The desktop entry point is
`python -m yolo_studio.desktop`; `start.cmd` and `start-phone.cmd` invoke it.
The installed console commands are `yolo-studio` and `yolo-webcam`.
Browser assets are included in built wheels, so installed distributions do not
need a separate frontend checkout. Checkout runs store generated files in
`runtime/`; wheel installations default to `~/.yolo-studio/runtime/`. Set
`YOLO_STUDIO_RUNTIME_DIR` to an absolute directory to override this location.

## Documentation

- [Full usage guide, settings, flags, and deployment](docs/usage.md)
- [Architecture and contributor notes](docs/architecture.md)

Environments, model weights, runtime files, editor settings, and local secrets
are excluded from Git. This repository contains source and reproducibility
instructions; it does not contain recorded camera footage.
