# YOLO webcam demo

Live object detection, instance segmentation, and human pose estimation on your
laptop. The default `all` mode overlays object boxes and colored masks with human
skeletons. Segmentation supplies the object detections, so combined mode runs two
models rather than three. Models run sequentially on the same original frame.

## Start

### Browser dashboard

Double-click `start-web.cmd` to start the Python server and open
**http://127.0.0.1:8765** in your browser. Select a source and click **Start
preview**. Change settings, then click **Apply changes**. **Stop** releases the
camera; closing the browser alone does not stop inference. Stop the server with
Ctrl+C in its terminal. If the dashboard was launched in the background during
initial setup, run `stop-web.cmd` first before restarting it with `start-web.cmd`.
The existing desktop launchers still work.

```powershell
.\start-web.cmd
# Another port:
.\start-web.cmd --port 9000
# Server only, without automatically opening a browser:
.\.venv-system\Scripts\python.exe -m yolo_studio --port 8765
# Optional access from devices on your trusted LAN:
.\start-web.cmd --host 0.0.0.0
```

With LAN listening enabled, browse to `http://LAPTOP_IP:8765`. The dashboard has
no account/login system. Local LAN access and link-accessible tunnels allow
visitors to select the server camera and phone feed. The default
bind address is `127.0.0.1`. Laptop camera selection always means the camera
attached to the server laptop, even if you view the page on a phone.

| Browser control | Available options |
| --- | --- |
| Source | Server camera index, this viewer?s browser camera, Android IP Webcam base address, direct HTTP/HTTPS/RTSP video URL |
| Feature checklist | Object detection, object segmentation, human pose; any combination; none selected = raw preview |
| Model size | YOLO26 nano, small, medium, large, extra-large |
| Runtime | Auto, CPU, each CUDA GPU detected by PyTorch; unavailable GPU is disabled |
| Capture resolution | 640×480, 1280×720, 1920×1080; laptop webcam only |
| Inference size | 320, 480, 640, 960, 1280 |
| Confidence / detection | Confidence threshold; Object detection checkbox controls boxes and labels |
| Preview | Width 640–1920, JPEG quality 35–95, output cap 1–60 FPS |
| Display | Fullscreen button or F; Escape leaves fullscreen; aspect ratio stays constant |

Web source URLs must point to an actual video stream, not a YouTube watch page
or camera control webpage. Phone base addresses automatically use `/video`.
Larger models download on first use; controls remain accessible while loading.
Changing settings reloads the session. Newer settings replace older pending
changes; an in-progress model download may finish before the new session starts.
Each browser profile has an isolated session identified by an HttpOnly cookie.
Tabs in the same profile share that session; separate browser profiles/devices
do not share camera frames or settings. Inactive sessions are released after
about 90 seconds. Settings reset when the server restarts. CPU/GPU compute is
still shared by all sessions. Simultaneous server-camera sessions may compete
for the same physical camera.



### Detection feature checklist

Select any combination of **Object detection** (boxes/labels), **Object
segmentation** (colored masks), and **Human pose** (skeletons). Uncheck all for
raw video. Detection + segmentation uses the segmentation model's detections,
so it does not run an extra detector. Detection + pose loads those two models;
segmentation + pose loads those two. More models use more compute. Settings
apply when you click **Start / apply**. Existing desktop `--mode` flags remain
supported; API clients can send a `features` array.

### What the settings mean

| Setting | Effect |
| --- | --- |
| Inference size | Model input resolution. Larger inputs can reveal finer details/smaller objects, at more compute cost. Does not widen the camera view. |
| Confidence | Minimum object/person score to show a result. Lower displays more candidates and more false positives; higher hides uncertain results. |
| Preview width | Maximum transmitted video width. Smaller saves upload/download bandwidth; aspect ratio is preserved. |
| Output FPS cap | Maximum capture/send/process rate; not a guaranteed FPS. A lower cap reduces network and compute load. |
| JPEG quality | Higher is sharper and larger. Lower reduces bandwidth but loses detail. Applies to browser uploads and returned previews. |
| Faster preview | Selects nano, 320 inference size, 640 preview width, JPEG quality 60 and FPS cap 20. Keeps chosen features/runtime. Click Apply changes. |
| Compare raw feed | Unchecks all CV features. Click Apply changes to compare camera/network performance without inference. |

The interface includes hover explanations and an expandable settings guide.
FP16 GPU predictions use `quantize=16`; CPU uses `quantize=32`. The deprecated
`half` prediction argument is no longer sent.

### Multiple users

Each browser profile receives a separate HttpOnly session cookie and has its
own config, captured frames, preview frames, model instances, and worker thread.
Tabs in the same profile share that session. CPU, GPU memory, GPU execution and
network bandwidth are shared by every worker: multiple active users can lower
FPS, and large models can exhaust available GPU memory. Model loading is
serialized to avoid concurrent downloads of the same weights. There is no
fair-share GPU scheduler or automatic batching across users.

The session registry currently allows 32 browser sessions, including idle
sessions; this is a bookkeeping limit, not a promise of 32 simultaneous heavy
inference users. Idle sessions are removed after roughly 90 seconds. Closing a
page normally sends Stop; abrupt disconnects rely on timeouts. Concurrent access
to the same physical server webcam may be rejected by its driver.

### View a client's video on the server laptop

Open **http://127.0.0.1:8765/monitor** on the backend laptop, or click **Client
monitor** in the local dashboard header.

1. Your friend chooses **My camera**, allows browser camera access, and checks
   **Allow the server operator to view my camera**.
2. They click **Start / apply** and keep the page open.
3. In the local monitor, select their client session.
4. Choose **Raw incoming camera** or **Processed / annotated preview**. Use the
   fullscreen button to display it on the laptop.

Raw viewing reuses the incoming JPEG rather than re-encoding it or waiting for
CV, so it can refresh independently of inference. Annotated viewing uses the
same processed frames the client sees. Frames stay in memory; there is no
recording. Sharing is off by default, and disabling it or stopping the camera
immediately revokes monitor access. Anonymous client labels identify sessions;
no login names or camera permissions are inferred.

The monitor page and APIs require a localhost hostname and loopback client
address. They are blocked through the public Cloudflare URL and for other LAN
viewers. Other visitors cannot watch another client's stream. This is a local
operator monitor, not a public multi-camera dashboard.

### Camera ownership and remote viewers

- **Server camera** opens the webcam attached to the backend laptop.
- **My camera** requests camera permission on the device viewing the page.
  A camera selector appears after permission is granted. The browser captures
  video without audio, uploads JPEGs to the backend, and displays the returned
  inference preview over a persistent WebSocket. Uploads do not wait for an
  HTTP round trip per frame. When the upload buffer fills, newer capture attempts
  are skipped instead of building an unbounded queue. Stop, switching source, or leaving the page
  releases the browser camera tracks.
- **Phone** remains a server-side capture source: the backend laptop must be
  connected to the Android hotspot (or a network that can reach the phone).
  IP Webcam's default port is **8080**. Check its displayed address after
  switching networks; remote viewers do not need access to that private IP.
- **Web stream** is also fetched by the backend, using a direct media URL.

Browser camera permission requires HTTPS or localhost. A Cloudflare HTTPS
link satisfies this; plain HTTP on a LAN IP does not. Viewer-camera frames are
sent through Cloudflare to your backend for inference, not processed entirely
on the viewer's device. Preview width/JPEG quality also control browser upload
size. Internet round-trip latency and backend load can limit remote FPS.

### Share through Cloudflare Tunnel

This uses the same `cloudflared` Quick Tunnel approach as
`C:\Dev\Projects\lm-studio-demo`, forwarding to YOLO's port **8765**.

```powershell
# Start the dashboard if it is not already running:
.\start-web.cmd
# In another terminal, create a link-accessible HTTPS tunnel:
.\start-tunnel.cmd
# Optional email-PIN protection, if you decide to restrict access later:
.\start-tunnel.cmd -AllowedEmail 'friend@example.com'
# Alternate backend port:
.\start-tunnel.cmd -Port 9000
```

Share the printed `https://...trycloudflare.com` address. No email login is
required by default, as requested: anyone with the link can use the dashboard,
including its server-camera and phone options. Inference stays on the backend
laptop, and the phone's private IP is not publicly exposed as a separate service.

Keep the laptop, dashboard, and tunnel running. Quick Tunnel URLs change when
the tunnel restarts. Stop the background tunnel created during initial setup
with `stop-tunnel.cmd`; for a foreground tunnel, use Ctrl+C in its terminal.
Stop an existing background tunnel before running `start-tunnel.cmd` to avoid
creating two tunnels. Stopping the tunnel does not stop the local dashboard.

Tunnel headers from loopback are trusted for HTTPS origin checks and secure
session cookies. Other cross-origin control/upload requests are rejected. The
backend remains bound to loopback; no inbound router port forwarding is needed.
Quick Tunnels are temporary demo hosting rather than a stable production URL.
Use a named Cloudflare Tunnel for a permanent hostname.

References: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
and [browser camera requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

### Diagnose slow streaming

Click **Compare raw feed**, then **Apply changes** to disable inference. If raw
video is smooth but annotated video is slow, try **Faster preview**, a single
vision mode, or GPU runtime. If raw video is also slow, lower the phone's video
resolution/JPEG quality/FPS or improve its network connection.

The browser server reads source frames continuously and retains only the latest
one, skipping stale frames when processing is slower than capture. It also
stores only the latest encoded preview and pushes frames through WebSocket.
The browser keeps at most one pending frame while drawing; inbound uploads
retain only the latest undecoded JPEG. If WebSocket is unavailable, the app
falls back to the original HTTP transport. These bounds reduce application-side
queues; it cannot remove buffering
inside the phone, network, or decoder. Output FPS is a ceiling, not a guaranteed
rate. No video is saved by the server.

The dashboard shows capture FPS, actually displayed browser FPS, inference time, and
frame age. Frame age is measured from decoding on the laptop to publishing the
preview; it excludes phone capture/encoding and network delay. Lower preview
width and JPEG quality reduce browser bandwidth; lower inference size/model
size reduce processing work.

To add the browser dependencies to an existing environment without changing
the installed CPU/GPU PyTorch build:

```powershell
uv pip install --python .venv-system\Scripts\python.exe -r requirements.txt
```

New installations use the existing `setup.ps1` CPU/GPU options, which now include
the web dependencies. No Node.js build or cloud service is required.

Optional browser integration checks, with the server running:

```powershell
uv pip install --python .venv-system\Scripts\python.exe -r requirements-dev.txt
.\.venv-system\Scripts\python.exe -m playwright install chromium
.\.venv-system\Scripts\python.exe tests\integration\test_web_dashboard.py --browser
.\.venv-system\Scripts\python.exe tests\integration\test_browser_camera.py --browser
.\.venv-system\Scripts\python.exe tests\integration\test_features_monitor.py --port 8765
```

These checks use a local sample MJPEG stream, validate CPU/GPU inference when
available, switch source/mode/model through the browser, check fullscreen and
mobile layout, and verify Stop releases capture. They use isolated test sessions and do not replace other viewers'
source/settings. Screenshots use the bundled sample image and
are written to `runtime/artifacts/`.


### Faster remote streaming

The app uses a single persistent WebSocket for browser-camera uploads and
processed-preview delivery. Frames no longer require separate upload and
preview HTTP round trips. Upload buffering is bounded, stale generations are
rejected, and the browser drops older pending previews when rendering falls
behind. Status/config requests still use HTTP. Connections reconnect on loss;
HTTP capture/preview is retained as a fallback.

GPU inference uses FP16; CPU uses FP32. Browser segmentation uses the model's
normal mask resolution rather than generating high-resolution retina masks.
This reduces mask-processing cost, with potentially coarser mask boundaries.
The desktop script keeps its original high-resolution masks by default.

For a friend on the public URL, try GPU, nano, 320 inference pixels, 640 preview
pixels, and JPEG quality 60 (the **Faster preview** preset sets the size/quality
options). Use a single vision mode when you do not need combined segmentation
and pose. A smaller output FPS cap can also prevent bandwidth saturation.
Remote upload/download speed and shared backend GPU load still limit FPS.

On a synthetic camera using combined mode and the same public tunnel, measured
browser delivery improved from 3.2 FPS with HTTP to 13.6 FPS with WebSocket.
This is a short sample, not a guaranteed rate for real footage. Test your own
connection with:

```powershell
.\.venv-system\Scripts\python.exe scripts\python\benchmark_web.py --url https://YOUR-TUNNEL.trycloudflare.com
.\.venv-system\Scripts\python.exe scripts\python\benchmark_web.py --url https://YOUR-TUNNEL.trycloudflare.com --http
```

The benchmark uses Chromium's synthetic camera, not your real webcam, and
requires the optional browser-test dependencies described above. It creates
an isolated test session and releases the camera after testing.

### Desktop preview

Double-click `start.cmd`, or run:

```powershell
cd C:\Dev\Projects\yolo-demo
.\start.cmd --mode all --size n --device auto
.\start.cmd --mode all --size s --device gpu --fullscreen
```

Click the preview to give it keyboard focus. **F** toggles fullscreen. **Escape**
leaves fullscreen; in windowed mode it quits. **Q** always quits. You can also
close the window. Resizing and fullscreen preserve the source aspect ratio:
black borders fill unused space without stretching or cropping the image.

## Android IP Webcam input

Start the camera server in IP Webcam on Android, and connect the phone and
laptop to the same reachable Wi-Fi network (or connect the laptop to the phone's
hotspot). Open `http://10.12.48.195:8080` on the laptop to verify connectivity.
The demo uses the video feed at `http://10.12.48.195:8080/video`.

```powershell
# Your phone address is the default for --phone:
.\start-phone.cmd --fullscreen
# Equivalent, with explicit settings:
.\start.cmd --phone http://10.12.48.195:8080 --mode all --size n --device auto
# Verify one phone frame without opening a window:
.\start.cmd --phone --check
# Any explicit HTTP/RTSP video feed:
.\start.cmd --source http://10.12.48.195:8080/video --fullscreen
```

`--phone` accepts the base address and automatically adds `/video`; HTTP phone
addresses without a port use 8080. An explicit
path is kept as supplied. Update the address if the phone's IP changes.
`--phone` and `--source` cannot be used together. All detection, segmentation,
pose, model-size, device, and fullscreen options apply to phone input too.
Set capture resolution and orientation in the phone app: `--width` and `--height`
apply only to the laptop webcam. The phone frame's aspect ratio is preserved.

If authentication is enabled, pass a full URL such as
`--source "http://USERNAME:PASSWORD@10.12.48.195:8080/video"` (URL-encode special
characters in credentials). Network open/read operations time out after about
five seconds. A disconnected stream reports an error; restart the demo after
restoring connectivity. If the page cannot open in a browser, check the server
port, Wi-Fi/client isolation, and whether the phone server is still running.

## Modes and model sizes

| `--mode`        | Output                                             |
| ----------------- | -------------------------------------------------- |
| `detect`        | Object bounding boxes and class labels             |
| `segment`       | Object instance masks, bounding boxes, and labels  |
| `pose`          | Human skeletons with 17 keypoints and person boxes |
| `all` (default) | Object masks/boxes/labels plus human skeletons     |

| `--size` / `--model-size` | Name        | Order    |
| ----------------------------- | ----------- | -------- |
| `n` or `nano`             | Nano        | Smallest |
| `s` or `small`            | Small       | 2        |
| `m` or `medium`           | Medium      | 3        |
| `l` or `large`            | Large       | 4        |
| `x` or `extra-large`      | Extra-large | Largest  |

All modes support all five YOLO26 sizes. The selected weights download into
`runtime/models/` the first time each mode/size is used. Larger models need more compute
and memory; they do not enlarge the camera's viewing angle. Only nano weights
are predownloaded by setup. Nano is the default for responsiveness.

```powershell
# Object masks only, with labels/boxes hidden:
.\start.cmd --mode segment --size small --no-boxes
# Human skeletons:
.\start.cmd --mode pose --size medium --device gpu
# Largest object detector:
.\start.cmd --mode detect --size x --device gpu --imgsz 640
# Combined CPU demo with reduced inference resolution:
.\start.cmd --mode all --size n --device cpu --imgsz 320
# Full HD capture in fullscreen, if the camera supports it:
.\start.cmd --mode all --width 1920 --height 1080 --fullscreen
# Custom local weights; the mode must match the task of the checkpoint:
.\start.cmd --mode segment --model .\models\custom-seg.pt --device auto
```

## Deploy / install on Windows

This is a local application with desktop and browser interfaces. CPU/GPU selection chooses the laptop's
inference device. A server would need its own camera, a local media file, or
network access to an IP camera stream;
this application does not expose a remote inference API.

Install Python and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Copy this project (excluding `.venv`, `.venv-system`, logs, and `runtime/pids/`) to
its destination folder. Use an installed Python that Windows permits to run.
Open PowerShell in that folder and choose an installation:

```powershell
# CPU deployment:
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Compute cpu

# NVIDIA GPU deployment, also supports --device cpu:
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Compute gpu

# List devices exposed by the installed PyTorch build:
.\start.cmd --list-devices

# Launch, selecting GPU when available and otherwise CPU:
.\start.cmd --mode all --size n --device auto
```

The setup script creates `.venv-system`, installs PyTorch and the dependencies,
downloads nano detection/segmentation/pose weights, then validates all three
models, combined overlays, and aspect ratio preservation on a bundled sample
image. `requirements-lock.txt` records the packages installed by the most recent
setup. No administrator rights or system Python package changes are required.

GPU setup uses the official PyTorch `cu128` wheel index by default. It requires
a compatible NVIDIA GPU and driver. Setup explicitly replaces the existing
PyTorch/torchvision packages so switching between CPU and CUDA builds takes
effect. A CUDA-enabled install can run both CPU and GPU inference; switching
`--device` does not require reinstalling it. An explicit GPU request fails with
a clear message when CUDA is unavailable; `auto` falls back to CPU.

| Setup flag           | Default   | Purpose                                                                    |
| -------------------- | --------- | -------------------------------------------------------------------------- |
| `-Compute cpu\|gpu` | `cpu`   | Select CPU or NVIDIA CUDA PyTorch installation                             |
| `-CudaIndex cuNNN` | `cu128` | Choose another official CUDA wheel index compatible with Python/GPU/driver |
| `-SkipCheck`       | Off       | Install without downloading/testing nano model weights                     |

Example with an alternative CUDA index, after verifying it supports your setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Compute gpu -CudaIndex cu128
```

Use the [official PyTorch installation selector](https://docs.pytorch.org/get-started/locally/)
to choose a compatible build. NVIDIA GPU support is implemented through CUDA;
other GPU backends are not exposed by this demo.

`install_torch.py` reads the official package indexes and uses the primary
`download.pytorch.org` host for wheel downloads. This also works on networks
where the alternate `download-r2.pytorch.org` hostname cannot be resolved.

## All runtime flags

Run `.\start.cmd --help` for the same options from the program.

| Flag                               | Default                  | Meaning                                                                      |
| ---------------------------------- | ------------------------ | ---------------------------------------------------------------------------- |
| `--mode detect\|segment\|pose\|all` | `all`                  | Which overlays/models to run                                                 |
| `--size`, `--model-size`       | `n`                    | `n/s/m/l/x` or `nano/small/medium/large/extra-large`                     |
| `--model PATH`                   | Automatic YOLO26 weights | Custom local`.pt` file; requires a single matching `--mode`              |
| `--device auto\|cpu\|gpu\|cuda:N\|N` | `auto`                 | CPU or one CUDA GPU;`gpu` means GPU 0                                      |
| `--camera N`                     | `0`                    | Camera index; try`1` for another webcam                                    |
| `--source PATH_OR_URL` | Webcam | Local image/video or HTTP/HTTPS/RTSP stream; ignores camera capture settings |
| `--phone [URL]` | Off | IP Webcam base URL; bare flag uses `http://10.12.48.195:8080`; adds `/video` to a base address |
| `--width N`                      | `1280`                 | Requested camera capture width                                               |
| `--height N`                     | `720`                  | Requested camera capture height                                              |
| `--imgsz N`                      | `480`                  | Model inference input size; independent of capture/display size              |
| `--confidence FLOAT`             | `0.35`                 | Object/person confidence threshold between 0 and 1                           |
| `--fullscreen`                   | Off                      | Start fullscreen; F toggles it during the demo                               |
| `--window-width N`               | `1280`                 | Initial/restore window width                                                 |
| `--window-height N`              | `720`                  | Initial/restore window height                                                |
| `--no-boxes`                     | Off                      | Hide boxes and labels; retain masks and skeletons                            |
| `--check`                        | Off                      | Process one frame, print counts, and exit without a window                   |
| `--list-devices`                 | Off                      | Print CPU/CUDA availability and GPU names, then exit                         |
| `--help`, `-h`                 | Off                      | Print available options                                                      |

`--model` overrides size selection. `--no-boxes` with detect mode produces no
object overlays. File playback is inference-paced; it ends at the last frame.
Images produce one preview frame and then the program exits. `--check` is useful
for images or for verifying a camera without opening the preview.

## Verify deployment

```powershell
# Verify all tasks on the bundled sample, without opening the camera:
.\.venv-system\Scripts\python.exe tests\smoke\check_setup.py --device cpu
.\.venv-system\Scripts\python.exe tests\smoke\check_setup.py --device gpu
# Verify combined inference on one webcam frame:
.\start.cmd --mode all --device auto --check
# Process a local file without a preview:
.\start.cmd --mode all --source .\example.jpg --check
```

The automated sample checks use nano models. Larger sizes are selectable but
are downloaded and run only when requested. Visual inspection of fullscreen
and skeleton alignment can be done in the interactive preview.

## Capture and performance

The camera requests 1280x720 capture; startup prints the actual returned size.
Unsupported resolutions may fall back to another camera format. All capture
pixels are passed to inference and the preview. The lens limits the physical
viewing angle: move the laptop farther back or use a wider-angle webcam to
capture more of the scene. Increasing `--imgsz` changes inference detail, not
camera coverage. Desktop scripts do not upload footage. Browser-camera mode sends
frames to this backend for inference; camera footage is not recorded.
Internet is required for installation and first-time model downloads.

The current installation on this laptop passes combined CPU and CUDA inference
on the NVIDIA RTX 5060. Earlier installation attempts encountered Windows
application-control WinError 4551; if that error returns on another deployment,
use the CPU build or have the relevant policy permit the official CUDA DLLs.

Close Teams, Zoom, or other applications holding the camera. Open the camera
privacy shutter and enable desktop app camera access in Windows Settings >
Privacy & security > Camera. If performance is slow, try `--size n --imgsz 320`,
a single mode, or CUDA inference. If GPU memory runs out with a larger model,
reduce its size or inference resolution, or select `--device cpu`.

Model/task reference: [Ultralytics YOLO26](https://docs.ultralytics.com/models/yolo26).
