const $ = (id) => document.getElementById(id);
let source = "laptop",
  size = "n",
  frameId = -1,
  phase = "idle";
let blobUrl = null,
  polling = true;
let browserStream = null,
  uploadToken = 0;
let liveSocket = null,
  activeGeneration = 0,
  renderBusy = false,
  pendingFrame = null,
  displayTimes = [];
let sharingQueue = Promise.resolve(),
  sharingRevision = 0;
function connectLive() {
  if (!polling) return;
  liveSocket = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/live`,
  );
  liveSocket.binaryType = "arraybuffer";
  liveSocket.onmessage = (event) => {
    const data = new DataView(event.data);
    if (data.byteLength < 8 || data.getUint32(4) !== activeGeneration) return;
    pendingFrame = {
      blob: new Blob([event.data.slice(8)], { type: "image/jpeg" }),
      id: data.getUint32(0),
    };
    drawLatest();
  };
  liveSocket.onclose = () => {
    if (polling) setTimeout(connectLive, 1500);
  };
  liveSocket.onerror = () => liveSocket.close();
}
async function drawLatest() {
  if (renderBusy) return;
  renderBusy = true;
  while (pendingFrame && polling) {
    const frame = pendingFrame;
    pendingFrame = null;
    const nextUrl = URL.createObjectURL(frame.blob),
      previousUrl = blobUrl;
    await new Promise((resolve) => {
      $("video").onload = resolve;
      $("video").onerror = resolve;
      $("video").src = nextUrl;
    });
    blobUrl = nextUrl;
    frameId = frame.id;
    if (previousUrl) URL.revokeObjectURL(previousUrl);
    const now = performance.now();
    displayTimes.push(now);
    displayTimes = displayTimes.filter((time) => now - time < 1000);
    if (phase === "running") {
      $("video").hidden = false;
      $("empty").hidden = true;
    }
  }
  renderBusy = false;
}
const captureVideo = document.createElement("video"),
  captureCanvas = document.createElement("canvas");
captureVideo.muted = true;
captureVideo.playsInline = true;
const modeNames = {
  all: "COMBINED VISION",
  detect: "OBJECT DETECTION",
  segment: "OBJECT SEGMENTATION",
  pose: "HUMAN POSE",
  raw: "RAW PREVIEW",
};
const featureIds = {
  detect: "featureDetect",
  segment: "featureSegment",
  pose: "featurePose",
};
function selectedFeatures() {
  return Object.keys(featureIds).filter((feature) => $(featureIds[feature]).checked);
}
function selectFeatures(features) {
  Object.entries(featureIds).forEach(
    ([feature, id]) => ($(id).checked = features.includes(feature)),
  );
}
function featureTitle(features) {
  return features.length === 3
    ? "COMBINED VISION"
    : features.length === 0
      ? "RAW PREVIEW"
      : features.length === 1
        ? modeNames[features[0]]
        : features
            .map((feature) => ({ detect: "BOXES", segment: "MASKS", pose: "POSE" })[feature])
            .join(" + ");
}

function markDirty() {
  $("dirtyLabel").textContent = "Changes ready to apply";
  $("dirtyLabel").classList.add("dirty");
}
function pickSource(value, changed = true) {
  if (changed) serverAudio.stop();
  if (changed) clientMicrophone.stop();
  source = value;
  document.querySelectorAll("[data-source]").forEach((button) => {
    const selected = button.dataset.source === value;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", selected);
  });
  $("cameraFields").hidden = value !== "laptop";
  $("urlField").hidden = value === "laptop";
  $("urlField").hidden = !["phone", "url"].includes(value);
  $("browserCameraField").hidden = value !== "browser";
  $("facingField").hidden = value !== "browser";
  $("audioPanel").hidden = value !== "laptop";
  $("shareField").hidden = value !== "browser";
  $("shareHint").hidden = value !== "browser";
  $("clientAudioField").hidden = value !== "browser";
  $("sourceHint").textContent =
    value === "laptop"
      ? "Camera attached to the backend laptop."
      : value === "browser"
        ? "This device’s camera. Allow camera access; frames are sent to the backend for inference. Requires HTTPS or localhost."
        : value === "phone"
          ? "IP Webcam base address on the server’s network. Default port: 8080."
          : "Direct HTTP/HTTPS or RTSP video feed, not a webpage link.";
  if (changed) markDirty();
}
function pickSize(value, changed = true) {
  size = value;
  document.querySelectorAll("[data-size]").forEach((button) => {
    const selected = button.dataset.size === value;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", selected);
  });
  if (changed) markDirty();
}
function ranges() {
  $("confidenceValue").textContent = `${$("confidence").value}%`;
  $("qualityValue").textContent = `${$("quality").value}%`;
}
function config() {
  const [width, height] = $("captureSize").value.split(",").map(Number);
  return {
    source,
    camera: Number($("camera").value),
    url: $("url").value.trim(),
    features: selectedFeatures(),
    size,
    device: $("device").value,
    imgsz: Number($("imgsz").value),
    confidence: Number($("confidence").value) / 100,
    boxes: true,
    share_with_operator: $("shareOperator").checked,
    share_audio: $("shareAudio").checked,
    width,
    height,
    preview_width: Number($("previewWidth").value),
    quality: Number($("quality").value),
    max_fps: Number($("maxFps").value),
  };
}
function hydrate(c) {
  pickSource(c.source, false);
  pickSize(c.size, false);
  $("camera").value = c.camera;
  $("url").value = c.url;
  selectFeatures(
    c.features ||
      {
        raw: [],
        detect: ["detect"],
        segment: ["detect", "segment"],
        pose: ["pose"],
        all: ["detect", "segment", "pose"],
      }[c.mode] ||
      [],
  );
  $("device").value = c.device;
  $("imgsz").value = c.imgsz;
  $("confidence").value = Math.round(c.confidence * 100);
  $("shareOperator").checked = !!c.share_with_operator;
  $("shareAudio").checked = c.share_audio ?? true;
  $("shareAudio").disabled = !$("shareOperator").checked;
  $("captureSize").value = `${c.width},${c.height}`;
  $("previewWidth").value = c.preview_width;
  $("quality").value = c.quality;
  $("maxFps").value = c.max_fps;
  ranges();
}
async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : (data.detail || []).map((item) => item.msg).join("; "),
    );
  return data;
}
function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}
function renderStatus(s) {
  serverAudio.update(s, source);
  activeGeneration = s.generation;
  if (s.frame_id < frameId) {
    frameId = -1;
    stopBrowserCamera();
  }
  phase = s.phase;
  const running = phase === "running",
    busy = ["starting", "loading", "stopping"].includes(phase);
  const badge = $("statusBadge");
  badge.textContent = `● ${running ? "Live" : phase === "error" ? "Source error" : busy ? "Connecting" : "Idle"}`;
  badge.classList.toggle("live", running);
  badge.classList.toggle("failed", phase === "error");
  $("apply").textContent = running ? "Apply changes" : busy ? "Apply / restart" : "▶ Start preview";
  $("stop").disabled = ["idle", "stopping"].includes(phase);
  if (phase !== "running") {
    $("video").hidden = true;
    $("empty").hidden = false;
    $("emptyTitle").textContent =
      phase === "error"
        ? "Let’s reconnect"
        : busy
          ? "Preparing your live view"
          : "Your live view starts here";
    $("emptyText").textContent = s.message;
  }
  if (phase === "error") {
    showError(s.message);
    stopBrowserCamera();
  }
  const m = s.metrics;
  $("captureFps").textContent = m.capture_fps ?? "—";
  $("processFps").textContent =
    phase === "running"
      ? displayTimes.filter((time) => performance.now() - time < 1000).length
      : "—";
  $("inferenceMs").textContent = m.inference_ms ?? "—";
  $("frameAge").textContent = m.frame_age_ms ?? "—";
  $("resolution").textContent = m.resolution ?? "—";
  $("sourceLabel").textContent =
    s.config.source === "laptop"
      ? "SERVER CAMERA"
      : s.config.source === "browser"
        ? "MY BROWSER CAMERA"
        : s.config.source === "phone"
          ? "PHONE CAMERA"
          : "WEB STREAM";
  $("modeLabel").textContent = featureTitle(s.config.features || []);
  $("runtimeLabel").textContent =
    m.device === undefined
      ? "Ready when you are"
      : m.device === "cpu"
        ? "CPU inference"
        : `GPU ${m.device}`;
  let hint = "Try Raw preview to check the camera connection before adding inference.";
  if (running) {
    if ((m.preview_age_ms || 0) > 3000)
      hint = "Waiting for a fresh processed frame. Try a smaller model or Raw preview.";
    else if (s.config.mode === "raw")
      hint =
        "Inference is off. If this feed is slow, check the connection and phone capture settings.";
    else if (m.processing_fps && m.capture_fps > m.processing_fps * 1.5)
      hint =
        "Inference is slower than capture. Older frames are skipped to keep the preview current. Try nano / 320 px or Raw preview.";
    else
      hint =
        "Showing the newest available frames. Preview size and JPEG quality control browser bandwidth.";
  }
  $("healthText").textContent = hint;
  $("counts").replaceChildren(
    ...Object.entries(m.counts || {}).map(([task, count]) => {
      const span = document.createElement("span");
      span.textContent = `${count} ${task === "pose" ? "people" : task === "segment" ? "masks" : "objects"}`;
      return span;
    }),
  );
}
async function statuses() {
  while (polling) {
    try {
      renderStatus(await api("/api/status"));
    } catch (error) {
      showError(`Server unavailable: ${error.message}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
}
async function pollFrames() {
  while (polling) {
    if (liveSocket?.readyState === WebSocket.OPEN) {
      await new Promise((resolve) => setTimeout(resolve, 200));
      continue;
    }
    try {
      const response = await fetch(`/api/frame?after=${frameId}`);
      if (response.status === 200 && liveSocket?.readyState !== WebSocket.OPEN) {
        const nextId = Number(response.headers.get("X-Frame-Id"));
        pendingFrame = { blob: await response.blob(), id: nextId };
        drawLatest();
      }
    } catch {
      /* Status polling handles connection errors. */
    }
    await new Promise((resolve) => setTimeout(resolve, phase === "running" ? 16 : 200));
  }
}
async function fullscreen() {
  try {
    await toggleViewerFullscreen($("viewer"));
  } catch (error) {
    showError(`Fullscreen unavailable: ${error.message}`);
  }
}
function stopBrowserCamera() {
  clientMicrophone.stop();
  uploadToken++;
  if (browserStream) browserStream.getTracks().forEach((track) => track.stop());
  browserStream = null;
  captureVideo.srcObject = null;
}
async function startBrowserCamera() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)
    throw new Error("Browser camera requires HTTPS or localhost. Open the HTTPS tunnel link.");
  stopBrowserCamera();
  const id = $("browserCamera").value;
  browserStream = await navigator.mediaDevices.getUserMedia({
    video: id
      ? {
          deviceId: { exact: id },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        }
      : {
          facingMode: { ideal: $("facingMode").value },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
    audio: false,
  });
  captureVideo.srcObject = browserStream;
  await captureVideo.play();
  const devices = await navigator.mediaDevices.enumerateDevices(),
    selected = browserStream.getVideoTracks()[0].getSettings().deviceId;
  $("browserCamera").replaceChildren(
    ...devices
      .filter((device) => device.kind === "videoinput")
      .map((device, index) => {
        const option = document.createElement("option");
        option.value = device.deviceId;
        option.textContent = device.label || `Camera ${index + 1}`;
        return option;
      }),
  );
  $("browserCamera").value = selected || "";
}
async function uploadFrames(generation, settings) {
  const token = ++uploadToken;
  const context = captureCanvas.getContext("2d");
  while (polling && browserStream && token === uploadToken) {
    const started = performance.now();
    try {
      const width = captureVideo.videoWidth,
        height = captureVideo.videoHeight;
      if (!width || !height) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        continue;
      }
      const scale = Math.min(1, settings.preview_width / width);
      captureCanvas.width = Math.max(1, Math.round(width * scale));
      captureCanvas.height = Math.max(1, Math.round(height * scale));
      context.drawImage(captureVideo, 0, 0, captureCanvas.width, captureCanvas.height);
      const blob = await new Promise((resolve) =>
        captureCanvas.toBlob(resolve, "image/jpeg", settings.quality / 100),
      );
      if (token !== uploadToken || !blob) break;
      if (liveSocket?.readyState === WebSocket.OPEN) {
        if (liveSocket.bufferedAmount < 256000) {
          const header = new Uint8Array(4);
          new DataView(header.buffer).setUint32(0, generation);
          liveSocket.send(new Blob([header, blob]));
        }
      } else {
        const response = await fetch(`/api/browser-frame?generation=${generation}`, {
          method: "POST",
          headers: { "Content-Type": "image/jpeg" },
          body: blob,
        });
        if (![204, 409].includes(response.status))
          throw new Error(`Camera upload failed (${response.status}).`);
      }
    } catch (error) {
      showError(error.message);
      stopBrowserCamera();
      break;
    }
    // Pace uploads; WebSocket buffering is bounded and HTTP fallback is serial.
    await new Promise((resolve) =>
      setTimeout(resolve, Math.max(20, 1000 / settings.max_fps - (performance.now() - started))),
    );
  }
}
document
  .querySelectorAll("[data-source]")
  .forEach((button) => button.addEventListener("click", () => pickSource(button.dataset.source)));
document
  .querySelectorAll("[data-size]")
  .forEach((button) => button.addEventListener("click", () => pickSize(button.dataset.size)));
$("configForm").addEventListener("input", () => {
  ranges();
  markDirty();
});
$("configForm").addEventListener("change", markDirty);
$("facingMode").addEventListener("change", () => {
  // A specific deviceId overrides facingMode; clear it when choosing front/rear.
  $("browserCamera").value = "";
});
$("configForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  serverAudio.stop();
  $("apply").disabled = true;
  showError("");
  try {
    const settings = config();
    if (settings.source === "browser") await startBrowserCamera();
    else stopBrowserCamera();
    await sharingQueue;
    settings.share_with_operator = $("shareOperator").checked;
    settings.share_audio = $("shareAudio").checked;
    const state = await api("/api/config", settings);
    if (settings.source === "browser") {
      uploadFrames(state.generation, settings);
      if ($("shareOperator").checked && $("shareAudio").checked)
        clientMicrophone.start(state.generation);
    }
    $("dirtyLabel").textContent = "Settings applied";
    $("dirtyLabel").classList.remove("dirty");
    renderStatus(state);
  } catch (error) {
    stopBrowserCamera();
    showError(error.message);
  } finally {
    $("apply").disabled = false;
  }
});
$("stop").addEventListener("click", async () => {
  serverAudio.stop();
  stopBrowserCamera();
  try {
    await api("/api/stop", {});
    showError("");
  } catch (error) {
    showError(error.message);
  }
});
async function updateClientSharing() {
  const revision = ++sharingRevision;
  const sharing = {
    share_with_operator: $("shareOperator").checked,
    share_audio: $("shareAudio").checked,
  };
  $("shareAudio").disabled = !sharing.share_with_operator;
  if (!sharing.share_with_operator || !sharing.share_audio)
    clientMicrophone.stop("Microphone muted. No microphone audio is being shared.");
  // Preserve toggle order even if the connection is slow.
  const update = sharingQueue.then(() => api("/api/sharing", sharing));
  sharingQueue = update.catch(() => {});
  try {
    const state = await update;
    if (
      revision === sharingRevision &&
      browserStream &&
      sharing.share_with_operator &&
      sharing.share_audio
    )
      clientMicrophone.start(state.generation);
  } catch (error) {
    showError(error.message);
  }
}
$("shareOperator").addEventListener("change", updateClientSharing);
$("shareAudio").addEventListener("change", updateClientSharing);
$("fullscreen").addEventListener("click", fullscreen);
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    (document.fullscreenElement || $("viewer").classList.contains("expanded"))
  ) {
    event.preventDefault();
    fullscreen();
  } else if (
    event.key.toLowerCase() === "f" &&
    !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)
  ) {
    event.preventDefault();
    fullscreen();
  }
});
$("fastPreset").addEventListener("click", () => {
  pickSize("n");
  $("imgsz").value = 320;
  $("previewWidth").value = 640;
  $("quality").value = 60;
  $("maxFps").value = 20;
  ranges();
  markDirty();
});
$("rawPreset").addEventListener("click", () => {
  selectFeatures([]);
  markDirty();
});
window.addEventListener("pagehide", () => {
  polling = false;
  liveSocket?.close();
  serverAudio.stop();
  stopBrowserCamera();
  navigator.sendBeacon("/api/stop", new Blob(["{}"], { type: "application/json" }));
  if (blobUrl) URL.revokeObjectURL(blobUrl);
});
window.addEventListener("pageshow", (event) => {
  if (event.persisted) location.reload();
});
async function init() {
  try {
    const options = await api("/api/options");
    $("device").replaceChildren(
      ...options.devices.map((device) => {
        const option = document.createElement("option");
        option.value = device.value;
        option.textContent = device.label;
        option.disabled = !!device.disabled;
        return option;
      }),
    );
    $("gpuHint").textContent = options.gpu_available
      ? "GPU available. Auto selects GPU 0."
      : "GPU unavailable in the installed PyTorch build. CPU is available.";
    serverAudio.loadDevices();
    const state = await api("/api/status");
    hydrate(state.config);
    renderStatus(state);
    statuses();
    pollFrames();
  } catch (error) {
    showError(error.message);
  }
}
$("operatorLink").hidden = !["localhost", "127.0.0.1", "::1"].includes(location.hostname);
init().then(connectLive);
