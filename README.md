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
.\start-web.ps1
# In a second terminal, publish a temporary HTTPS link:
.\start-tunnel.ps1
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

Root PowerShell scripts are the public commands. Shared Python invocation lives in
`scripts/lib/python.ps1`; installer and benchmark tools live in `scripts/python/`.
Use Ctrl+C for services started in a terminal. `stop-web.ps1` and
`stop-tunnel.ps1` stop their recorded background instances.

## Mobile and audio

Open the public HTTPS tunnel URL on your phone. Choose **My camera**, select a
front/rear camera preference, and press **Start preview**. Touch controls,
portrait/landscape layouts, and fullscreen (with an in-page fallback) are supported.
Phone camera access requires HTTPS or localhost; an HTTP LAN address cannot
normally access a mobile browser's camera.

For **Server camera**, start the preview, choose a **Server microphone**, and tap
**Listen**. **Mute**, Stop, source changes, backgrounding the page, and disconnects
stop listening. The microphone is captured on the backend laptop; browser/phone
sources remain video-only. Audio and CV video are independent, so they may have
different delays. Nothing is recorded.
Windows input choices omit duplicate legacy drivers. **Input level** shows the
received microphone signal; **Test speaker** checks sound output in your browser.
If the input meter stays flat while speaking, check the laptop's mic-mute key
and Windows Sound input settings.

All Windows commands are PowerShell scripts. If Windows blocks script execution,
run the same command with a per-process bypass, for example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-web.ps1
```

`start-phone.cmd` used to launch the desktop preview with `--phone`. It and the
duplicate CMD wrappers have been removed. Use:

```powershell
.\start-desktop.ps1 --phone http://10.12.48.195:8080 --fullscreen
.\start-web.ps1 -Port 8765 -NoBrowser
.\start-tunnel.ps1 -Port 8765
```

The desktop viewer automatically reads [config/desktop.toml](config/desktop.toml).
Edit its CV mode, model size, CPU/GPU device, camera/source, confidence, and window
settings, then run `.\start-desktop.ps1`. Restart the viewer after editing.
Command-line flags override the file:

```powershell
.\start-desktop.ps1 --device cpu --mode pose
.\start-desktop.ps1 --config .\config\desktop.toml
.\start-desktop.ps1 --no-config
```

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
  audio.py            Shared on-demand server microphone capture
  vision.py           Model loading, inference, and annotation
  engine.py           Inference workers and browser sessions
  paths.py            Packaged assets and writable runtime locations
  app.py              Compatibility ASGI import
  server.py           Compatibility web command
  desktop.py          Compatibility desktop command
scripts/              Shared PowerShell helper and Python maintenance tools
scripts/python/       PyTorch installer and performance benchmark
config/desktop.toml   Default settings for the standalone desktop viewer
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
.\.venv-system\Scripts\python.exe -m unittest discover -s tests/unit -v
.\.venv-system\Scripts\python.exe tests\smoke\check_setup.py --device cpu
.\.venv-system\Scripts\python.exe tests\integration\test_mobile.py --port 8766
.\.venv-system\Scripts\python.exe tests\integration\test_audio_frontend.py --port 8766
.\.venv-system\Scripts\python.exe tests\integration\test_web_dashboard.py --port 8766 --browser
.\.venv-system\Scripts\python.exe tests\integration\test_browser_camera.py --url http://127.0.0.1:8766 --browser
.\.venv-system\Scripts\python.exe tests\integration\test_features_monitor.py --port 8766
```

Checks use synthetic/bundled sample images and isolated sessions. Browser QA
screenshots are written to `runtime/artifacts/`. The desktop entry point is
`python -m yolo_studio.desktop`; `start-desktop.ps1` forwards its Python flags.
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
